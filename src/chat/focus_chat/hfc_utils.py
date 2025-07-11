import time
from typing import Optional
from src.chat.message_receive.message import MessageRecv, BaseMessageInfo
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.message_receive.message import UserInfo
from src.common.logger import get_logger
import json
from typing import Dict, Any

logger = get_logger(__name__)


class CycleDetail:
    """循环信息记录类"""

    def __init__(self, cycle_id: int):
        self.cycle_id = cycle_id
        self.prefix = ""
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

    def complete_cycle(self):
        """完成循环，记录结束时间"""
        self.end_time = time.time()

        # 处理 prefix，只保留中英文字符和基本标点
        if not self.prefix:
            self.prefix = "group"
        else:
            # 只保留中文、英文字母、数字和基本标点
            allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
            self.prefix = (
                "".join(char for char in self.prefix if "\u4e00" <= char <= "\u9fff" or char in allowed_chars)
                or "group"
            )

    def set_thinking_id(self, thinking_id: str):
        """设置思考消息ID"""
        self.thinking_id = thinking_id

    def set_loop_info(self, loop_info: Dict[str, Any]):
        """设置循环信息"""
        self.loop_plan_info = loop_info["loop_plan_info"]
        self.loop_action_info = loop_info["loop_action_info"]



def parse_thinking_id_to_timestamp(thinking_id: str) -> float:
    """
    将形如 'tid<timestamp>' 的 thinking_id 解析回 float 时间戳
    例如: 'tid1718251234.56' -> 1718251234.56
    """
    if not thinking_id.startswith("tid"):
        raise ValueError("thinking_id 格式不正确")
    ts_str = thinking_id[3:]
    return float(ts_str)

