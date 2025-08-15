from typing import Optional
from src.config.config import global_config
from src.chat.frequency_control.utils import parse_stream_config_to_chat_id

class TalkFrequencyControl:
    def __init__(self,chat_id:str):
        self.chat_id = chat_id
        self.talk_frequency_adjust = 1
        
    def get_current_talk_frequency(self) -> float:
        return get_current_talk_frequency(self.chat_id) * self.talk_frequency_adjust
        

class TalkFrequencyControlManager:
    def __init__(self):
        self.talk_frequency_controls = {}
        
    def get_talk_frequency_control(self,chat_id:str) -> TalkFrequencyControl:
        if chat_id not in self.talk_frequency_controls:
            self.talk_frequency_controls[chat_id] = TalkFrequencyControl(chat_id)
        return self.talk_frequency_controls[chat_id]


def get_current_talk_frequency(chat_id: Optional[str] = None) -> float:
    """
    根据当前时间和聊天流获取对应的 talk_frequency

    Args:
        chat_stream_id: 聊天流ID，格式为 "platform:chat_id:type"

    Returns:
        float: 对应的频率值
    """
    if not global_config.chat.talk_frequency_adjust:
        return global_config.chat.talk_frequency

    # 优先检查聊天流特定的配置
    if chat_id:
        stream_frequency = get_stream_specific_frequency(chat_id)
        if stream_frequency is not None:
            return stream_frequency

    # 检查全局时段配置（第一个元素为空字符串的配置）
    global_frequency = get_global_frequency()
    return global_config.chat.talk_frequency if global_frequency is None else global_frequency

def get_time_based_frequency(time_freq_list: list[str]) -> Optional[float]:
    """
    根据时间配置列表获取当前时段的频率

    Args:
        time_freq_list: 时间频率配置列表，格式为 ["HH:MM,frequency", ...]

    Returns:
        float: 频率值，如果没有配置则返回 None
    """
    from datetime import datetime

    current_time = datetime.now().strftime("%H:%M")
    current_hour, current_minute = map(int, current_time.split(":"))
    current_minutes = current_hour * 60 + current_minute

    # 解析时间频率配置
    time_freq_pairs = []
    for time_freq_str in time_freq_list:
        try:
            time_str, freq_str = time_freq_str.split(",")
            hour, minute = map(int, time_str.split(":"))
            frequency = float(freq_str)
            minutes = hour * 60 + minute
            time_freq_pairs.append((minutes, frequency))
        except (ValueError, IndexError):
            continue

    if not time_freq_pairs:
        return None

    # 按时间排序
    time_freq_pairs.sort(key=lambda x: x[0])

    # 查找当前时间对应的频率
    current_frequency = None
    for minutes, frequency in time_freq_pairs:
        if current_minutes >= minutes:
            current_frequency = frequency
        else:
            break

    # 如果当前时间在所有配置时间之前，使用最后一个时间段的频率（跨天逻辑）
    if current_frequency is None and time_freq_pairs:
        current_frequency = time_freq_pairs[-1][1]

    return current_frequency


def get_stream_specific_frequency(chat_stream_id: str):
    """
    获取特定聊天流在当前时间的频率

    Args:
        chat_stream_id: 聊天流ID（哈希值）

    Returns:
        float: 频率值，如果没有配置则返回 None
    """
    # 查找匹配的聊天流配置
    for config_item in global_config.chat.talk_frequency_adjust:
        if not config_item or len(config_item) < 2:
            continue

        stream_config_str = config_item[0]  # 例如 "qq:1026294844:group"

        # 解析配置字符串并生成对应的 chat_id
        config_chat_id = parse_stream_config_to_chat_id(stream_config_str)
        if config_chat_id is None:
            continue

        # 比较生成的 chat_id
        if config_chat_id != chat_stream_id:
            continue

        # 使用通用的时间频率解析方法
        return get_time_based_frequency(config_item[1:])

    return None

def get_global_frequency() -> Optional[float]:
    """
    获取全局默认频率配置

    Returns:
        float: 频率值，如果没有配置则返回 None
    """
    for config_item in global_config.chat.talk_frequency_adjust:
        if not config_item or len(config_item) < 2:
            continue

        # 检查是否为全局默认配置（第一个元素为空字符串）
        if config_item[0] == "":
            return get_time_based_frequency(config_item[1:])

    return None

talk_frequency_control = TalkFrequencyControlManager()