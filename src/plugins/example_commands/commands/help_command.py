from src.common.logger_manager import get_logger
from src.chat.message_receive.command_handler import BaseCommand, register_command, _COMMAND_REGISTRY
from typing import Tuple, Optional

logger = get_logger("help_command")

@register_command
class HelpCommand(BaseCommand):
    """帮助命令，显示所有可用命令的帮助信息"""
    
    command_name = "help"
    command_description = "显示所有可用命令的帮助信息"
    command_pattern = r"^/help(?:\s+(?P<command>\w+))?$"  # 匹配 /help 或 /help 命令名
    command_help = "使用方法: /help [命令名] - 显示所有命令或特定命令的帮助信息"
    command_examples = ["/help", "/help echo"]
    enable_command = True
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行帮助命令
        
        Returns:
            Tuple[bool, Optional[str]]: (是否执行成功, 回复消息)
        """
        try:
            # 获取匹配到的命令名（如果有）
            command_name = self.matched_groups.get("command")
            
            # 如果指定了命令名，显示该命令的详细帮助
            if command_name:
                logger.info(f"{self.log_prefix} 查询命令帮助: {command_name}")
                return self._show_command_help(command_name)
            
            # 否则，显示所有命令的简要帮助
            logger.info(f"{self.log_prefix} 查询所有命令帮助")
            return self._show_all_commands()
        
        except Exception as e:
            logger.error(f"{self.log_prefix} 执行帮助命令时出错: {e}")
            return False, f"执行命令时出错: {str(e)}"
    
    def _show_command_help(self, command_name: str) -> Tuple[bool, str]:
        """显示特定命令的详细帮助信息
        
        Args:
            command_name: 命令名称
            
        Returns:
            Tuple[bool, str]: (是否执行成功, 回复消息)
        """
        # 查找命令
        command_cls = _COMMAND_REGISTRY.get(command_name)
        
        if not command_cls:
            return False, f"未找到命令: {command_name}"
        
        # 获取命令信息
        description = getattr(command_cls, "command_description", "无描述")
        help_text = getattr(command_cls, "command_help", "无帮助信息")
        examples = getattr(command_cls, "command_examples", [])
        
        # 构建帮助信息
        help_info = [
            f"【命令】: {command_name}",
            f"【描述】: {description}",
            f"【用法】: {help_text}"
        ]
        
        # 添加示例
        if examples:
            help_info.append("【示例】:")
            for example in examples:
                help_info.append(f"  {example}")
        
        return True, "\n".join(help_info)
    
    def _show_all_commands(self) -> Tuple[bool, str]:
        """显示所有可用命令的简要帮助信息
        
        Returns:
            Tuple[bool, str]: (是否执行成功, 回复消息)
        """
        # 获取所有已启用的命令
        enabled_commands = {
            name: cls for name, cls in _COMMAND_REGISTRY.items()
            if getattr(cls, "enable_command", True)
        }
        
        if not enabled_commands:
            return True, "当前没有可用的命令"
        
        # 构建命令列表
        command_list = ["可用命令列表:"]
        for name, cls in sorted(enabled_commands.items()):
            description = getattr(cls, "command_description", "无描述")
            # 获取命令前缀示例
            examples = getattr(cls, "command_examples", [])
            prefix = ""
            if examples and len(examples) > 0:
                # 从第一个示例中提取前缀
                example = examples[0]
                # 找到第一个空格前的内容作为前缀
                space_pos = example.find(" ")
                if space_pos > 0:
                    prefix = example[:space_pos]
                else:
                    prefix = example
            else:
                # 默认使用/name作为前缀
                prefix = f"/{name}"
            
            command_list.append(f"{prefix} - {description}")
        
        command_list.append("\n使用 /help <命令名> 获取特定命令的详细帮助")
        
        return True, "\n".join(command_list) 