from src.common.logger_manager import get_logger
from src.chat.focus_chat.planners.actions.plugin_action import PluginAction, register_action
from typing import Tuple

logger = get_logger("mute_action")


@register_action
class MuteAction(PluginAction):
    """测试动作处理类"""

    action_name = "mute_action"
    action_description = (
        "如果某人违反了公序良俗，或者别人戳你太多，，或者某人刷屏，一定要禁言某人，如果你很生气，可以禁言某人"
    )
    action_parameters = {
        "target": "禁言对象，输入你要禁言的对象的名字，必填，",
        "duration": "禁言时长，输入你要禁言的时长，单位为秒，必填",
    }
    action_require = [
        "当有人违反了公序良俗时使用",
        "当有人刷屏时使用",
        "当有人要求禁言自己时使用",
        "当有人戳你两次以上时，防止刷屏，禁言他，必须牢记",
        "当千石可乐或可乐酱要求你禁言时使用",
        "当你想回避某个话题时使用",
    ]
    default = True  # 不是默认动作，需要手动添加到使用集

    async def process(self) -> Tuple[bool, str]:
        """处理测试动作"""
        logger.info(f"{self.log_prefix} 执行online动作: {self.reasoning}")

        # 发送测试消息
        target = self.action_data.get("target")
        duration = self.action_data.get("duration")
        reason = self.action_data.get("reason")
        platform, user_id = await self.get_user_id_by_person_name(target)

        await self.send_message_by_expressor(f"我要禁言{target}，{platform},时长{duration}秒，理由{reason}，表达情绪")

        try:
            await self.send_message(f"[command]mute,{user_id},{duration}")

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行mute动作时出错: {e}")
            await self.send_message_by_expressor(f"执行mute动作时出错: {e}")

            return False, "执行mute动作时出错"

        return True, "测试动作执行成功"
