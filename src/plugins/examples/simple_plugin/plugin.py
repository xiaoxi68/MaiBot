"""
完整示例插件

演示新插件系统的完整功能：
- 使用简化的导入接口
- 展示Action和Command组件的定义
- 展示插件配置的使用
- 提供实用的示例功能
- 演示API的多种使用方式
"""

from typing import List, Tuple, Type, Optional

# 使用简化的导入接口
from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseAction,
    BaseCommand,
    ComponentInfo,
    ActionActivationType,
    ChatMode,
)
from src.common.logger_manager import get_logger

logger = get_logger("simple_plugin")


class HelloAction(BaseAction):
    """智能问候Action组件"""

    # ✅ 现在可以直接在类中定义激活条件！
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["你好", "hello", "问候", "hi", "嗨"]
    keyword_case_sensitive = False
    mode_enable = ChatMode.ALL
    parallel_action = False

    async def execute(self) -> Tuple[bool, str]:
        """执行问候动作"""
        username = self.action_data.get("username", "朋友")

        # 使用配置文件中的问候消息
        plugin_instance = SimplePlugin()
        greeting_template = plugin_instance.get_config("hello_action.greeting_message", "你好，{username}！")
        enable_emoji = plugin_instance.get_config("hello_action.enable_emoji", True)
        enable_llm = plugin_instance.get_config("hello_action.enable_llm_greeting", False)

        # 如果启用LLM生成个性化问候
        if enable_llm:
            try:
                # 演示：使用LLM API生成个性化问候
                models = self.api.get_available_models()
                if models:
                    first_model = list(models.values())[0]
                    prompt = f"为用户名叫{username}的朋友生成一句温暖的个性化问候语，不超过30字："

                    success, response, _, _ = await self.api.generate_with_model(
                        prompt=prompt, model_config=first_model
                    )

                    if success:
                        logger.info(f"{self.log_prefix} 使用LLM生成问候: {response}")
                        return True, response
            except Exception as e:
                logger.warning(f"{self.log_prefix} LLM生成问候失败，使用默认模板: {e}")

        # 构建基础问候消息
        response = greeting_template.format(username=username)
        if enable_emoji:
            response += " 😊"

        # 演示：存储Action执行记录到数据库
        await self.api.store_action_info(
            action_build_into_prompt=False, action_prompt_display=f"问候了用户: {username}", action_done=True
        )

        logger.info(f"{self.log_prefix} 执行问候动作: {username}")
        return True, response


class EchoCommand(BaseCommand):
    """回声命令 - 重复用户输入"""

    # ✅ 现在可以直接在类中定义命令模式！
    command_pattern = r"^/echo\s+(?P<message>.+)$"
    command_help = "重复消息，用法：/echo <消息内容>"
    command_examples = ["/echo Hello World", "/echo 你好世界"]

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行回声命令"""
        # 获取匹配的参数
        message = self.matched_groups.get("message", "")

        if not message:
            response = "请提供要重复的消息！用法：/echo <消息内容>"
        else:
            response = f"🔊 {message}"

        # 发送回复
        await self.send_reply(response)

        logger.info(f"{self.log_prefix} 执行回声命令: {message}")
        return True, response


class StatusCommand(BaseCommand):
    """状态查询Command组件"""

    # ✅ 直接定义命令模式
    command_pattern = r"^/status\s*(?P<type>\w+)?$"
    command_help = "查询系统状态，用法：/status [类型]"
    command_examples = ["/status", "/status 系统", "/status 插件"]

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行状态查询命令"""
        # 获取匹配的参数
        query_type = self.matched_groups.get("type", "系统")

        # 从配置文件获取设置
        plugin_instance = SimplePlugin()
        show_detailed = plugin_instance.get_config("status_command.show_detailed_info", True)
        allowed_types = plugin_instance.get_config("status_command.allowed_types", ["系统", "插件"])

        if query_type not in allowed_types:
            response = f"不支持的查询类型: {query_type}\n支持的类型: {', '.join(allowed_types)}"
        elif show_detailed:
            response = f"📊 {query_type}状态详情：\n✅ 运行正常\n🔧 版本: 1.0.0\n⚡ 性能: 良好"
        else:
            response = f"✅ {query_type}状态：正常"

        # 发送回复
        await self.send_reply(response)

        logger.info(f"{self.log_prefix} 执行状态查询: {query_type}")
        return True, response


class HelpCommand(BaseCommand):
    """帮助命令 - 显示插件功能"""

    # ✅ 直接定义命令模式
    command_pattern = r"^/help$"
    command_help = "显示插件帮助信息"
    command_examples = ["/help"]

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行帮助命令"""
        help_text = """
🤖 简单示例插件帮助

📝 可用命令：
• /echo <消息> - 重复你的消息
• /status [类型] - 查询系统状态
• /help - 显示此帮助信息

🎯 智能功能：
• 自动问候 - 当消息包含"你好"、"hello"等关键词时触发

⚙️ 配置：
本插件支持通过config.toml文件进行个性化配置

💡 这是新插件系统的完整示例，展示了Action和Command的结合使用。
        """.strip()

        await self.send_reply(help_text)

        logger.info(f"{self.log_prefix} 显示帮助信息")
        return True, "已显示帮助信息"


@register_plugin
class SimplePlugin(BasePlugin):
    """完整示例插件

    包含多个Action和Command组件，展示插件系统的完整功能
    """

    # 插件基本信息
    plugin_name = "simple_plugin"
    plugin_description = "完整的示例插件，展示新插件系统的各种功能"
    plugin_version = "1.1.0"
    plugin_author = "MaiBot开发团队"
    enable_plugin = True
    config_file_name = "config.toml"  # 配置文件

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""

        # ✅ 现在可以直接从类属性生成组件信息！
        return [
            (HelloAction.get_action_info("hello_action", "智能问候动作，支持自定义消息和表情"), HelloAction),
            (EchoCommand.get_command_info("echo_command", "回声命令，重复用户输入的消息"), EchoCommand),
            (StatusCommand.get_command_info("status_command", "状态查询命令，支持多种查询类型"), StatusCommand),
            (HelpCommand.get_command_info("help_command", "帮助命令，显示插件功能说明"), HelpCommand),
        ]
