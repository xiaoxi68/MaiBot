from src.common.logger_manager import get_logger
from src.chat.message_receive.command_handler import BaseCommand, register_command
from src.chat.actions.plugin_api.message_api import MessageAPI
from typing import Tuple, Optional

logger = get_logger("send_msg_command")

@register_command
class SendMessageCommand(BaseCommand, MessageAPI):
    """发送消息命令，可以向指定群聊或私聊发送消息"""
    
    command_name = "send"
    command_description = "向指定群聊或私聊发送消息"
    command_pattern = r"^/send\s+(?P<target_type>group|user)\s+(?P<target_id>\d+)\s+(?P<content>.+)$"
    command_help = "使用方法: /send <group|user> <ID> <消息内容> - 发送消息到指定群聊或用户"
    command_examples = [
        "/send group 123456789 大家好！",
        "/send user 987654321 私聊消息"
    ]
    enable_command = True
    
    def __init__(self, message):
        super().__init__(message)
        # 初始化MessageAPI需要的服务（虽然这里不会用到，但保持一致性）
        self._services = {}
        self.log_prefix = f"[Command:{self.command_name}]"
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行发送消息命令
        
        Returns:
            Tuple[bool, Optional[str]]: (是否执行成功, 回复消息)
        """
        try:
            # 获取匹配到的参数
            target_type = self.matched_groups.get("target_type")  # group 或 user
            target_id = self.matched_groups.get("target_id")      # 群ID或用户ID
            content = self.matched_groups.get("content")          # 消息内容
            
            if not all([target_type, target_id, content]):
                return False, "命令参数不完整，请检查格式"
            
            logger.info(f"{self.log_prefix} 执行发送消息命令: {target_type}:{target_id} -> {content[:50]}...")
            
            # 根据目标类型调用不同的发送方法
            if target_type == "group":
                success = await self._send_to_group(target_id, content)
                target_desc = f"群聊 {target_id}"
            elif target_type == "user":
                success = await self._send_to_user(target_id, content)
                target_desc = f"用户 {target_id}"
            else:
                return False, f"不支持的目标类型: {target_type}，只支持 group 或 user"
            
            # 返回执行结果
            if success:
                return True, f"✅ 消息已成功发送到 {target_desc}"
            else:
                return False, f"❌ 消息发送失败，可能是目标 {target_desc} 不存在或没有权限"
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 执行发送消息命令时出错: {e}")
            return False, f"命令执行出错: {str(e)}"
    
    async def _send_to_group(self, group_id: str, content: str) -> bool:
        """发送消息到群聊
        
        Args:
            group_id: 群聊ID
            content: 消息内容
            
        Returns:
            bool: 是否发送成功
        """
        try:
            success = await self.send_text_to_group(
                text=content,
                group_id=group_id,
                platform="qq"  # 默认使用QQ平台
            )
            
            if success:
                logger.info(f"{self.log_prefix} 成功发送消息到群聊 {group_id}")
            else:
                logger.warning(f"{self.log_prefix} 发送消息到群聊 {group_id} 失败")
            
            return success
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送群聊消息时出错: {e}")
            return False
    
    async def _send_to_user(self, user_id: str, content: str) -> bool:
        """发送消息到私聊
        
        Args:
            user_id: 用户ID
            content: 消息内容
            
        Returns:
            bool: 是否发送成功
        """
        try:
            success = await self.send_text_to_user(
                text=content,
                user_id=user_id,
                platform="qq"  # 默认使用QQ平台
            )
            
            if success:
                logger.info(f"{self.log_prefix} 成功发送消息到用户 {user_id}")
            else:
                logger.warning(f"{self.log_prefix} 发送消息到用户 {user_id} 失败")
            
            return success
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送私聊消息时出错: {e}")
            return False 