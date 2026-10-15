"""
Automated unit and integration test suite for appointment actions:
- check_availability
- book_appointment
- cancel_appointment
- Multi-tenant appointment isolation
- Vocode CancelAppointmentAction execution
"""
import datetime
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
from backend.tools import (
    check_availability,
    book_appointment,
    cancel_appointment,
    normalize_date,
    normalize_time,
)
from backend.db.repository import db_repository
from backend.agent_factory import get_temporal_grounding_instruction, create_agent


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


def test_normalize_date_relative_keywords():
    """Verify deterministic parsing of relative keywords given a reference date."""
    base = datetime.date(2026, 10, 15)  # Thursday
    assert normalize_date("today", base_date=base) == "2026-10-15"
    assert normalize_date("tomorrow", base_date=base) == "2026-10-16"
    assert normalize_date("tmrw", base_date=base) == "2026-10-16"
    assert normalize_date("day after tomorrow", base_date=base) == "2026-10-17"
    assert normalize_date("yesterday", base_date=base) == "2026-10-14"


def test_normalize_date_weekdays():
    """Verify conversion of weekday mentions into upcoming ISO dates."""
    base = datetime.date(2026, 10, 15)  # Thursday
    # Friday is tomorrow (1 day ahead)
    assert normalize_date("friday", base_date=base) == "2026-10-16"
    assert normalize_date("this friday", base_date=base) == "2026-10-16"
    # Monday is 4 days ahead
    assert normalize_date("monday", base_date=base) == "2026-10-19"
    # Same weekday without 'next' returns today
    assert normalize_date("thursday", base_date=base) == "2026-10-15"
    # Same weekday with 'next' jumps 7 days
    assert normalize_date("next thursday", base_date=base) == "2026-10-22"


def test_normalize_date_formats():
    """Verify parsing of standard ISO, US slash, and verbal date strings."""
    base = datetime.date(2026, 10, 15)
    assert normalize_date("2026-11-20", base_date=base) == "2026-11-20"
    assert normalize_date("11/20/2026", base_date=base) == "2026-11-20"
    assert normalize_date("November 20th, 2026", base_date=base) == "2026-11-20"
    assert normalize_date("Nov 20, 2026", base_date=base) == "2026-11-20"
    assert normalize_date("November 20", base_date=base) == "2026-11-20"


def test_normalize_time():
    """Verify normalization of various 12-hour and 24-hour time expressions."""
    assert normalize_time("2pm") == "02:00 PM"
    assert normalize_time("2 pm") == "02:00 PM"
    assert normalize_time("02:00 PM") == "02:00 PM"
    assert normalize_time("2:30 pm") == "02:30 PM"
    assert normalize_time("9am") == "09:00 AM"
    assert normalize_time("09:00") == "09:00 AM"
    assert normalize_time("14:00") == "02:00 PM"
    assert normalize_time("16:30") == "04:30 PM"
    assert normalize_time("12:00 PM") == "12:00 PM"
    assert normalize_time("12:00 AM") == "12:00 AM"


def test_cross_matching_booking_and_availability_conflict(sample_user):
    """
    Verify cross-matching: Booking with ISO date '2026-10-16' correctly
    blocks availability when queried with relative date 'tomorrow',
    and detects conflict when another user attempts to book the same slot.
    """
    user_id = sample_user["id"]
    base = datetime.date(2026, 10, 15)  # Tomorrow is 2026-10-16

    # 1. Book an appointment using ISO date and colloquial time
    booked = book_appointment(
        name="Alice Walker",
        date="2026-10-16",
        time="2pm",
        service="Consultation",
        user_id=user_id,
        base_date=base,
    )
    assert booked["status"] == "confirmed"
    assert booked["appointment"]["date"] == "2026-10-16"
    assert booked["appointment"]["time"] == "02:00 PM"

    # 2. Check availability using relative date "tomorrow"
    avail = check_availability(date="tomorrow", base_date=base)
    assert avail["status"] == "success"
    assert avail["normalized_date"] == "2026-10-16"
    assert "02:00 PM" in avail["booked_slots"]
    assert "02:00 PM" not in avail["available_slots"]
    assert "09:00 AM" in avail["available_slots"]

    # 3. Attempt booking the same slot using relative date and standard time
    conflict = book_appointment(
        name="Bob Stone",
        date="tomorrow",
        time="02:00 PM",
        service="Consultation",
        user_id=user_id,
        base_date=base,
    )
    assert conflict["status"] == "conflict"
    assert conflict["booking_id"] is None
    assert "already booked" in conflict["summary"].lower()


def test_temporal_grounding_instruction():
    """Verify temporal grounding prompt generation and injection into agent preamble."""
    fixed_dt = datetime.datetime(2026, 10, 15, 14, 30)
    instruction = get_temporal_grounding_instruction(user_timezone="UTC", current_time=fixed_dt)
    assert "Thursday, October 15, 2026" in instruction
    assert "2026-10-15" in instruction
    assert "02:30 PM" in instruction
    assert "Temporal Grounding:" in instruction

    agent = create_agent(persona_key="concierge")
    if hasattr(agent, "agent_config"):
        preamble = agent.agent_config.prompt_preamble
        assert "Temporal Grounding:" in preamble

