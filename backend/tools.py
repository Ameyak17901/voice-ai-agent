"""
Tool integrations and persistence services for the Web Voice Copilot.
Integrates with SQLite via DBRepository for transactional state.
Includes deterministic temporal normalization for verbal, relative, and standard dates/times.
"""
import datetime
import re
from typing import Dict, Any, List, Optional
from backend.db.repository import db_repository

# Standard default daily slot pool
ALL_DAILY_SLOTS = [
    "09:00 AM",
    "11:00 AM",
    "02:00 PM",
    "04:30 PM",
]

_WEEKDAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


def normalize_date(date_str: str, base_date: Optional[datetime.date] = None) -> str:
    """
    Normalizes human verbal dates, relative dates, and standard date strings
    into ISO-8601 'YYYY-MM-DD' format.
    
    Supported formats:
    - Relative keywords: "today", "tomorrow", "day after tomorrow", "yesterday"
    - Weekdays: "monday", "this friday", "next tuesday", "coming wednesday"
    - ISO format: "2026-10-16", "2026/10/16"
    - Common formats: "10/16/2026", "10-16-2026", "October 16", "Oct 16, 2026", "16th October"
    """
    if not date_str or not isinstance(date_str, str):
        ref = base_date or datetime.date.today()
        return ref.isoformat()

    clean = date_str.strip().lower()
    ref = base_date or datetime.date.today()

    # 1. Relative keywords
    if clean in ("today", "current day", "this day"):
        return ref.isoformat()
    if clean in ("tomorrow", "tmrw"):
        return (ref + datetime.timedelta(days=1)).isoformat()
    if clean in ("day after tomorrow",):
        return (ref + datetime.timedelta(days=2)).isoformat()
    if clean in ("yesterday",):
        return (ref - datetime.timedelta(days=1)).isoformat()

    # 2. Weekday matching
    is_next = "next" in clean
    for wd_name, target_idx in _WEEKDAY_NAMES.items():
        if re.search(r"\b" + wd_name + r"\b", clean):
            current_idx = ref.weekday()
            diff = (target_idx - current_idx) % 7
            if diff == 0:
                days_ahead = 7 if is_next else 0
            else:
                days_ahead = diff
                if is_next and diff <= 3:
                    days_ahead += 7
            return (ref + datetime.timedelta(days=days_ahead)).isoformat()

    # 3. ISO-8601 YYYY-MM-DD or YYYY/MM/DD
    iso_match = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", clean)
    if iso_match:
        try:
            return datetime.date(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3))
            ).isoformat()
        except ValueError:
            pass

    # 4. Remove ordinal suffixes (1st, 2nd, 3rd, 4th, etc.)
    cleaned_ordinals = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", clean)

    # 5. Explicit date formats with year
    formats_with_year = [
        "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y",
        "%d %B %Y", "%d %b %Y",
    ]
    for fmt in formats_with_year:
        try:
            return datetime.datetime.strptime(cleaned_ordinals, fmt).date().isoformat()
        except ValueError:
            continue

    # 6. Formats without year (infer ref.year)
    formats_without_year = [
        "%B %d", "%b %d", "%d %B", "%d %b", "%m/%d", "%m-%d"
    ]
    for fmt in formats_without_year:
        try:
            parsed = datetime.datetime.strptime(cleaned_ordinals, fmt).date()
            res = parsed.replace(year=ref.year)
            # If date has already passed by more than 60 days, assume next year
            if (res - ref).days < -60:
                res = res.replace(year=ref.year + 1)
            return res.isoformat()
        except ValueError:
            continue

    # Fallback to sanitized input
    return clean.strip()


def normalize_time(time_str: str) -> str:
    """
    Normalizes time strings into standardized 12-hour format: 'HH:MM AM/PM'
    Examples:
    - '2pm', '2 PM', '2:00pm', '2:00 PM' -> '02:00 PM'
    - '9am', '9:30 AM', '09:00' -> '09:00 AM', '09:30 AM'
    - '14:00', '16:30' -> '02:00 PM', '04:30 PM'
    """
    if not time_str or not isinstance(time_str, str):
        return "09:00 AM"

    raw = time_str.strip().lower()

    # 1. 12-hour format with AM/PM (e.g. "2pm", "2:30 pm", "09:00am")
    ampm_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", raw)
    if ampm_match:
        hour = int(ampm_match.group(1))
        minute = int(ampm_match.group(2)) if ampm_match.group(2) else 0
        period = ampm_match.group(3).upper()
        if 1 <= hour <= 12 and 0 <= minute < 60:
            return f"{hour:02d}:{minute:02d} {period}"

    # 2. 24-hour format (e.g. "14:00", "09:30", "16:45", "9:00")
    h24_match = re.search(r"\b(\d{1,2}):(\d{2})\b", raw)
    if h24_match:
        hour = int(h24_match.group(1))
        minute = int(h24_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute < 60:
            if hour == 0:
                h12 = 12
                period = "AM"
            elif hour < 12:
                h12 = hour
                period = "AM"
            elif hour == 12:
                h12 = 12
                period = "PM"
            else:
                h12 = hour - 12
                period = "PM"
            return f"{h12:02d}:{minute:02d} {period}"

    # Fallback to uppercase
    return time_str.strip().upper()


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
            date=normalize_date(item.get("date", "today")),
            time=normalize_time(item.get("time", "09:00 AM")),
            service=item.get("service", "General Consultation"),
            conversation_id=item.get("conversation_id"),
        )


SCHEDULED_APPOINTMENTS = _ScheduledAppointmentsProxy()


def check_availability(
    date: str = "today",
    base_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Check available booking slots for a given date by dynamically cross-referencing
    persisted appointments in SQLite.
    Normalizes verbal, relative, and standard dates to guarantee accurate availability checks.
    """
    norm_target_date = normalize_date(date, base_date=base_date)
    all_appts = db_repository.list_appointments()

    # Find slots already booked for target date
    booked_times = {
        normalize_time(a["time"])
        for a in all_appts
        if normalize_date(a["date"], base_date=base_date) == norm_target_date and a["status"] == "confirmed"
    }

    available = [slot for slot in ALL_DAILY_SLOTS if normalize_time(slot) not in booked_times]
    if not available:
        msg = f"All appointment slots for {date} are currently fully booked."
    else:
        msg = f"Slots available for {date}: {', '.join(available)}."

    return {
        "status": "success",
        "date": date,
        "normalized_date": norm_target_date,
        "available_slots": available,
        "booked_slots": sorted(list(booked_times)),
        "message": msg,
    }


def book_appointment(
    name: str,
    date: str,
    time: str,
    service: str = "General Consultation",
    conversation_id: Optional[str] = None,
    user_id: Optional[int] = None,
    base_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Persist an appointment booking into SQLite with duplicate-prevention and date/time normalization.
    """
    norm_target_date = normalize_date(date, base_date=base_date)
    norm_target_time = normalize_time(time)

    # Check for slot collision across normalized dates and times
    existing = db_repository.list_appointments()
    is_taken = any(
        normalize_date(a["date"], base_date=base_date) == norm_target_date
        and normalize_time(a["time"]) == norm_target_time
        and a["status"] == "confirmed"
        for a in existing
    )

    if is_taken:
        return {
            "status": "conflict",
            "booking_id": None,
            "summary": f"The slot {norm_target_time} on {norm_target_date} is unfortunately already booked. Please choose another time.",
        }

    appt = db_repository.create_appointment(
        name=name.strip(),
        date=norm_target_date,
        time=norm_target_time,
        service=service.strip() if service else "General Consultation",
        conversation_id=conversation_id,
        user_id=user_id,
    )

    return {
        "status": "confirmed",
        "booking_id": appt["id"],
        "summary": f"Appointment confirmed for {name.strip()} on {norm_target_date} at {norm_target_time} for {appt['service']}.",
        "appointment": appt,
    }


def cancel_appointment(
    appointment_id: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Cancels a scheduled appointment and updates persistent storage."""
    result = db_repository.cancel_appointment(appointment_id, user_id=user_id)
    if not result:
        return {
            "status": "not_found",
            "message": f"Appointment with ID '{appointment_id}' was not found or could not be cancelled.",
            "appointment": None,
        }
    return {
        "status": "cancelled",
        "message": f"Appointment '{appointment_id}' has been successfully cancelled.",
        "appointment": result,
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