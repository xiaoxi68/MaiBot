from typing import List, Tuple, Type
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ComponentInfo, ActionActivationType, ConfigField
)

# ===== Action组件 =====

class HelloAction(BaseAction):
    """问候Action - 简单的问候动作"""

    # === 基本信息（必须填写）===
    action_name = "hello_greeting"
    action_description = "向用户发送问候消息"

    # === 功能描述（必须填写）===
    action_parameters = {
        "greeting_message": "要发送的问候消息"
    }
    action_require = [
        "需要发送友好问候时使用",
        "当有人向你问好时使用",
        "当你遇见没有见过的人时使用"
        ]
    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        """执行问候动作 - 这是核心功能"""
        # 发送问候消息
        greeting_message = self.action_data.get("greeting_message","")
        base_message = self.get_config("greeting.message", "嗨！很开心见到你！😊")
        message = base_message + greeting_message
        await self.send_text(message)

        return True, "发送了问候消息"

class ByeAction(BaseAction):
    """告别Action - 只在用户说再见时激活"""
    
    action_name = "bye_greeting"
    action_description = "向用户发送告别消息"
    
    # 使用关键词激活
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    
    # 关键词设置
    activation_keywords = ["再见", "bye", "88", "拜拜"]
    keyword_case_sensitive = False
    
    action_parameters = {"bye_message": "要发送的告别消息"}
    action_require = [
        "用户要告别时使用",
        "当有人要离开时使用",
        "当有人和你说再见时使用",
        ]
    associated_types = ["text"]
    
    async def execute(self) -> Tuple[bool, str]:
        bye_message = self.action_data.get("bye_message","")
        
        message = "再见！期待下次聊天！👋" + bye_message
        await self.send_text(message)
        return True, "发送了告别消息"

class TimeCommand(BaseCommand):
    """时间查询Command - 响应/time命令"""

    command_name = "time"
    command_description = "查询当前时间"

    # === 命令设置（必须填写）===
    command_pattern = r"^/time$"  # 精确匹配 "/time" 命令
    command_help = "查询当前时间"
    command_examples = ["/time"]
    intercept_message = True  # 拦截消息，不让其他组件处理

    async def execute(self) -> Tuple[bool, str]:
        """执行时间查询"""
        import datetime
  
        # 获取当前时间
        time_format = self.get_config("time.format", "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()
        time_str = now.strftime(time_format)
  
        # 发送时间信息
        message = f"⏰ 当前时间：{time_str}"
        await self.send_text(message)
  
        return True, f"显示了当前时间: {time_str}"


# ===== 插件注册 =====

@register_plugin
class HelloWorldPlugin(BasePlugin):
    """Hello World插件 - 你的第一个MaiCore插件"""

    # 插件基本信息
    plugin_name = "hello_world_plugin"
    plugin_description = "我的第一个MaiCore插件，包含问候功能"
    plugin_version = "1.0.0"
    plugin_author = "你的名字"
    enable_plugin = True
    config_file_name = "config.toml"  # 配置文件名

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本信息",
        "greeting": "问候功能配置",
        "time": "时间查询配置"
    }

    # 配置Schema定义
    config_schema = {
        "plugin": {
            "name": ConfigField(type=str, default="hello_world_plugin", description="插件名称"),
            "version": ConfigField(type=str, default="1.0.0", description="插件版本"),
            "enabled": ConfigField(type=bool, default=False, description="是否启用插件")
        },
        "greeting": {
            "message": ConfigField(
                type=str, 
                default="嗨！很开心见到你！😊", 
                description="默认问候消息"
            ),
            "enable_emoji": ConfigField(type=bool, default=True, description="是否启用表情符号")
        },
        "time": {
            "format": ConfigField(
                type=str, 
                default="%Y-%m-%d %H:%M:%S", 
                description="时间显示格式"
            )
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (HelloAction.get_action_info(), HelloAction),
            (ByeAction.get_action_info(), ByeAction),  # 添加告别Action
            (TimeCommand.get_command_info(), TimeCommand),
        ]