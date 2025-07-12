import time
from typing import Optional
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.message_receive.message import UserInfo
from src.common.logger import get_logger
from typing import Dict, Any
from src.config.config import global_config
from src.chat.message_receive.message import MessageThinking
from src.chat.message_receive.normal_message_sender import message_manager
from src.common.message_repository import count_messages



logger = get_logger(__name__)


class CycleDetail:
    """循环信息记录类"""

    def __init__(self, cycle_id: int):
        self.cycle_id = cycle_id
        self.thinking_id = ""
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.timers: Dict[str, float] = {}

        self.loop_plan_info: Dict[str, Any] = {}
        self.loop_action_info: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        """将循环信息转换为字典格式"""

        def convert_to_serializable(obj, depth=0, seen=None):
            if seen is None:
                seen = set()

            # 防止递归过深
            if depth > 5:  # 降低递归深度限制
                return str(obj)

            # 防止循环引用
            obj_id = id(obj)
            if obj_id in seen:
                return str(obj)
            seen.add(obj_id)

            try:
                if hasattr(obj, "to_dict"):
                    # 对于有to_dict方法的对象，直接调用其to_dict方法
                    return obj.to_dict()
                elif isinstance(obj, dict):
                    # 对于字典，只保留基本类型和可序列化的值
                    return {
                        k: convert_to_serializable(v, depth + 1, seen)
                        for k, v in obj.items()
                        if isinstance(k, (str, int, float, bool))
                    }
                elif isinstance(obj, (list, tuple)):
                    # 对于列表和元组，只保留可序列化的元素
                    return [
                        convert_to_serializable(item, depth + 1, seen)
                        for item in obj
                        if not isinstance(item, (dict, list, tuple))
                        or isinstance(item, (str, int, float, bool, type(None)))
                    ]
                elif isinstance(obj, (str, int, float, bool, type(None))):
                    return obj
                else:
                    return str(obj)
            finally:
                seen.remove(obj_id)

        return {
            "cycle_id": self.cycle_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "timers": self.timers,
            "thinking_id": self.thinking_id,
            "loop_plan_info": convert_to_serializable(self.loop_plan_info),
            "loop_action_info": convert_to_serializable(self.loop_action_info),
        }

    def set_loop_info(self, loop_info: Dict[str, Any]):
        """设置循环信息"""
        self.loop_plan_info = loop_info["loop_plan_info"]
        self.loop_action_info = loop_info["loop_action_info"]


async def create_thinking_message_from_dict(message_data: dict, chat_stream: ChatStream, thinking_id: str) -> str:
    """创建思考消息"""
    bot_user_info = UserInfo(
        user_id=global_config.bot.qq_account,
        user_nickname=global_config.bot.nickname,
        platform=message_data.get("chat_info_platform"),
    )

    thinking_message = MessageThinking(
        message_id=thinking_id,
        chat_stream=chat_stream,
        bot_user_info=bot_user_info,
        reply=None,
        thinking_start_time=time.time(),
        timestamp=time.time(),
    )

    await message_manager.add_message(thinking_message)
    return thinking_id

async def cleanup_thinking_message_by_id(chat_id: str, thinking_id: str, log_prefix: str):
    """根据ID清理思考消息"""
    try:
        container = await message_manager.get_container(chat_id)
        if container:
            for msg in container.messages[:]:
                if isinstance(msg, MessageThinking) and msg.message_info.message_id == thinking_id:
                    container.messages.remove(msg)
                    logger.info(f"{log_prefix}已清理思考消息 {thinking_id}")
                    break
    except Exception as e:
        logger.error(f"{log_prefix} 清理思考消息 {thinking_id} 时出错: {e}")

    
    
def get_recent_message_stats(minutes: int = 30, chat_id: str = None) -> dict:
    """
    Args:
        minutes (int): 检索的分钟数，默认30分钟
        chat_id (str, optional): 指定的chat_id，仅统计该chat下的消息。为None时统计全部。
    Returns:
        dict: {"bot_reply_count": int, "total_message_count": int}
    """

    now = time.time()
    start_time = now - minutes * 60
    bot_id = global_config.bot.qq_account

    filter_base = {"time": {"$gte": start_time}}
    if chat_id is not None:
        filter_base["chat_id"] = chat_id

    # 总消息数
    total_message_count = count_messages(filter_base)
    # bot自身回复数
    bot_filter = filter_base.copy()
    bot_filter["user_id"] = bot_id
    bot_reply_count = count_messages(bot_filter)

    return {"bot_reply_count": bot_reply_count, "total_message_count": total_message_count}
