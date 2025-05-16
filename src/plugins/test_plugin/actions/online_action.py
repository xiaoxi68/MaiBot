from src.common.logger_manager import get_logger
from src.chat.focus_chat.planners.actions.plugin_action import PluginAction, register_action
from typing import Tuple

logger = get_logger("check_online_action")


@register_action
class CheckOnlineAction(PluginAction):
    """测试动作处理类"""

    action_name = "check_online_action"
    action_description = "这是一个检查在线状态的动作，当有人要求你检查Maibot（麦麦 机器人）在线状态时使用"
    action_parameters = {"mode": "查看模式"}
    action_require = [
        "当有人要求你检查Maibot（麦麦 机器人）在线状态时使用",
        "mode参数为version时查看在线版本状态，默认用这种",
        "mode参数为type时查看在线系统类型分布",
    ]
    default = True  # 不是默认动作，需要手动添加到使用集

    async def process(self) -> Tuple[bool, str]:
        """处理测试动作"""
        logger.info(f"{self.log_prefix} 执行online动作: {self.reasoning}")

        # 发送测试消息
        mode = self.action_data.get("mode", "type")

        await self.send_message_by_expressor("我看看")

        try:
            if mode == "type":
                await self.send_message("#online detail")
            elif mode == "version":
                await self.send_message("#online")

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行online动作时出错: {e}")
            await self.send_message_by_expressor("执行online动作时出错: {e}")

            return False, "执行online动作时出错"

        return True, "测试动作执行成功"
