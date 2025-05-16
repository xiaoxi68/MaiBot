from src.common.logger_manager import get_logger
from src.chat.focus_chat.planners.actions.plugin_action import PluginAction, register_action
from typing import Tuple

logger = get_logger("test_action")


@register_action
class TestAction(PluginAction):
    """测试动作处理类"""

    action_name = "test_action"
    action_description = "这是一个测试动作，当有人要求你测试插件系统时使用"
    action_parameters = {"test_param": "测试参数（可选）"}
    action_require = [
        "测试情况下使用",
        "想测试插件动作加载时使用",
    ]
    default = False  # 不是默认动作，需要手动添加到使用集

    async def process(self) -> Tuple[bool, str]:
        """处理测试动作"""
        logger.info(f"{self.log_prefix} 执行测试动作: {self.reasoning}")

        # 获取聊天类型
        chat_type = self.get_chat_type()
        logger.info(f"{self.log_prefix} 当前聊天类型: {chat_type}")

        # 获取最近消息
        recent_messages = self.get_recent_messages(3)
        logger.info(f"{self.log_prefix} 最近3条消息: {recent_messages}")

        # 发送测试消息
        test_param = self.action_data.get("test_param", "默认参数")
        await self.send_message_by_expressor(f"测试动作执行成功，参数: {test_param}")

        return True, "测试动作执行成功"
