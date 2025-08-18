from typing import Optional
import hashlib


def parse_stream_config_to_chat_id(stream_config_str: str) -> Optional[str]:
    """
    解析流配置字符串并生成对应的 chat_id

    Args:
        stream_config_str: 格式为 "platform:id:type" 的字符串

    Returns:
        str: 生成的 chat_id，如果解析失败则返回 None
    """
    try:
        parts = stream_config_str.split(":")
        if len(parts) != 3:
            return None

        platform = parts[0]
        id_str = parts[1]
        stream_type = parts[2]

        # 判断是否为群聊
        is_group = stream_type == "group"

        # 使用与 ChatStream.get_stream_id 相同的逻辑生成 chat_id

        if is_group:
            components = [platform, str(id_str)]
        else:
            components = [platform, str(id_str), "private"]
        key = "_".join(components)
        return hashlib.md5(key.encode()).hexdigest()

    except (ValueError, IndexError):
        return None