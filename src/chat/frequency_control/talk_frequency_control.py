from typing import Optional
from datetime import datetime, timedelta
import statistics
from src.config.config import global_config
from src.chat.frequency_control.utils import parse_stream_config_to_chat_id
from src.common.database.database_model import Messages


def get_config_base_talk_frequency(chat_id: Optional[str] = None) -> float:
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


def get_weekly_hourly_message_stats(chat_id: str):
    """
    计算指定聊天最近一周每个小时的消息数量和用户数量
    
    Args:
        chat_id: 聊天ID（对应 Messages 表的 chat_id 字段）
    
    Returns:
        dict: 包含24个小时统计数据，格式为:
        {
            "0": {"message_count": [5, 8, 3, 12, 6, 9, 7], "message_std_dev": 2.1},
            "1": {"message_count": [10, 15, 8, 20, 12, 18, 14], "message_std_dev": 3.2},
            ...
        }
    """
    # 计算一周前的时间戳
    one_week_ago = datetime.now() - timedelta(days=7)
    one_week_ago_timestamp = one_week_ago.timestamp()
    
    # 初始化数据结构：按小时存储每天的消息计数
    hourly_data = {}
    for hour in range(24):
        hourly_data[f"hour_{hour}"] = {"daily_counts": []}
    
    try:
        # 查询指定聊天最近一周的消息
        messages = Messages.select().where(
            (Messages.time >= one_week_ago_timestamp) &
            (Messages.chat_id == chat_id)
        )
        
        # 统计每个小时的数据
        for message in messages:
            # 将时间戳转换为datetime
            msg_time = datetime.fromtimestamp(message.time)
            hour = msg_time.hour
            
            # 记录每天的消息计数（按日期分组）
            day_key = msg_time.strftime("%Y-%m-%d")
            hour_key = f"{hour}"
            
            # 为该小时添加当天的消息计数
            found = False
            for day_count in hourly_data[hour_key]["daily_counts"]:
                if day_count["date"] == day_key:
                    day_count["count"] += 1
                    found = True
                    break
            
            if not found:
                hourly_data[hour_key]["daily_counts"].append({"date": day_key, "count": 1})
            
                  
    except Exception as e:
        # 如果查询失败，返回空的统计结果
        print(f"Error getting weekly hourly message stats for chat {chat_id}: {e}")
        hourly_stats = {}
        for hour in range(24):
            hourly_stats[f"hour_{hour}"] = {
                "message_count": [],
                "message_std_dev": 0.0
            }
        return hourly_stats
    
    # 计算每个小时的统计结果
    hourly_stats = {}
    for hour in range(24):
        hour_key = f"hour_{hour}"
        daily_counts = [day["count"] for day in hourly_data[hour_key]["daily_counts"]]
        
        # 计算总消息数
        total_messages = sum(daily_counts)
        
        # 计算标准差
        message_std_dev = 0.0
        if len(daily_counts) > 1:
            message_std_dev = statistics.stdev(daily_counts)
        elif len(daily_counts) == 1:
            message_std_dev = 0.0
        
        # 按日期排序每日消息计数
        daily_counts_sorted = sorted(hourly_data[hour_key]["daily_counts"], key=lambda x: x["date"])
        
        hourly_stats[hour_key] = {
            "message_count": [day["count"] for day in daily_counts_sorted],
            "message_std_dev": message_std_dev
        }
    
    return hourly_stats

def get_recent_15min_stats(chat_id: str):
    """
    获取最近15分钟指定聊天的消息数量和发言人数
    
    Args:
        chat_id: 聊天ID（对应 Messages 表的 chat_id 字段）
    
    Returns:
        dict: 包含消息数量和发言人数，格式为:
        {
            "message_count": 25,
            "user_count": 8,
            "time_range": "2025-01-01 14:30:00 - 2025-01-01 14:45:00"
        }
    """
    # 计算15分钟前的时间戳
    fifteen_min_ago = datetime.now() - timedelta(minutes=15)
    fifteen_min_ago_timestamp = fifteen_min_ago.timestamp()
    current_time = datetime.now()
    
    # 初始化统计结果
    message_count = 0
    user_set = set()
    
    try:
        # 查询最近15分钟的消息
        messages = Messages.select().where(
            (Messages.time >= fifteen_min_ago_timestamp) &
            (Messages.chat_id == chat_id)
        )
        
        # 统计消息数量和用户
        for message in messages:
            message_count += 1
            if message.user_id:
                user_set.add(message.user_id)
                
    except Exception as e:
        # 如果查询失败，返回空结果
        print(f"Error getting recent 15min stats for chat {chat_id}: {e}")
        return {
            "message_count": 0,
            "user_count": 0,
            "time_range": f"{fifteen_min_ago.strftime('%Y-%m-%d %H:%M:%S')} - {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
        }
    
    return {
        "message_count": message_count,
        "user_count": len(user_set),
        "time_range": f"{fifteen_min_ago.strftime('%Y-%m-%d %H:%M:%S')} - {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
    }
