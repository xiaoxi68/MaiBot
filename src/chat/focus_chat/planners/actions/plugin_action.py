import traceback
from typing import Tuple, Dict, List, Any, Optional
from src.chat.focus_chat.planners.actions.base_action import BaseAction
from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.focus_chat.hfc_utils import create_empty_anchor_message
from src.common.logger_manager import get_logger
from src.chat.person_info.person_info import person_info_manager
from abc import abstractmethod

logger = get_logger("plugin_action")


class PluginAction(BaseAction):
    """插件动作基类

    封装了主程序内部依赖，提供简化的API接口给插件开发者
    """

    def __init__(self, action_data: dict, reasoning: str, cycle_timers: dict, thinking_id: str, **kwargs):
        """初始化插件动作基类"""
        super().__init__(action_data, reasoning, cycle_timers, thinking_id)

        # 存储内部服务和对象引用
        self._services = {}

        # 从kwargs提取必要的内部服务
        if "observations" in kwargs:
            self._services["observations"] = kwargs["observations"]
        if "expressor" in kwargs:
            self._services["expressor"] = kwargs["expressor"]
        if "chat_stream" in kwargs:
            self._services["chat_stream"] = kwargs["chat_stream"]

        self.log_prefix = kwargs.get("log_prefix", "")

    async def get_user_id_by_person_name(self, person_name: str) -> Tuple[str, str]:
        """根据用户名获取用户ID"""
        person_id = person_info_manager.get_person_id_by_person_name(person_name)
        user_id = await person_info_manager.get_value(person_id, "user_id")
        platform = await person_info_manager.get_value(person_id, "platform")
        return platform, user_id

    # 提供简化的API方法
    async def send_message(self, text: str, target: Optional[str] = None) -> bool:
        """发送消息的简化方法

        Args:
            text: 要发送的消息文本
            target: 目标消息（可选）

        Returns:
            bool: 是否发送成功
        """
        try:
            expressor = self._services.get("expressor")
            chat_stream = self._services.get("chat_stream")

            if not expressor or not chat_stream:
                logger.error(f"{self.log_prefix} 无法发送消息：缺少必要的内部服务")
                return False

            # 构造简化的动作数据
            reply_data = {"text": text, "target": target or "", "emojis": []}

            # 获取锚定消息（如果有）
            observations = self._services.get("observations", [])

            chatting_observation: ChattingObservation = next(
                obs for obs in observations if isinstance(obs, ChattingObservation)
            )
            anchor_message = chatting_observation.search_message_by_text(reply_data["target"])

            # 如果没有找到锚点消息，创建一个占位符
            if not anchor_message:
                logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message.update_chat_stream(chat_stream)

            response_set = [
                ("text", text),
            ]

            # 调用内部方法发送消息
            success = await expressor.send_response_messages(
                anchor_message=anchor_message,
                response_set=response_set,
            )

            return success
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送消息时出错: {e}")
            traceback.print_exc()
            return False

    async def send_message_by_expressor(self, text: str, target: Optional[str] = None) -> bool:
        """发送消息的简化方法

        Args:
            text: 要发送的消息文本
            target: 目标消息（可选）

        Returns:
            bool: 是否发送成功
        """
        try:
            expressor = self._services.get("expressor")
            chat_stream = self._services.get("chat_stream")

            if not expressor or not chat_stream:
                logger.error(f"{self.log_prefix} 无法发送消息：缺少必要的内部服务")
                return False

            # 构造简化的动作数据
            reply_data = {"text": text, "target": target or "", "emojis": []}

            # 获取锚定消息（如果有）
            observations = self._services.get("observations", [])

            chatting_observation: ChattingObservation = next(
                obs for obs in observations if isinstance(obs, ChattingObservation)
            )
            anchor_message = chatting_observation.search_message_by_text(reply_data["target"])

            # 如果没有找到锚点消息，创建一个占位符
            if not anchor_message:
                logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message.update_chat_stream(chat_stream)

            # 调用内部方法发送消息
            success, _ = await expressor.deal_reply(
                cycle_timers=self.cycle_timers,
                action_data=reply_data,
                anchor_message=anchor_message,
                reasoning=self.reasoning,
                thinking_id=self.thinking_id,
            )

            return success
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送消息时出错: {e}")
            return False

    def get_chat_type(self) -> str:
        """获取当前聊天类型

        Returns:
            str: 聊天类型 ("group" 或 "private")
        """
        chat_stream = self._services.get("chat_stream")
        if chat_stream and hasattr(chat_stream, "group_info"):
            return "group" if chat_stream.group_info else "private"
        return "unknown"

    def get_recent_messages(self, count: int = 5) -> List[Dict[str, Any]]:
        """获取最近的消息

        Args:
            count: 要获取的消息数量

        Returns:
            List[Dict]: 消息列表，每个消息包含发送者、内容等信息
        """
        messages = []
        observations = self._services.get("observations", [])

        if observations and len(observations) > 0:
            obs = observations[0]
            if hasattr(obs, "get_talking_message"):
                raw_messages = obs.get_talking_message()
                # 转换为简化格式
                for msg in raw_messages[-count:]:
                    simple_msg = {
                        "sender": msg.get("sender", "未知"),
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp", 0),
                    }
                    messages.append(simple_msg)

        return messages

    @abstractmethod
    async def process(self) -> Tuple[bool, str]:
        """插件处理逻辑，子类必须实现此方法

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        pass

    async def handle_action(self) -> Tuple[bool, str]:
        """实现BaseAction的抽象方法，调用子类的process方法

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        return await self.process()
