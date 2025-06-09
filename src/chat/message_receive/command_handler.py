import re
import importlib
import pkgutil
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Type, Optional, Tuple, Pattern
from src.common.logger_manager import get_logger
from src.chat.message_receive.message import MessageRecv
from src.chat.actions.plugin_api.message_api import MessageAPI
from src.chat.focus_chat.hfc_utils import create_empty_anchor_message
from src.chat.focus_chat.expressors.default_expressor import DefaultExpressor

logger = get_logger("command_handler")

# 全局命令注册表
_COMMAND_REGISTRY: Dict[str, Type["BaseCommand"]] = {}
_COMMAND_PATTERNS: Dict[Pattern, Type["BaseCommand"]] = {}

class BaseCommand(ABC):
    """命令基类，所有自定义命令都应该继承这个类"""
    
    # 命令的基本属性
    command_name: str = ""  # 命令名称
    command_description: str = ""  # 命令描述
    command_pattern: str = ""  # 命令匹配模式（正则表达式）
    command_help: str = ""  # 命令帮助信息
    command_examples: List[str] = []  # 命令使用示例
    enable_command: bool = True  # 是否启用命令
    
    def __init__(self, message: MessageRecv):
        """初始化命令处理器
        
        Args:
            message: 接收到的消息对象
        """
        self.message = message
        self.matched_groups: Dict[str, str] = {}  # 存储正则表达式匹配的命名组
        self._services = {}  # 存储内部服务
        
        # 设置服务
        self._services["chat_stream"] = message.chat_stream
        
        # 日志前缀
        self.log_prefix = f"[Command:{self.command_name}]"
    
    @abstractmethod
    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行命令的抽象方法，需要被子类实现
        
        Returns:
            Tuple[bool, Optional[str]]: (是否执行成功, 可选的回复消息)
        """
        pass
    
    def set_matched_groups(self, groups: Dict[str, str]) -> None:
        """设置正则表达式匹配的命名组
        
        Args:
            groups: 正则表达式匹配的命名组
        """
        self.matched_groups = groups
        
    async def send_reply(self, content: str) -> None:
        """发送回复消息
        
        Args:
            content: 回复内容
        """
        try:
            # 获取聊天流
            chat_stream = self.message.chat_stream
            if not chat_stream:
                logger.error(f"{self.log_prefix} 无法发送消息：缺少chat_stream")
                return
                
            # 创建空的锚定消息
            anchor_message = await create_empty_anchor_message(
                chat_stream.platform, 
                chat_stream.group_info, 
                chat_stream
            )
            
            # 创建表达器，传入chat_stream参数
            expressor = DefaultExpressor(chat_stream)
            
            # 设置服务
            self._services["expressor"] = expressor
            
            # 发送消息
            response_set = [
                ("text", content),
            ]
            
            # 调用表达器发送消息
            await expressor.send_response_messages(
                anchor_message=anchor_message,
                response_set=response_set,
                display_message="",
            )
            
            logger.info(f"{self.log_prefix} 命令回复消息发送成功: {content[:30]}...")
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送命令回复消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())


def register_command(cls):
    """
    命令注册装饰器
    
    用法:
        @register_command
        class MyCommand(BaseCommand):
            command_name = "my_command"
            command_description = "我的命令"
            command_pattern = r"^/mycommand\s+(?P<arg1>\w+)\s+(?P<arg2>\w+)$"
            ...
    """
    # 检查类是否有必要的属性
    if not hasattr(cls, "command_name") or not hasattr(cls, "command_description") or not hasattr(cls, "command_pattern"):
        logger.error(f"命令类 {cls.__name__} 缺少必要的属性: command_name, command_description 或 command_pattern")
        return cls
    
    command_name = cls.command_name
    command_pattern = cls.command_pattern
    is_enabled = getattr(cls, "enable_command", True)  # 默认启用命令
    
    if not command_name or not command_pattern:
        logger.error(f"命令类 {cls.__name__} 的 command_name 或 command_pattern 为空")
        return cls
    
    # 将命令类注册到全局注册表
    _COMMAND_REGISTRY[command_name] = cls
    
    # 编译正则表达式并注册
    try:
        pattern = re.compile(command_pattern, re.IGNORECASE | re.DOTALL)
        _COMMAND_PATTERNS[pattern] = cls
        logger.info(f"已注册命令: {command_name} -> {cls.__name__}，命令启用: {is_enabled}")
    except re.error as e:
        logger.error(f"命令 {command_name} 的正则表达式编译失败: {e}")
    
    return cls


class CommandManager:
    """命令管理器，负责加载和处理命令"""
    
    def __init__(self):
        """初始化命令管理器"""
        self._load_commands()
    
    def _load_commands(self) -> None:
        """加载所有命令"""
        try:
            # 检查插件目录是否存在
            plugin_path = "src.plugins"
            plugin_dir = os.path.join("src", "plugins")
            if not os.path.exists(plugin_dir):
                logger.info(f"插件目录 {plugin_dir} 不存在，跳过插件命令加载")
                return
            
            # 导入插件包
            try:
                plugins_package = importlib.import_module(plugin_path)
                logger.info(f"成功导入插件包: {plugin_path}")
            except ImportError as e:
                logger.error(f"导入插件包失败: {e}")
                return
            
            # 遍历插件包中的所有子包
            loaded_commands = 0
            for _, plugin_name, is_pkg in pkgutil.iter_modules(
                plugins_package.__path__, plugins_package.__name__ + "."
            ):
                if not is_pkg:
                    continue
                
                logger.debug(f"检测到插件: {plugin_name}")
                
                # 检查插件是否有commands子包
                plugin_commands_path = f"{plugin_name}.commands"
                plugin_commands_dir = plugin_name.replace(".", os.path.sep) + os.path.sep + "commands"
                
                if not os.path.exists(plugin_commands_dir):
                    logger.debug(f"插件 {plugin_name} 没有commands目录: {plugin_commands_dir}")
                    continue
                
                try:
                    # 尝试导入插件的commands包
                    commands_module = importlib.import_module(plugin_commands_path)
                    logger.info(f"成功加载插件命令模块: {plugin_commands_path}")
                    
                    # 遍历commands目录中的所有Python文件
                    commands_dir = os.path.dirname(commands_module.__file__)
                    for file in os.listdir(commands_dir):
                        if file.endswith('.py') and file != '__init__.py':
                            command_module_name = f"{plugin_commands_path}.{file[:-3]}"
                            try:
                                importlib.import_module(command_module_name)
                                logger.info(f"成功加载命令: {command_module_name}")
                                loaded_commands += 1
                            except Exception as e:
                                logger.error(f"加载命令失败: {command_module_name}, 错误: {e}")
                    
                except ImportError as e:
                    logger.debug(f"插件 {plugin_name} 的commands子包导入失败: {e}")
                    continue
            
            logger.success(f"成功加载 {loaded_commands} 个插件命令")
            logger.info(f"已注册的命令: {list(_COMMAND_REGISTRY.keys())}")
        
        except Exception as e:
            logger.error(f"加载命令失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def process_command(self, message: MessageRecv) -> Tuple[bool, Optional[str], bool]:
        """处理消息中的命令
        
        Args:
            message: 接收到的消息对象
            
        Returns:
            Tuple[bool, Optional[str], bool]: (是否找到并执行了命令, 命令执行结果, 是否继续处理消息)
        """
        if not message.processed_plain_text:
            await message.process()
        
        text = message.processed_plain_text
        
        # 检查是否匹配任何命令模式
        for pattern, command_cls in _COMMAND_PATTERNS.items():
            match = pattern.match(text)
            if match and getattr(command_cls, "enable_command", True):
                # 创建命令实例
                command_instance = command_cls(message)
                
                # 提取命名组并设置
                groups = match.groupdict()
                command_instance.set_matched_groups(groups)
                
                try:
                    # 执行命令
                    success, response = await command_instance.execute()
                    
                    # 记录命令执行结果
                    if success:
                        logger.info(f"命令 {command_cls.command_name} 执行成功")
                        if response:
                            # 使用命令实例的send_reply方法发送回复
                            await command_instance.send_reply(response)
                    else:
                        logger.warning(f"命令 {command_cls.command_name} 执行失败: {response}")
                        if response:
                            # 使用命令实例的send_reply方法发送错误信息
                            await command_instance.send_reply(f"命令执行失败: {response}")
                    
                    # 命令执行后不再继续处理消息
                    return True, response, False
                
                except Exception as e:
                    logger.error(f"执行命令 {command_cls.command_name} 时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
                    try:
                        # 使用命令实例的send_reply方法发送错误信息
                        await command_instance.send_reply(f"命令执行出错: {str(e)}")
                    except Exception as send_error:
                        logger.error(f"发送错误消息失败: {send_error}")
                    
                    # 命令执行出错后不再继续处理消息
                    return True, str(e), False
        
        # 没有匹配到任何命令，继续处理消息
        return False, None, True


# 创建全局命令管理器实例
command_manager = CommandManager() 