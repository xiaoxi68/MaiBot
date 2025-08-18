from typing import Optional
from src.config.config import global_config
from src.chat.frequency_control.utils import parse_stream_config_to_chat_id


class FocusValueControl:
    def __init__(self,chat_id:str):
        self.chat_id = chat_id
        self.focus_value_adjust = 1
        
        
    def get_current_focus_value(self) -> float:
        return get_current_focus_value(self.chat_id) * self.focus_value_adjust
        

class FocusValueControlManager:
    def __init__(self):
        self.focus_value_controls = {}
        
    def get_focus_value_control(self,chat_id:str) -> FocusValueControl:
        if chat_id not in self.focus_value_controls:
            self.focus_value_controls[chat_id] = FocusValueControl(chat_id)
        return self.focus_value_controls[chat_id]



def get_current_focus_value(chat_id: Optional[str] = None) -> float:
    """
    根据当前时间和聊天流获取对应的 focus_value
    """
    if not global_config.chat.focus_value_adjust:
        return global_config.chat.focus_value
    
    if chat_id:
        stream_focus_value = get_stream_specific_focus_value(chat_id)
        if stream_focus_value is not None:
            return stream_focus_value
        
    global_focus_value = get_global_focus_value()
    if global_focus_value is not None:
        return global_focus_value
    
    return global_config.chat.focus_value

def get_stream_specific_focus_value(chat_id: str) -> Optional[float]:
    """
    获取特定聊天流在当前时间的专注度

    Args:
        chat_stream_id: 聊天流ID（哈希值）

    Returns:
        float: 专注度值，如果没有配置则返回 None
    """
    # 查找匹配的聊天流配置
    for config_item in global_config.chat.focus_value_adjust:
        if not config_item or len(config_item) < 2:
            continue

        stream_config_str = config_item[0]  # 例如 "qq:1026294844:group"

        # 解析配置字符串并生成对应的 chat_id
        config_chat_id = parse_stream_config_to_chat_id(stream_config_str)
        if config_chat_id is None:
            continue

        # 比较生成的 chat_id
        if config_chat_id != chat_id:
            continue

        # 使用通用的时间专注度解析方法
        return get_time_based_focus_value(config_item[1:])

    return None


def get_time_based_focus_value(time_focus_list: list[str]) -> Optional[float]:
    """
    根据时间配置列表获取当前时段的专注度

    Args:
        time_focus_list: 时间专注度配置列表，格式为 ["HH:MM,focus_value", ...]

    Returns:
        float: 专注度值，如果没有配置则返回 None
    """
    from datetime import datetime

    current_time = datetime.now().strftime("%H:%M")
    current_hour, current_minute = map(int, current_time.split(":"))
    current_minutes = current_hour * 60 + current_minute

    # 解析时间专注度配置
    time_focus_pairs = []
    for time_focus_str in time_focus_list:
        try:
            time_str, focus_str = time_focus_str.split(",")
            hour, minute = map(int, time_str.split(":"))
            focus_value = float(focus_str)
            minutes = hour * 60 + minute
            time_focus_pairs.append((minutes, focus_value))
        except (ValueError, IndexError):
            continue

    if not time_focus_pairs:
        return None

    # 按时间排序
    time_focus_pairs.sort(key=lambda x: x[0])

    # 查找当前时间对应的专注度
    current_focus_value = None
    for minutes, focus_value in time_focus_pairs:
        if current_minutes >= minutes:
            current_focus_value = focus_value
        else:
            break

    # 如果当前时间在所有配置时间之前，使用最后一个时间段的专注度（跨天逻辑）
    if current_focus_value is None and time_focus_pairs:
        current_focus_value = time_focus_pairs[-1][1]

    return current_focus_value


def get_global_focus_value() -> Optional[float]:
    """
    获取全局默认专注度配置

    Returns:
        float: 专注度值，如果没有配置则返回 None
    """
    for config_item in global_config.chat.focus_value_adjust:
        if not config_item or len(config_item) < 2:
            continue

        # 检查是否为全局默认配置（第一个元素为空字符串）
        if config_item[0] == "":
            return get_time_based_focus_value(config_item[1:])

    return None

focus_value_control = FocusValueControlManager()