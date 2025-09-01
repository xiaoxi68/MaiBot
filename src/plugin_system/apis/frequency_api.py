from src.common.logger import get_logger
from src.chat.frequency_control.frequency_control import frequency_control_manager

logger = get_logger("frequency_api")


def get_current_focus_value(chat_id: str) -> float:
    return frequency_control_manager.get_or_create_frequency_control(chat_id).get_final_focus_value()

def get_current_talk_frequency(chat_id: str) -> float:
    return frequency_control_manager.get_or_create_frequency_control(chat_id).get_final_talk_frequency()

def set_focus_value_adjust(chat_id: str, focus_value_adjust: float) -> None:
    frequency_control_manager.get_or_create_frequency_control(chat_id).focus_value_external_adjust = focus_value_adjust
    
def set_talk_frequency_adjust(chat_id: str, talk_frequency_adjust: float) -> None:
    frequency_control_manager.get_or_create_frequency_control(chat_id).talk_frequency_external_adjust = talk_frequency_adjust

def get_focus_value_adjust(chat_id: str) -> float:
    return frequency_control_manager.get_or_create_frequency_control(chat_id).focus_value_external_adjust
    
def get_talk_frequency_adjust(chat_id: str) -> float:
    return frequency_control_manager.get_or_create_frequency_control(chat_id).talk_frequency_external_adjust





