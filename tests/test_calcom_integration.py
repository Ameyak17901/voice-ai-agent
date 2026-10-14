"""
Unit and integration tests for Cal.com API v2 client and tools integration.
Validates username/event_slug, eventTypeId, slot parsing, booking creation,
cancellation, and graceful SQLite fallback when Cal.com is offline.
"""
import pytest
import datetime
import httpx
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock

from vocode.streaming.models.actions import ActionInput
from backend.actions.appointment_actions import (
    CheckAvailabilityAction,
    CheckAvailabilityActionConfig,
    CheckAvailabilityParams,
    BookAppointmentAction,
    BookAppointmentActionConfig,
    BookAppointmentParams,
)
from backend.calendar_service.calcom_client import CalComClient
from backend.tools import (
    check_availability_async,
    check_availability,
    book_appointment_async,
    book_appointment,
    cancel_appointment_async,
)
from backend.db.repository import db_repository


def test_calcom_client_configuration():
    """Verify is_configured rules across various credential combinations."""
    # 1. Empty client
    c_empty = CalComClient(api_key=None, event_type_id=None, username=None, event_slug=None)
    assert not c_empty.is_configured

    # 2. Only API key (missing identifier)
    c_key_only = CalComClient(api_key="cal_live_123", event_type_id=None, username=None, event_slug=None)
    assert not c_key_only.is_configured

    # 3. API key + numeric event_type_id
    c_id = CalComClient(api_key="cal_live_123", event_type_id=98765)
    assert c_id.is_configured

    # 4. API key + username + event_slug (Cal.com v2 modern pattern)
    c_slug = CalComClient(api_key="cal_live_123", username="alexsmith", event_slug="consultation")
    assert c_slug.is_configured


@pytest.mark.asyncio
async def test_calcom_get_available_slots_with_slug():
    """Verify get_available_slots converts Cal.com v2 ISO slots into 12-hour format."""
    client = CalComClient(
        api_key="cal_live_test_key",
        username="alexsmith",
        event_slug="consultation",
        base_url="https://api.cal.com/v2",
    )

    mock_response_data = {
        "status": "success",
        "data": {
            "slots": {
                "2026-10-20": [
                    {"time": "2026-10-20T09:00:00Z"},
                    {"time": "2026-10-20T14:00:00Z"},
                    {"time": "2026-10-20T16:30:00Z"},
                ]
            }
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        slots = await client.get_available_slots(target_date="2026-10-20")

        # Ensure correct query params were constructed
        assert mock_get.called
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["params"]["username"] == "alexsmith"
        assert call_kwargs["params"]["eventTypeSlug"] == "consultation"
        assert call_kwargs["params"]["start"] == "2026-10-20"

        # Verify parsed slots
        assert slots == ["09:00 AM", "02:00 PM", "04:30 PM"]


@pytest.mark.asyncio
async def test_calcom_create_booking_success():
    """Verify create_booking posts to /v2/bookings and parses confirmation response."""
    client = CalComClient(
        api_key="cal_live_test_key",
        username="alexsmith",
        event_slug="consultation",
    )

    mock_resp_data = {
        "status": "success",
        "data": {
            "id": 55566,
            "uid": "cal_bk_live_999",
            "meetingUrl": "https://meet.google.com/xyz-uvw-rst",
            "status": "accepted",
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = mock_resp_data

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await client.create_booking(
            name="Sarah Connor",
            date="2026-10-20",
            time="02:00 PM",
            service="VIP Consultation",
        )

        assert result["status"] == "confirmed"
        assert result["booking_id"] == "cal_bk_live_999"
        assert result["meeting_url"] == "https://meet.google.com/xyz-uvw-rst"

        # Check payload
        payload = mock_post.call_args.kwargs["json"]
        assert payload["username"] == "alexsmith"
        assert payload["eventTypeSlug"] == "consultation"
        assert payload["attendee"]["name"] == "Sarah Connor"
        assert "2026-10-20T14:00:00Z" in payload["start"]


@pytest.mark.asyncio
async def test_calcom_cancel_booking_success():
    """Verify cancel_booking triggers POST to /v2/bookings/{uid}/cancel."""
    client = CalComClient(api_key="cal_live_test_key", username="alexsmith")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await client.cancel_booking("cal_bk_live_999")
        assert res["status"] == "cancelled"
        assert "cal_bk_live_999" in res["message"]


@pytest.mark.asyncio
async def test_tools_calcom_live_lookup_and_fallback(sample_user):
    """
    Integration test:
    1. When Cal.com is configured, check_availability returns Cal.com slots.
    2. When Cal.com is offline / unconfigured, check_availability falls back to SQLite seamlessly.
    """
    user_id = sample_user["id"]
    base = datetime.date(2026, 10, 15)

    # 1. Test Cal.com configured & returning slots
    with patch.object(CalComClient, "is_configured", new_callable=PropertyMock, return_value=True):
        with patch.object(
            CalComClient,
            "get_available_slots",
            new_callable=AsyncMock,
            return_value=["11:00 AM", "03:00 PM"],
        ):
            res = await check_availability_async(date="tomorrow", base_date=base)
            assert res["status"] == "success"
            assert res["source"] == "cal.com"
            assert res["available_slots"] == ["11:00 AM", "03:00 PM"]

    # 2. Test fallback to SQLite when Cal.com is unconfigured
    with patch.object(CalComClient, "is_configured", new_callable=PropertyMock, return_value=False):
        res_fallback = await check_availability_async(date="tomorrow", base_date=base)
        assert res_fallback["status"] == "success"
        assert res_fallback["source"] == "sqlite"
        assert len(res_fallback["available_slots"]) > 0


@pytest.mark.asyncio
async def test_tools_calcom_booking_and_db_persistence(sample_user):
    """
    Verify that booking through tools when Cal.com is configured:
    - Calls Cal.com create_booking
    - Obtains Cal.com UID
    - Persists appointment in local SQLite DB for tenant isolation and history
    """
    user_id = sample_user["id"]
    base = datetime.date(2026, 10, 15)

    mock_cal_res = {
        "status": "confirmed",
        "booking_id": "cal_bk_enterprise_777",
        "meeting_url": "https://meet.google.com/test-meet",
        "summary": "Confirmed on Cal.com",
    }

    with patch.object(CalComClient, "is_configured", new_callable=PropertyMock, return_value=True):
        with patch.object(
            CalComClient,
            "create_booking",
            new_callable=AsyncMock,
            return_value=mock_cal_res,
        ):
            booked = await book_appointment_async(
                name="Diana Prince",
                date="2026-10-16",
                time="11:00 AM",
                service="Cardiology",
                user_id=user_id,
                base_date=base,
            )
            assert booked["status"] == "confirmed"
            assert booked["booking_id"] == "cal_bk_enterprise_777"
            assert booked["source"] == "cal.com"

            # Check that local SQLite DB has the record saved
            db_appts = db_repository.list_appointments(user_id=user_id)
            diana_appt = next((a for a in db_appts if a["name"] == "Diana Prince"), None)
            assert diana_appt is not None
            assert diana_appt["date"] == "2026-10-16"
            assert diana_appt["time"] == "11:00 AM"
            assert diana_appt["status"] == "confirmed"


@pytest.mark.asyncio
async def test_check_availability_action_execution_with_calcom():
    """Verify Vocode CheckAvailabilityAction executes end-to-end with Cal.com integration."""
    action_cfg = CheckAvailabilityActionConfig()
    action = CheckAvailabilityAction(action_config=action_cfg)

    with patch.object(CalComClient, "is_configured", new_callable=PropertyMock, return_value=True):
        with patch.object(
            CalComClient,
            "get_available_slots",
            new_callable=AsyncMock,
            return_value=["10:00 AM", "03:30 PM"],
        ):
            action_input = ActionInput(
                action_config=action_cfg,
                conversation_id="test_conv_calcom_1",
                params=CheckAvailabilityParams(date="2026-10-25"),
            )
            output = await action.run(action_input)
            assert output.response.status == "success"
            assert output.response.available_slots == ["10:00 AM", "03:30 PM"]
            assert "10:00 AM" in output.response.message


@pytest.mark.asyncio
async def test_book_appointment_action_execution_with_calcom(sample_user):
    """Verify Vocode BookAppointmentAction executes end-to-end with Cal.com integration."""
    action_cfg = BookAppointmentActionConfig()
    action = BookAppointmentAction(action_config=action_cfg)

    mock_cal_res = {
        "status": "confirmed",
        "booking_id": "cal_bk_action_runner_888",
        "meeting_url": "https://meet.google.com/action-meet",
        "summary": "Confirmed on Cal.com via Action",
    }

    with patch.object(CalComClient, "is_configured", new_callable=PropertyMock, return_value=True):
        with patch.object(
            CalComClient,
            "create_booking",
            new_callable=AsyncMock,
            return_value=mock_cal_res,
        ):
            action_input = ActionInput(
                action_config=action_cfg,
                conversation_id="test_conv_calcom_2",
                params=BookAppointmentParams(
                    name="Bruce Wayne",
                    date="2026-10-26",
                    time="02:00 PM",
                    service="Executive Checkup",
                ),
            )
            output = await action.run(action_input)
            assert output.response.status == "confirmed"
            assert output.response.booking_id == "cal_bk_action_runner_888"
            assert "Bruce Wayne" in output.response.summary

