import time
from typing import Optional
from src.chat.message_receive.message import MessageRecv, BaseMessageInfo
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.message_receive.message import UserInfo
from src.common.logger import get_logger
import json
import os
from typing import Dict, Any

logger = get_logger(__name__)

log_dir = "log/log_cycle_debug/"


class CycleDetail:
    """循环信息记录类"""

    def __init__(self, cycle_id: int):
        self.cycle_id = cycle_id
        self.prefix = ""
        self.thinking_id = ""
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.timers: Dict[str, float] = {}

        # 新字段
        self.loop_observation_info: Dict[str, Any] = {}
        self.loop_processor_info: Dict[str, Any] = {}  # 前处理器信息
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
            "loop_observation_info": convert_to_serializable(self.loop_observation_info),
            "loop_processor_info": convert_to_serializable(self.loop_processor_info),
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

        # current_time_minute = time.strftime("%Y%m%d_%H%M", time.localtime())

        # try:
        #     self.log_cycle_to_file(
        #         log_dir + self.prefix + f"/{current_time_minute}_cycle_" + str(self.cycle_id) + ".json"
        #     )
        # except Exception as e:
        #     logger.warning(f"写入文件日志，可能是群名称包含非法字符: {e}")

    def log_cycle_to_file(self, file_path: str):
        """将循环信息写入文件"""
        # 如果目录不存在，则创建目
        dir_name = os.path.dirname(file_path)
        # 去除特殊字符，保留字母、数字、下划线、中划线和中文
        dir_name = "".join(
            char for char in dir_name if char.isalnum() or char in ["_", "-", "/"] or "\u4e00" <= char <= "\u9fff"
        )
        # print("dir_name:", dir_name)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        # 写入文件

        file_path = os.path.join(dir_name, os.path.basename(file_path))
        # print("file_path:", file_path)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")

    def set_thinking_id(self, thinking_id: str):
        """设置思考消息ID"""
        self.thinking_id = thinking_id

    def set_loop_info(self, loop_info: Dict[str, Any]):
        """设置循环信息"""
        self.loop_observation_info = loop_info["loop_observation_info"]
        self.loop_processor_info = loop_info["loop_processor_info"]
        self.loop_plan_info = loop_info["loop_plan_info"]
        self.loop_action_info = loop_info["loop_action_info"]



async def create_empty_anchor_message(
    platform: str, group_info: dict, chat_stream: ChatStream
) -> Optional[MessageRecv]:
    """
    重构观察到的最后一条消息作为回复的锚点，
    如果重构失败或观察为空，则创建一个占位符。
    """

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

    return anchor_message


def parse_thinking_id_to_timestamp(thinking_id: str) -> float:
    """
    将形如 'tid<timestamp>' 的 thinking_id 解析回 float 时间戳
    例如: 'tid1718251234.56' -> 1718251234.56
    """
    if not thinking_id.startswith("tid"):
        raise ValueError("thinking_id 格式不正确")
    ts_str = thinking_id[3:]
    return float(ts_str)


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
