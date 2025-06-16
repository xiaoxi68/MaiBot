"""
禁言插件

提供智能禁言功能的群聊管理插件。

功能特性：
- 智能LLM判定：根据聊天内容智能判断是否需要禁言
- 灵活的时长管理：支持自定义禁言时长限制
- 模板化消息：支持自定义禁言提示消息
- 参数验证：完整的输入参数验证和错误处理
- 配置文件支持：所有设置可通过配置文件调整

包含组件：
- 智能禁言Action - 基于LLM判断是否需要禁言
- 禁言命令Command - 手动执行禁言操作
"""

from typing import List, Tuple, Type, Optional
import random

# 导入新插件系统
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.base_plugin import register_plugin
from src.plugin_system.base.base_action import BaseAction
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ComponentInfo, ActionActivationType, ChatMode
from src.common.logger import get_logger

logger = get_logger("mute_plugin")


# ===== Action组件 =====


class MuteAction(BaseAction):
    """智能禁言Action - 基于LLM智能判断是否需要禁言"""

    # 激活设置
    focus_activation_type = ActionActivationType.LLM_JUDGE  # Focus模式使用LLM判定，确保谨慎
    normal_activation_type = ActionActivationType.KEYWORD  # Normal模式使用关键词激活，快速响应
    mode_enable = ChatMode.ALL
    parallel_action = False

    # 动作基本信息
    action_name = "mute"
    action_description = "智能禁言系统，基于LLM判断是否需要禁言"

    # 关键词设置（用于Normal模式）
    activation_keywords = ["禁言", "mute", "ban", "silence"]
    keyword_case_sensitive = False

    # LLM判定提示词（用于Focus模式）
    llm_judge_prompt = """
判定是否需要使用禁言动作的严格条件：

使用禁言的情况：
1. 用户发送明显违规内容（色情、暴力、政治敏感等）
2. 恶意刷屏或垃圾信息轰炸
3. 用户主动明确要求被禁言（"禁言我"等）
4. 严重违反群规的行为
5. 恶意攻击他人或群组管理

绝对不要使用的情况：
2. 情绪化表达但无恶意
3. 开玩笑或调侃，除非过分
4. 单纯的意见分歧或争论

"""

    # 动作参数定义
    action_parameters = {
        "target": "禁言对象，必填，输入你要禁言的对象的名字，请仔细思考不要弄错禁言对象",
        "duration": "禁言时长，必填，输入你要禁言的时长（秒），单位为秒，必须为数字",
        "reason": "禁言理由，可选",
    }

    # 动作使用场景
    action_require = [
        "当有人违反了公序良俗的内容",
        "当有人刷屏时使用",
        "当有人发了擦边，或者色情内容时使用",
        "当有人要求禁言自己时使用",
        "如果某人已经被禁言了，就不要再次禁言了，除非你想追加时间！！",
    ]

    # 关联类型
    associated_types = ["text", "command"]

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行智能禁言判定"""
        logger.info(f"{self.log_prefix} 执行智能禁言动作")

        # 获取参数
        target = self.action_data.get("target")
        duration = self.action_data.get("duration")
        reason = self.action_data.get("reason", "违反群规")

        # 参数验证
        if not target:
            error_msg = "禁言目标不能为空"
            logger.error(f"{self.log_prefix} {error_msg}")
            await self.send_text("没有指定禁言对象呢~")
            return False, error_msg

        if not duration:
            error_msg = "禁言时长不能为空"
            logger.error(f"{self.log_prefix} {error_msg}")
            await self.send_text("没有指定禁言时长呢~")
            return False, error_msg

        # 获取时长限制配置
        min_duration = self.api.get_config("mute.min_duration", 60)
        max_duration = self.api.get_config("mute.max_duration", 2592000)

        # 验证时长格式并转换
        try:
            duration_int = int(duration)
            if duration_int <= 0:
                error_msg = "禁言时长必须大于0"
                logger.error(f"{self.log_prefix} {error_msg}")
                await self.send_text("禁言时长必须是正数哦~")
                return False, error_msg

            # 限制禁言时长范围
            if duration_int < min_duration:
                duration_int = min_duration
                logger.info(f"{self.log_prefix} 禁言时长过短，调整为{min_duration}秒")
            elif duration_int > max_duration:
                duration_int = max_duration
                logger.info(f"{self.log_prefix} 禁言时长过长，调整为{max_duration}秒")

        except (ValueError, TypeError):
            error_msg = f"禁言时长格式无效: {duration}"
            logger.error(f"{self.log_prefix} {error_msg}")
            await self.send_text("禁言时长必须是数字哦~")
            return False, error_msg

        # 获取用户ID
        try:
            platform, user_id = await self.api.get_user_id_by_person_name(target)
        except Exception as e:
            error_msg = f"查找用户ID时出错: {e}"
            logger.error(f"{self.log_prefix} {error_msg}")
            await self.send_text("查找用户信息时出现问题~")
            return False, error_msg

        if not user_id:
            error_msg = f"未找到用户 {target} 的ID"
            await self.send_text(f"找不到 {target} 这个人呢~")
            logger.error(f"{self.log_prefix} {error_msg}")
            return False, error_msg

        # 格式化时长显示
        enable_formatting = self.api.get_config("mute.enable_duration_formatting", True)
        time_str = self._format_duration(duration_int) if enable_formatting else f"{duration_int}秒"

        # 获取模板化消息
        message = self._get_template_message(target, time_str, reason)
        # await self.send_text(message)
        await self.send_message_by_expressor(message)

        # 发送群聊禁言命令
        success = await self.send_command(
            command_name="GROUP_BAN",
            args={"qq_id": str(user_id), "duration": str(duration_int)},
            display_message=f"发送禁言命令",
        )

        if success:
            logger.info(f"{self.log_prefix} 成功发送禁言命令，用户 {target}({user_id})，时长 {duration_int} 秒")
            # 存储动作信息
            await self.api.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=f"尝试禁言了用户 {target}，时长 {time_str}，原因：{reason}",
                action_done=True,
                thinking_id=self.thinking_id,
                action_data={
                    "target": target,
                    "user_id": user_id,
                    "duration": duration_int,
                    "duration_str": time_str,
                    "reason": reason
                }
            )
            return True, f"成功禁言 {target}，时长 {time_str}"
        else:
            error_msg = "发送禁言命令失败"
            logger.error(f"{self.log_prefix} {error_msg}")
            await self.send_text("执行禁言动作失败")
            return False, error_msg

    def _get_template_message(self, target: str, duration_str: str, reason: str) -> str:
        """获取模板化的禁言消息"""
        templates = self.api.get_config(
            "mute.templates",
            [
                "好的，禁言 {target} {duration}，理由：{reason}",
                "收到，对 {target} 执行禁言 {duration}，因为{reason}",
                "明白了，禁言 {target} {duration}，原因是{reason}",
            ],
        )

        template = random.choice(templates)
        return template.format(target=target, duration=duration_str, reason=reason)

    def _format_duration(self, seconds: int) -> str:
        """将秒数格式化为可读的时间字符串"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds > 0:
                return f"{minutes}分{remaining_seconds}秒"
            else:
                return f"{minutes}分钟"
        elif seconds < 86400:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            if remaining_minutes > 0:
                return f"{hours}小时{remaining_minutes}分钟"
            else:
                return f"{hours}小时"
        else:
            days = seconds // 86400
            remaining_hours = (seconds % 86400) // 3600
            if remaining_hours > 0:
                return f"{days}天{remaining_hours}小时"
            else:
                return f"{days}天"


# ===== Command组件 =====


class MuteCommand(BaseCommand):
    """禁言命令 - 手动执行禁言操作"""

    # Command基本信息
    command_name = "mute_command"
    command_description = "禁言命令，手动执行禁言操作"

    command_pattern = r"^/mute\s+(?P<target>\S+)\s+(?P<duration>\d+)(?:\s+(?P<reason>.+))?$"
    command_help = "禁言指定用户，用法：/mute <用户名> <时长(秒)> [理由]"
    command_examples = ["/mute 用户名 300", "/mute 张三 600 刷屏", "/mute @某人 1800 违规内容"]
    intercept_message = True  # 拦截消息处理

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行禁言命令"""
        try:
            target = self.matched_groups.get("target")
            duration = self.matched_groups.get("duration")
            reason = self.matched_groups.get("reason", "管理员操作")

            if not all([target, duration]):
                await self.send_text("❌ 命令参数不完整，请检查格式")
                return False, "参数不完整"

            # 获取时长限制配置
            min_duration = self.api.get_config("mute.min_duration", 60)
            max_duration = self.api.get_config("mute.max_duration", 2592000)

            # 验证时长
            try:
                duration_int = int(duration)
                if duration_int <= 0:
                    await self.send_text("❌ 禁言时长必须大于0")
                    return False, "时长无效"

                # 限制禁言时长范围
                if duration_int < min_duration:
                    duration_int = min_duration
                    await self.send_text(f"⚠️ 禁言时长过短，调整为{min_duration}秒")
                elif duration_int > max_duration:
                    duration_int = max_duration
                    await self.send_text(f"⚠️ 禁言时长过长，调整为{max_duration}秒")

            except ValueError:
                await self.send_text("❌ 禁言时长必须是数字")
                return False, "时长格式错误"

            # 获取用户ID
            try:
                platform, user_id = await self.api.get_user_id_by_person_name(target)
            except Exception as e:
                logger.error(f"{self.log_prefix} 查找用户ID时出错: {e}")
                await self.send_text("❌ 查找用户信息时出现问题")
                return False, str(e)

            if not user_id:
                await self.send_text(f"❌ 找不到用户: {target}")
                return False, "用户不存在"

            # 格式化时长显示
            enable_formatting = self.api.get_config("mute.enable_duration_formatting", True)
            time_str = self._format_duration(duration_int) if enable_formatting else f"{duration_int}秒"

            logger.info(f"{self.log_prefix} 执行禁言命令: {target}({user_id}) -> {time_str}")

            # 发送群聊禁言命令
            success = await self.send_command(
                command_name="GROUP_BAN",
                args={"qq_id": str(user_id), "duration": str(duration_int)},
                display_message=f"禁言了 {target} {time_str}",
            )

            if success:
                # 获取并发送模板化消息
                message = self._get_template_message(target, time_str, reason)
                await self.send_text(message)

                logger.info(f"{self.log_prefix} 成功禁言 {target}({user_id})，时长 {duration_int} 秒")
                return True, f"成功禁言 {target}，时长 {time_str}"
            else:
                await self.send_text("❌ 发送禁言命令失败")
                return False, "发送禁言命令失败"

        except Exception as e:
            logger.error(f"{self.log_prefix} 禁言命令执行失败: {e}")
            await self.send_text(f"❌ 禁言命令错误: {str(e)}")
            return False, str(e)

    def _get_template_message(self, target: str, duration_str: str, reason: str) -> str:
        """获取模板化的禁言消息"""
        templates = self.api.get_config(
            "mute.templates",
            [
                "✅ 已禁言 {target} {duration}，理由：{reason}",
                "🔇 对 {target} 执行禁言 {duration}，因为{reason}",
                "⛔ 禁言 {target} {duration}，原因：{reason}",
            ],
        )

        template = random.choice(templates)
        return template.format(target=target, duration=duration_str, reason=reason)

    def _format_duration(self, seconds: int) -> str:
        """将秒数格式化为可读的时间字符串"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds > 0:
                return f"{minutes}分{remaining_seconds}秒"
            else:
                return f"{minutes}分钟"
        elif seconds < 86400:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            if remaining_minutes > 0:
                return f"{hours}小时{remaining_minutes}分钟"
            else:
                return f"{hours}小时"
        else:
            days = seconds // 86400
            remaining_hours = (seconds % 86400) // 3600
            if remaining_hours > 0:
                return f"{days}天{remaining_hours}小时"
            else:
                return f"{days}天"


# ===== 插件主类 =====


@register_plugin
class MutePlugin(BasePlugin):
    """禁言插件

    提供智能禁言功能：
    - 智能禁言Action：基于LLM判断是否需要禁言
    - 禁言命令Command：手动执行禁言操作
    """

    # 插件基本信息
    plugin_name = "mute_plugin"
    plugin_description = "群聊禁言管理插件，提供智能禁言功能"
    plugin_version = "2.0.0"
    plugin_author = "MaiBot开发团队"
    enable_plugin = True
    config_file_name = "config.toml"

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""

        # 从配置获取组件启用状态
        enable_smart_mute = self.get_config("components.enable_smart_mute", True)
        enable_mute_command = self.get_config("components.enable_mute_command", True)

        components = []

        # 添加智能禁言Action
        if enable_smart_mute:
            components.append((MuteAction.get_action_info(), MuteAction))

        # 添加禁言命令Command
        if enable_mute_command:
            components.append((MuteCommand.get_command_info(), MuteCommand))

        return components
