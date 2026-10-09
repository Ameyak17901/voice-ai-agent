import datetime
from typing import Dict, Any, List, Optional, Type
from loguru import logger
from pydantic.v1 import BaseModel, Field

from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.models.actions import ActionConfig, ActionInput, ActionOutput
from backend.tools import check_availability, book_appointment, get_company_info


# ==========================================
# 1. Check Availability Action
# ==========================================
class CheckAvailabilityActionConfig(ActionConfig, type="check_availability"):  # type: ignore
    pass


class CheckAvailabilityParams(BaseModel):
    date: str = Field(
        default="today",
        description="The target date to check available appointment slots for (e.g. 'today', 'tomorrow', or 'YYYY-MM-DD').",
    )


class CheckAvailabilityResponse(BaseModel):
    status: str
    date: str
    available_slots: List[str]
    message: str


class CheckAvailabilityAction(
    BaseAction[
        CheckAvailabilityActionConfig,
        CheckAvailabilityParams,
        CheckAvailabilityResponse,
    ]
):
    description: str = "Checks available appointment slots for a specified date (e.g., today, tomorrow, or a specific date)."
    parameters_type: Type[CheckAvailabilityParams] = CheckAvailabilityParams
    response_type: Type[CheckAvailabilityResponse] = CheckAvailabilityResponse

    def __init__(self, action_config: CheckAvailabilityActionConfig):
        super().__init__(
            action_config=action_config,
            quiet=False,
            should_respond="never",
            is_interruptible=True,
        )

    def get_function_name(self) -> str:
        return "check_availability"

    async def run(
        self, action_input: ActionInput[CheckAvailabilityParams]
    ) -> ActionOutput[CheckAvailabilityResponse]:
        date = action_input.params.date or "today"
        logger.info(f"[VOICE_ACTION: CHECK_AVAILABILITY] Querying available slots for date='{date}'")
        raw_result = check_availability(date=date)
        response = CheckAvailabilityResponse(
            status=raw_result.get("status", "success"),
            date=raw_result.get("date", date),
            available_slots=raw_result.get("available_slots", []),
            message=raw_result.get("message", ""),
        )
        logger.info(f"[VOICE_ACTION: CHECK_AVAILABILITY_SUCCESS] Available slots: {response.available_slots}")
        return ActionOutput(
            action_type=action_input.action_config.type,
            response=response,
        )


# ==========================================
# 2. Book Appointment Action
# ==========================================
class BookAppointmentActionConfig(ActionConfig, type="book_appointment"):  # type: ignore
    pass


class BookAppointmentParams(BaseModel):
    name: str = Field(..., description="The full name of the patient or caller booking the appointment.")
    date: str = Field(..., description="The date of the appointment (e.g. 'today', 'tomorrow', or 'YYYY-MM-DD').")
    time: str = Field(..., description="The preferred appointment time slot (e.g. '09:00 AM', '11:00 AM', '02:00 PM', '04:30 PM').")
    service: Optional[str] = Field(
        default="General Consultation",
        description="Type of consultation or service requested (e.g. 'Dental Cleaning', 'General Consultation', 'Admissions Tour').",
    )


class BookAppointmentResponse(BaseModel):
    status: str
    booking_id: str
    summary: str


class BookAppointmentAction(
    BaseAction[
        BookAppointmentActionConfig,
        BookAppointmentParams,
        BookAppointmentResponse,
    ]
):
    description: str = "Books and confirms an appointment when the user provides their name, date, time slot, and service."
    parameters_type: Type[BookAppointmentParams] = BookAppointmentParams
    response_type: Type[BookAppointmentResponse] = BookAppointmentResponse

    def __init__(self, action_config: BookAppointmentActionConfig):
        super().__init__(
            action_config=action_config,
            quiet=False,
            should_respond="never",
            is_interruptible=True,
        )

    def get_function_name(self) -> str:
        return "book_appointment"

    async def run(
        self, action_input: ActionInput[BookAppointmentParams]
    ) -> ActionOutput[BookAppointmentResponse]:
        params = action_input.params
        logger.info(
            f"[VOICE_ACTION: BOOK_APPOINTMENT] Attempting booking for name='{params.name}', "
            f"date='{params.date}', time='{params.time}', service='{params.service}'"
        )
        raw_result = book_appointment(
            name=params.name,
            date=params.date,
            time=params.time,
            service=params.service or "General Consultation",
            conversation_id=action_input.conversation_id,
        )
        response = BookAppointmentResponse(
            status=raw_result.get("status", "confirmed"),
            booking_id=raw_result.get("booking_id", "APPT-000"),
            summary=raw_result.get("summary", ""),
        )
        logger.info(f"[VOICE_ACTION: BOOK_APPOINTMENT_SUCCESS] Confirmed booking: {response.booking_id}")
        return ActionOutput(
            action_type=action_input.action_config.type,
            response=response,
        )


# ==========================================
# 3. Get Company Info Action
# ==========================================
class GetCompanyInfoActionConfig(ActionConfig, type="get_company_info"):  # type: ignore
    pass


class GetCompanyInfoParams(BaseModel):
    topic: Optional[str] = Field(
        default="overview",
        description="Specific topic requested: 'overview', 'services', 'hours', or 'location'.",
    )


class GetCompanyInfoResponse(BaseModel):
    name: str
    services: List[str]
    business_hours: str
    support_email: str
    location: str


class GetCompanyInfoAction(
    BaseAction[
        GetCompanyInfoActionConfig,
        GetCompanyInfoParams,
        GetCompanyInfoResponse,
    ]
):
    description: str = "Retrieves authoritative clinic or company information such as official business hours, supported services, and contact details."
    parameters_type: Type[GetCompanyInfoParams] = GetCompanyInfoParams
    response_type: Type[GetCompanyInfoResponse] = GetCompanyInfoResponse

    def __init__(self, action_config: GetCompanyInfoActionConfig):
        super().__init__(
            action_config=action_config,
            quiet=False,
            should_respond="never",
            is_interruptible=True,
        )

    def get_function_name(self) -> str:
        return "get_company_info"

    async def run(
        self, action_input: ActionInput[GetCompanyInfoParams]
    ) -> ActionOutput[GetCompanyInfoResponse]:
        logger.info("[VOICE_ACTION: GET_COMPANY_INFO] Fetching company knowledge base.")
        raw_result = get_company_info()
        response = GetCompanyInfoResponse(
            name=raw_result.get("name", "NovaVoice AI Systems"),
            services=raw_result.get("services", []),
            business_hours=raw_result.get("business_hours", ""),
            support_email=raw_result.get("support_email", ""),
            location=raw_result.get("location", ""),
        )
        return ActionOutput(
            action_type=action_input.action_config.type,
            response=response,
        )
