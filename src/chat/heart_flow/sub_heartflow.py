from rich.traceback import install

from src.common.logger import get_logger
from src.chat.message_receive.chat_stream import get_chat_manager
from src.chat.chat_loop.heartFC_chat import HeartFChatting
from src.chat.utils.utils import get_chat_type_and_target_info

logger = get_logger("sub_heartflow")

install(extra_lines=3)


class SubHeartflow:
    def __init__(
        self,
        subheartflow_id,
    ):
        """子心流初始化函数

        Args:
            subheartflow_id: 子心流唯一标识符
        """
        # 基础属性，两个值是一样的
        self.subheartflow_id = subheartflow_id
        self.chat_id = subheartflow_id

        self.is_group_chat, self.chat_target_info = get_chat_type_and_target_info(self.chat_id)
        self.log_prefix = get_chat_manager().get_stream_name(self.subheartflow_id) or self.subheartflow_id

        # focus模式退出冷却时间管理
        self.last_focus_exit_time: float = 0  # 上次退出focus模式的时间

        # 随便水群 normal_chat 和 认真水群 focus_chat 实例
        # CHAT模式激活 随便水群  FOCUS模式激活 认真水群
        self.heart_fc_instance: HeartFChatting = HeartFChatting(
            chat_id=self.subheartflow_id,
        )  # 该sub_heartflow的HeartFChatting实例

    async def initialize(self):
        """异步初始化方法，创建兴趣流并确定聊天类型"""
        await self.heart_fc_instance.start()
