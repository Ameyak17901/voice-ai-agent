"""
Cal.com API v2 Client for real-time slot lookups, booking creation, and cancellations.
Supports both modern 'username + eventTypeSlug' and legacy 'eventTypeId' workflows
as documented in official Cal.com v2 API specifications.
"""
import datetime
import re
from typing import Dict, Any, List, Optional
import httpx
from loguru import logger
from backend.config import settings


class CalComClient:
    """
    Async client for Cal.com API v2 with support for:
    - Slot querying by username + eventTypeSlug or eventTypeId
    - Confirmed booking creation
    - Booking cancellation
    - Graceful error handling and timeouts for real-time voice pipelines
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        event_type_id: Optional[int] = None,
        username: Optional[str] = None,
        event_slug: Optional[str] = None,
        base_url: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout_seconds: float = 4.0,
    ):
        self.api_key = api_key or settings.cal_com_api_key
        self.event_type_id = event_type_id or settings.cal_com_event_type_id
        self.username = username or settings.cal_com_username
        self.event_slug = event_slug or settings.cal_com_event_slug or "30min"
        self.base_url = (base_url or settings.cal_com_base_url or "https://api.cal.com/v2").rstrip("/")
        self.api_version = api_version or settings.cal_com_api_version or "2024-08-13"
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        """Checks if minimum credentials exist to query or book against Cal.com."""
        if getattr(self, "_is_configured_override", None) is not None:
            return self._is_configured_override
        has_key = bool(self.api_key)
        has_identifier = bool(self.event_type_id or (self.username and self.event_slug))
        return has_key and has_identifier

    @is_configured.setter
    def is_configured(self, value: bool) -> None:
        self._is_configured_override = value

    def _headers(self) -> Dict[str, str]:
        """Generates standard Cal.com v2 headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "cal-api-version": self.api_version,
            "Content-Type": "application/json",
        }

    async def get_available_slots(
        self,
        target_date: str,  # YYYY-MM-DD
        timezone: str = "UTC",
    ) -> List[str]:
        """
        Fetches live available slots for a target date from Cal.com API v2.
        Returns slots formatted as 12-hour strings ('09:00 AM', '02:00 PM').
        """
        if not self.is_configured:
            logger.debug("[CALCOM_CLIENT] Client is not configured. Skipping Cal.com slot fetch.")
            return []

        # In Cal.com v2, /v2/slots accepts either eventTypeId or username + eventTypeSlug
        params: Dict[str, Any] = {
            "start": f"{target_date}",
            "end": f"{target_date}",
            "timeZone": timezone,
        }

        if self.event_type_id:
            params["eventTypeId"] = self.event_type_id
        else:
            params["username"] = self.username
            params["eventTypeSlug"] = self.event_slug

        url = f"{self.base_url}/slots"
        logger.info(f"[CALCOM_CLIENT] Fetching available slots from {url} for date='{target_date}' (timezone='{timezone}')")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=self._headers(), params=params)
                if response.status_code != 200:
                    logger.warning(
                        f"[CALCOM_CLIENT] Slots API returned status={response.status_code}: {response.text[:200]}"
                    )
                    return []

                payload = response.json()
                raw_data = payload.get("data", {})

                # Cal.com v2 slots payload format:
                # {"data": {"slots": {"2026-10-18": [{"time": "2026-10-18T14:00:00Z"}, ...]}}}
                # or sometimes directly {"data": [{"time": ...}]}
                slots_dict = raw_data.get("slots", {}) if isinstance(raw_data, dict) else {}
                day_slots = slots_dict.get(target_date, []) if isinstance(slots_dict, dict) else []

                if not day_slots and isinstance(raw_data, list):
                    day_slots = raw_data

                formatted_slots: List[str] = []
                for item in day_slots:
                    iso_time = item.get("time") if isinstance(item, dict) else str(item)
                    if not iso_time:
                        continue
                    try:
                        # Normalize ISO string to datetime
                        clean_iso = iso_time.replace("Z", "+00:00")
                        dt = datetime.datetime.fromisoformat(clean_iso)
                        formatted_slots.append(dt.strftime("%I:%M %p"))
                    except Exception as parse_err:
                        logger.debug(f"[CALCOM_CLIENT] Could not parse slot '{iso_time}': {parse_err}")

                # Deduplicate and sort
                unique_slots = sorted(list(set(formatted_slots)), key=lambda s: datetime.datetime.strptime(s, "%I:%M %p"))
                logger.info(f"[CALCOM_CLIENT] Successfully retrieved {len(unique_slots)} slots from Cal.com for {target_date}")
                return unique_slots

        except httpx.RequestError as exc:
            logger.error(f"[CALCOM_CLIENT: NETWORK_ERROR] Failed connecting to Cal.com: {exc}")
            return []
        except Exception as exc:
            logger.error(f"[CALCOM_CLIENT: UNEXPECTED_ERROR] Error fetching slots: {exc}")
            return []

    async def create_booking(
        self,
        name: str,
        date: str,  # YYYY-MM-DD
        time: str,  # e.g. "02:00 PM"
        email: Optional[str] = None,
        timezone: str = "UTC",
        service: str = "General Consultation",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a confirmed booking in Cal.com and syncs to host's Google Calendar.
        """
        if not self.is_configured:
            raise RuntimeError("CalComClient is not configured with valid API key or event identifiers.")

        # Convert date and time to ISO-8601 string
        try:
            dt = datetime.datetime.strptime(f"{date.strip()} {time.strip()}", "%Y-%m-%d %I:%M %p")
            iso_start = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            iso_start = f"{date}T{time}Z"

        attendee_email = email or f"{re.sub(r'[^a-zA-Z0-9]', '.', name.strip().lower())}@guest.voice-agent.local"

        payload: Dict[str, Any] = {
            "start": iso_start,
            "attendee": {
                "name": name.strip(),
                "email": attendee_email,
                "timeZone": timezone,
            },
            "metadata": {
                "source": "Voice AI Receptionist",
                "service": service,
                "notes": notes or "Booked via NovaVoice AI Assistant",
            },
        }

        if self.event_type_id:
            payload["eventTypeId"] = self.event_type_id
        else:
            payload["username"] = self.username
            payload["eventTypeSlug"] = self.event_slug

        url = f"{self.base_url}/bookings"
        logger.info(f"[CALCOM_CLIENT] Creating booking on Cal.com: attendee='{name}', start='{iso_start}'")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds + 2.0) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                if response.status_code not in (200, 201):
                    logger.error(
                        f"[CALCOM_CLIENT] Booking creation failed with status={response.status_code}: {response.text}"
                    )
                    return {
                        "status": "conflict" if response.status_code == 409 else "error",
                        "booking_id": None,
                        "summary": f"Could not confirm booking on Cal.com (Status: {response.status_code}).",
                        "raw": response.text,
                    }

                res_json = response.json()
                data = res_json.get("data", {})
                booking_id = str(data.get("uid") or data.get("id") or "cal_confirmed")
                meeting_url = data.get("meetingUrl") or data.get("location")

                logger.info(f"[CALCOM_CLIENT] Booking successfully created: UID='{booking_id}', Meet='{meeting_url}'")
                return {
                    "status": "confirmed",
                    "booking_id": booking_id,
                    "meeting_url": meeting_url,
                    "summary": f"Appointment confirmed on Cal.com for {name} on {date} at {time}.",
                    "data": data,
                }

        except httpx.RequestError as exc:
            logger.error(f"[CALCOM_CLIENT: NETWORK_ERROR] Failed during booking creation: {exc}")
            return {
                "status": "error",
                "booking_id": None,
                "summary": f"Network error communicating with Cal.com: {exc}",
            }

    async def cancel_booking(
        self,
        booking_uid: str,
        reason: str = "Cancelled by caller via Voice AI Receptionist",
    ) -> Dict[str, Any]:
        """
        Cancels an existing booking on Cal.com using POST /v2/bookings/{bookingUid}/cancel.
        """
        if not self.api_key:
            return {
                "status": "error",
                "message": "Cal.com API key is not configured.",
            }

        url = f"{self.base_url}/bookings/{booking_uid}/cancel"
        payload = {"cancellationReason": reason}
        logger.info(f"[CALCOM_CLIENT] Requesting cancellation for booking '{booking_uid}'")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                if response.status_code in (200, 204):
                    logger.info(f"[CALCOM_CLIENT] Successfully cancelled booking '{booking_uid}' on Cal.com")
                    return {
                        "status": "cancelled",
                        "message": f"Appointment '{booking_uid}' has been cancelled on Cal.com.",
                    }
                else:
                    logger.warning(
                        f"[CALCOM_CLIENT] Cancel booking returned status={response.status_code}: {response.text}"
                    )
                    return {
                        "status": "error",
                        "message": f"Failed to cancel Cal.com booking (status {response.status_code}).",
                    }
        except Exception as exc:
            logger.error(f"[CALCOM_CLIENT] Error cancelling Cal.com booking: {exc}")
            return {
                "status": "error",
                "message": f"Error communicating with Cal.com cancellation service: {exc}",
            }


calcom_client = CalComClient()
