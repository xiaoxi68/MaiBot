import time
import traceback
from typing import Optional
from src.chat.message_receive.message import MessageRecv, BaseMessageInfo
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.message_receive.message import UserInfo
from src.common.logger_manager import get_logger
import json

logger = get_logger(__name__)


async def _create_empty_anchor_message(
    platform: str, group_info: dict, chat_stream: ChatStream
) -> Optional[MessageRecv]:
    """
    重构观察到的最后一条消息作为回复的锚点，
    如果重构失败或观察为空，则创建一个占位符。
    """

    try:
        placeholder_id = f"mid_pf_{int(time.time() * 1000)}"
        placeholder_user = UserInfo(user_id="system_trigger", user_nickname="System Trigger", platform=platform)
        placeholder_msg_info = BaseMessageInfo(
            message_id=placeholder_id,
            platform=platform,
            group_info=group_info,
            user_info=placeholder_user,
            time=time.time(),
        )
        placeholder_msg_dict = {
            "message_info": placeholder_msg_info.to_dict(),
            "processed_plain_text": "[System Trigger Context]",
            "raw_message": "",
            "time": placeholder_msg_info.time,
        }
        anchor_message = MessageRecv(placeholder_msg_dict)
        anchor_message.update_chat_stream(chat_stream)
        logger.debug(f"创建占位符锚点消息: ID={anchor_message.message_info.message_id}")
        return anchor_message

    except Exception as e:
        logger.error(f"Error getting/creating anchor message: {e}")
        logger.error(traceback.format_exc())
        return None


def get_keywords_from_json(json_str: str) -> list[str]:
    # 提取JSON内容
    start = json_str.find("{")
    end = json_str.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("未找到有效的JSON内容")
        return []

    json_content = json_str[start:end]

    # 解析JSON
    try:
        json_data = json.loads(json_content)
        return json_data.get("keywords", [])
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        return []
