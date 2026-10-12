"""
Automated unit and integration test suite for appointment actions:
- check_availability
- book_appointment
- cancel_appointment
- Multi-tenant appointment isolation
- Vocode CancelAppointmentAction execution
"""
import pytest
from vocode.streaming.models.actions import ActionInput
from backend.actions.appointment_actions import (
    CheckAvailabilityAction,
    CheckAvailabilityActionConfig,
    CheckAvailabilityParams,
    BookAppointmentAction,
    BookAppointmentActionConfig,
    BookAppointmentParams,
    CancelAppointmentAction,
    CancelAppointmentActionConfig,
    CancelAppointmentParams,
)
from backend.tools import check_availability, book_appointment, cancel_appointment
from backend.db.repository import db_repository


def test_check_availability_slots():
    """Verify check_availability returns valid slots."""
    result = check_availability(date="tomorrow")
    assert result["status"] == "success"
    assert len(result["available_slots"]) > 0

    assert "tomorrow" in result["message"]


def test_book_and_cancel_appointment_lifecycle(sample_user):
    """Verify end-to-end booking and cancellation against isolated database."""
    user_id = sample_user["id"]

    # 1. Book appointment
    booked = book_appointment(
        name="John Doe",
        date="2026-11-01",
        time="10:00 AM",
        service="Dental Checkup",
        user_id=user_id,
    )
    assert booked["status"] == "confirmed"
    appt_id = booked["booking_id"]
    assert appt_id is not None

    # Verify stored in DB
    db_appt = db_repository.get_appointment_by_id(appt_id, user_id=user_id)
    assert db_appt is not None
    assert db_appt["status"] == "confirmed"
    assert db_appt["name"] == "John Doe"

    # 2. Cancel appointment
    cancelled = cancel_appointment(appt_id, user_id=user_id)
    assert cancelled["status"] == "cancelled"
    assert "successfully cancelled" in cancelled["message"]

    # Verify updated in DB
    updated_db_appt = db_repository.get_appointment_by_id(appt_id, user_id=user_id)
    assert updated_db_appt["status"] == "cancelled"

    # 3. Attempt to cancel non-existent appointment
    non_existent = cancel_appointment("NON-EXISTENT-ID-999", user_id=user_id)
    assert non_existent["status"] == "not_found"
    assert non_existent["appointment"] is None


def test_cancel_appointment_tenant_isolation(isolated_db):
    """Verify that User B cannot cancel User A's appointment."""
    u1 = db_repository.create_user("user_a@example.com", "user_a", "Pass1234!")
    u2 = db_repository.create_user("user_b@example.com", "user_b", "Pass5678!")

    # User A books an appointment
    booked = book_appointment(
        name="Alice Smith",
        date="2026-11-05",
        time="02:00 PM",
        service="Cardiology",
        user_id=u1["id"],
    )
    appt_id = booked["booking_id"]

    # User B attempts to cancel User A's appointment
    unauthorized_cancel = cancel_appointment(appt_id, user_id=u2["id"])
    assert unauthorized_cancel["status"] == "not_found"

    # Confirm appointment is still confirmed in DB for User A
    appt = db_repository.get_appointment_by_id(appt_id, user_id=u1["id"])
    assert appt["status"] == "confirmed"

    # User A can legitimately cancel their own appointment
    authorized_cancel = cancel_appointment(appt_id, user_id=u1["id"])
    assert authorized_cancel["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_appointment_action_execution(sample_user):
    """Verify Vocode CancelAppointmentAction executes smoothly through action runner."""
    user_id = sample_user["id"]

    # Pre-seed an appointment in DB
    booked = book_appointment(
        name="Bob Martin",
        date="2026-12-01",
        time="11:30 AM",
        service="General Consultation",
        user_id=user_id,
    )
    appt_id = booked["booking_id"]

    # Instantiate action
    action_cfg = CancelAppointmentActionConfig()
    action = CancelAppointmentAction(action_config=action_cfg)
    assert action.get_function_name() == "cancel_appointment"

    action_input = ActionInput(
        action_config=action_cfg,
        conversation_id="test_conv_cancel_1",
        params=CancelAppointmentParams(appointment_id=appt_id),
    )

    action_output = await action.run(action_input)
    assert action_output.response.status == "cancelled"
    assert "successfully cancelled" in action_output.response.message.lower()
