from src.common.logger_manager import get_logger
from src.chat.message_receive.command_handler import BaseCommand, register_command
from typing import Tuple, Optional

logger = get_logger("echo_command")

@register_command
class EchoCommand(BaseCommand):
    """回显命令，将用户输入的内容回显"""
    
    command_name = "echo"
    command_description = "回显命令，将用户输入的内容回显"
    command_pattern = r"^/echo\s+(?P<content>.+)$"  # 匹配 /echo 后面的所有内容
    command_help = "使用方法: /echo <内容> - 回显你输入的内容"
    command_examples = ["/echo 你好，世界！", "/echo 这是一个测试"]
    enable_command = True
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行回显命令
        
        Returns:
            Tuple[bool, Optional[str]]: (是否执行成功, 回复消息)
        """
        try:
            # 获取匹配到的内容
            content = self.matched_groups.get("content")
            
            if not content:
                return False, "请提供要回显的内容"
            
            logger.info(f"{self.log_prefix} 执行回显命令: {content}")
            return True, f"🔄 {content}"
        
        except Exception as e:
            logger.error(f"{self.log_prefix} 执行回显命令时出错: {e}")
            return False, f"执行命令时出错: {str(e)}" 