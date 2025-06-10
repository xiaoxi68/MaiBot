from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional, List
from src.common.logger_manager import get_logger
from src.plugin_system.apis.plugin_api import PluginAPI
from src.plugin_system.base.component_types import CommandInfo, ComponentType
from src.chat.message_receive.message import MessageRecv

logger = get_logger("base_command")


class BaseCommand(ABC):
    """Command组件基类

    Command是插件的一种组件类型，用于处理命令请求

    子类可以通过类属性定义命令模式：
    - command_pattern: 命令匹配的正则表达式
    - command_help: 命令帮助信息
    - command_examples: 命令使用示例列表
    - intercept_message: 是否拦截消息处理（默认True拦截，False继续传递）
    """

    # 默认命令设置（子类可以覆盖）
    command_pattern: str = ""
    command_help: str = ""
    command_examples: List[str] = []
    intercept_message: bool = True  # 默认拦截消息，不继续处理

    def __init__(self, message: MessageRecv, plugin_config: dict = None):
        """初始化Command组件

        Args:
            message: 接收到的消息对象
            plugin_config: 插件配置字典
        """
        self.message = message
        self.matched_groups: Dict[str, str] = {}  # 存储正则表达式匹配的命名组

        # 创建API实例
        self.api = PluginAPI(chat_stream=message.chat_stream, log_prefix="[Command]", plugin_config=plugin_config)

        self.log_prefix = "[Command]"

        logger.debug(f"{self.log_prefix} Command组件初始化完成")

    def set_matched_groups(self, groups: Dict[str, str]) -> None:
        """设置正则表达式匹配的命名组

        Args:
            groups: 正则表达式匹配的命名组
        """
        self.matched_groups = groups

    @abstractmethod
    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行Command的抽象方法，子类必须实现

        Returns:
            Tuple[bool, Optional[str]]: (是否执行成功, 可选的回复消息)
        """
        pass

    async def send_reply(self, content: str) -> None:
        """发送回复消息

        Args:
            content: 回复内容
        """
        # 获取聊天流信息
        chat_stream = self.message.chat_stream

        if chat_stream.group_info:
            # 群聊
            await self.api.send_text_to_group(
                text=content, group_id=str(chat_stream.group_info.group_id), platform=chat_stream.platform
            )
        else:
            # 私聊
            await self.api.send_text_to_user(
                text=content, user_id=str(chat_stream.user_info.user_id), platform=chat_stream.platform
            )

    async def send_command(self, command_name: str, args: dict = None, display_message: str = None) -> bool:
        """发送命令消息
        
        使用和send_reply相同的方式通过MessageAPI发送命令
        
        Args:
            command_name: 命令名称
            args: 命令参数
            display_message: 显示消息
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 构造命令数据
            command_data = {
                "name": command_name,
                "args": args or {}
            }
            
            # 使用send_message_to_target方法发送命令
            chat_stream = self.message.chat_stream
            command_content = str(command_data)
            
            if chat_stream.group_info:
                # 群聊
                success = await self.api.send_message_to_target(
                    message_type="command",
                    content=command_content,
                    platform=chat_stream.platform,
                    target_id=str(chat_stream.group_info.group_id),
                    is_group=True,
                    display_message=display_message or f"执行命令: {command_name}"
                )
            else:
                # 私聊
                success = await self.api.send_message_to_target(
                    message_type="command",
                    content=command_content,
                    platform=chat_stream.platform,
                    target_id=str(chat_stream.user_info.user_id),
                    is_group=False,
                    display_message=display_message or f"执行命令: {command_name}"
                )
            
            if success:
                logger.info(f"{self.log_prefix} 成功发送命令: {command_name}")
            else:
                logger.error(f"{self.log_prefix} 发送命令失败: {command_name}")
                
            return success
                
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送命令时出错: {e}")
            return False

    @classmethod
    def get_command_info(cls, name: str = None, description: str = None) -> "CommandInfo":
        """从类属性生成CommandInfo

        Args:
            name: Command名称，如果不提供则使用类名
            description: Command描述，如果不提供则使用类文档字符串

        Returns:
            CommandInfo: 生成的Command信息对象
        """

        # 优先使用类属性，然后自动生成
        if name is None:
            name = getattr(cls, "command_name", cls.__name__.lower().replace("command", ""))
        if description is None:
            description = getattr(cls, "command_description", None)
            if description is None:
                description = cls.__doc__ or f"{cls.__name__} Command组件"
                description = description.strip().split("\n")[0]  # 取第一行作为描述

        return CommandInfo(
            name=name,
            component_type=ComponentType.COMMAND,
            description=description,
            command_pattern=cls.command_pattern,
            command_help=cls.command_help,
            command_examples=cls.command_examples.copy() if cls.command_examples else [],
            intercept_message=cls.intercept_message,
        )
