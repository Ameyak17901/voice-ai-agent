from typing import Dict, Sequence, Type, Union
from loguru import logger

from vocode.streaming.action.abstract_factory import AbstractActionFactory
from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.action.default_factory import CONVERSATION_ACTIONS
from vocode.streaming.models.actions import ActionConfig

from backend.actions.appointment_actions import (
    CheckAvailabilityAction,
    CheckAvailabilityActionConfig,
    BookAppointmentAction,
    BookAppointmentActionConfig,
    GetCompanyInfoAction,
    GetCompanyInfoActionConfig,
)

CUSTOM_ACTIONS: Dict[str, Type[BaseAction]] = {
    "check_availability": CheckAvailabilityAction,
    "book_appointment": BookAppointmentAction,
    "get_company_info": GetCompanyInfoAction,
}


class CustomActionFactory(AbstractActionFactory):
    """
    Action factory that combines Vocode standard actions with custom
    application actions (calendar, booking, knowledge lookups).
    """

    def __init__(self, actions: Sequence[ActionConfig] | dict = ()):
        self.action_configs_dict = {action.type: action for action in actions}
        self.actions = {**CONVERSATION_ACTIONS, **CUSTOM_ACTIONS}

    def create_action(self, action_config: ActionConfig) -> BaseAction:
        action_type = action_config.type
        action_class = self.actions.get(action_type)
        if not action_class:
            logger.error(f"Action type '{action_type}' not found in registry. Supported: {list(self.actions.keys())}")
            raise ValueError(f"Action type '{action_type}' not supported by Agent config.")
        return action_class(action_config)
