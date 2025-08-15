from src.common.logger import get_logger
from src.chat.frequency_control.focus_value_control import FocusValueControlManager
from src.chat.frequency_control.talk_frequency_control import TalkFrequencyControlManager

logger = get_logger("frequency_api")


def get_current_focus_value(chat_id: str) -> float:
    return FocusValueControlManager().get_focus_value_control(chat_id).get_current_focus_value()

def get_current_talk_frequency(chat_id: str) -> float:
    return TalkFrequencyControlManager().get_talk_frequency_control(chat_id).get_current_talk_frequency()

def set_focus_value_adjust(chat_id: str, focus_value_adjust: float) -> None:
    FocusValueControlManager().get_focus_value_control(chat_id).focus_value_adjust = focus_value_adjust
    
def set_talk_frequency_adjust(chat_id: str, talk_frequency_adjust: float) -> None:
    TalkFrequencyControlManager().get_talk_frequency_control(chat_id).talk_frequency_adjust = talk_frequency_adjust

def get_focus_value_adjust(chat_id: str) -> float:
    return FocusValueControlManager().get_focus_value_control(chat_id).focus_value_adjust
    
def get_talk_frequency_adjust(chat_id: str) -> float:
    return TalkFrequencyControlManager().get_talk_frequency_control(chat_id).talk_frequency_adjust





