"""
Tool integrations and persistence services for the Web Voice Copilot.
Integrates with SQLite via DBRepository for transactional state.
"""
import datetime
from typing import Dict, Any, List, Optional
from backend.db.repository import db_repository

# Standard default daily slot pool
ALL_DAILY_SLOTS = [
    "09:00 AM",
    "11:00 AM",
    "02:00 PM",
    "04:30 PM",
]


class _ScheduledAppointmentsProxy(list):
    """Backwards-compatible list interface that reads live from DBRepository."""
    def __iter__(self):
        return iter(db_repository.list_appointments())

    def __len__(self):
        return len(db_repository.list_appointments())

    def __getitem__(self, index):
        return db_repository.list_appointments()[index]

    def append(self, item):
        db_repository.create_appointment(
            name=item.get("name", "Unknown"),
            date=item.get("date", "today"),
            time=item.get("time", "09:00 AM"),
            service=item.get("service", "General Consultation"),
            conversation_id=item.get("conversation_id"),
        )


SCHEDULED_APPOINTMENTS = _ScheduledAppointmentsProxy()


def check_availability(date: str = "today") -> Dict[str, Any]:
    """
    Check available booking slots for a given date by dynamically cross-referencing
    persisted appointments in SQLite.
    """
    target_date = date.strip().lower()
    all_appts = db_repository.list_appointments()

    # Find slots already booked for target date
    booked_times = {
        a["time"].strip().upper()
        for a in all_appts
        if a["date"].strip().lower() == target_date and a["status"] == "confirmed"
    }

    available = [slot for slot in ALL_DAILY_SLOTS if slot.strip().upper() not in booked_times]
    if not available:
        msg = f"All appointment slots for {date} are currently fully booked."
    else:
        msg = f"Slots available for {date}: {', '.join(available)}."

    return {
        "status": "success",
        "date": date,
        "available_slots": available,
        "booked_slots": list(booked_times),
        "message": msg,
    }


def book_appointment(
    name: str,
    date: str,
    time: str,
    service: str = "General Consultation",
    conversation_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Persist an appointment booking into SQLite with duplicate-prevention.
    """
    target_date = date.strip().lower()
    target_time = time.strip().upper()

    # Check for slot collision
    existing = db_repository.list_appointments()
    is_taken = any(
        a["date"].strip().lower() == target_date
        and a["time"].strip().upper() == target_time
        and a["status"] == "confirmed"
        for a in existing
    )

    if is_taken:
        return {
            "status": "conflict",
            "booking_id": None,
            "summary": f"The slot {time} on {date} is unfortunately already booked. Please choose another time.",
        }

    appt = db_repository.create_appointment(
        name=name.strip(),
        date=date.strip(),
        time=time.strip(),
        service=service.strip() if service else "General Consultation",
        conversation_id=conversation_id,
        user_id=user_id,
    )

    return {
        "status": "confirmed",
        "booking_id": appt["id"],
        "summary": f"Appointment confirmed for {name} on {date} at {time} for {service}.",
        "appointment": appt,
    }


def get_company_info() -> Dict[str, Any]:
    """Returns basic company knowledge base details."""
    return {
        "name": "NovaVoice AI Systems",
        "services": [
            "AI Voice Receptionist",
            "Real-time Audio Streaming",
            "Automated Dispatch & Support"
        ],
        "business_hours": "Monday to Friday, 8:00 AM to 6:00 PM EST",
        "support_email": "support@novavoice.example.com",
        "location": "San Francisco, CA"
    }