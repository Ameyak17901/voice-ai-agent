"""
Tool integrations and mock action services for the Web Voice Copilot.
These simulate real business tools (Appointment booking, availability check, FAQ lookup).
"""
import datetime
from typing import Dict, Any, List

# In-memory mock appointment booking store
SCHEDULED_APPOINTMENTS: List[Dict[str, Any]] = []

AVAILABLE_SLOTS = [
    "09:00 AM",
    "11:00 AM",
    "02:00 PM",
    "04:30 PM",
]


def check_availability(date: str = "today") -> Dict[str, Any]:
    """Check available booking slots for a given date."""
    return {
        "status": "success",
        "date": date,
        "available_slots": AVAILABLE_SLOTS,
        "message": f"Slots available for {date}: {', '.join(AVAILABLE_SLOTS)}."
    }


def book_appointment(name: str, date: str, time: str, service: str = "General Consultation") -> Dict[str, Any]:
    """Book an appointment for a user."""
    booking_record = {
        "id": f"APPT-{len(SCHEDULED_APPOINTMENTS) + 101}",
        "name": name,
        "date": date,
        "time": time,
        "service": service,
        "created_at": datetime.datetime.now().isoformat()
    }
    SCHEDULED_APPOINTMENTS.append(booking_record)
    return {
        "status": "confirmed",
        "booking_id": booking_record["id"],
        "summary": f"Appointment confirmed for {name} on {date} at {time} for {service}."
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