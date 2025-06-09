import traceback
import time
from typing import Optional, List, Dict, Any
from src.common.logger_manager import get_logger
from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.focus_chat.hfc_utils import create_empty_anchor_message

# 以下为类型注解需要
from src.chat.message_receive.chat_stream import ChatStream, chat_manager
from src.chat.focus_chat.expressors.default_expressor import DefaultExpressor
from src.chat.focus_chat.replyer.default_replyer import DefaultReplyer
from src.chat.focus_chat.info.obs_info import ObsInfo

# 新增导入
from src.chat.focus_chat.heartFC_sender import HeartFCSender
from src.chat.message_receive.message import MessageSending
from maim_message import Seg, UserInfo, GroupInfo
from src.config.config import global_config

logger = get_logger("message_api")

class MessageAPI:
    """消息API模块
    
    提供了发送消息、获取消息历史等功能
    """
    
    async def send_message_to_target(
        self,
        message_type: str,
        content: str,
        platform: str,
        target_id: str,
        is_group: bool = True,
        display_message: str = "",
    ) -> bool:
        """直接向指定目标发送消息
        
        Args:
            message_type: 消息类型，如"text"、"image"、"emoji"等
            content: 消息内容
            platform: 目标平台，如"qq"
            target_id: 目标ID（群ID或用户ID）
            is_group: 是否为群聊，True为群聊，False为私聊
            display_message: 显示消息（可选）
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 构建目标聊天流ID
            if is_group:
                # 群聊：从数据库查找对应的聊天流
                target_stream = None
                for stream_id, stream in chat_manager.streams.items():
                    if (stream.group_info and 
                        str(stream.group_info.group_id) == str(target_id) and 
                        stream.platform == platform):
                        target_stream = stream
                        break
                
                if not target_stream:
                    logger.error(f"{getattr(self, 'log_prefix', '')} 未找到群ID为 {target_id} 的聊天流")
                    return False
            else:
                # 私聊：从数据库查找对应的聊天流
                target_stream = None
                for stream_id, stream in chat_manager.streams.items():
                    if (not stream.group_info and 
                        str(stream.user_info.user_id) == str(target_id) and 
                        stream.platform == platform):
                        target_stream = stream
                        break
                
                if not target_stream:
                    logger.error(f"{getattr(self, 'log_prefix', '')} 未找到用户ID为 {target_id} 的私聊流")
                    return False
            
            # 创建HeartFCSender实例
            heart_fc_sender = HeartFCSender()
            
            # 生成消息ID和thinking_id
            current_time = time.time()
            message_id = f"plugin_msg_{int(current_time * 1000)}"
            thinking_id = f"plugin_thinking_{int(current_time * 1000)}"
            
            # 构建机器人用户信息
            bot_user_info = UserInfo(
                user_id=global_config.bot.qq_account,
                user_nickname=global_config.bot.nickname,
                platform=platform,
            )
            
            # 创建消息段
            message_segment = Seg(type=message_type, data=content)
            
            # 创建空锚点消息（用于回复）
            anchor_message = await create_empty_anchor_message(
                platform, target_stream.group_info, target_stream
            )
            
            # 构建发送消息对象
            bot_message = MessageSending(
                message_id=message_id,
                chat_stream=target_stream,
                bot_user_info=bot_user_info,
                sender_info=target_stream.user_info,  # 目标用户信息
                message_segment=message_segment,
                display_message=display_message,
                reply=anchor_message,
                is_head=True,
                is_emoji=(message_type == "emoji"),
                thinking_start_time=current_time,
            )
            
            # 发送消息
            sent_msg = await heart_fc_sender.send_message(
                bot_message, 
                has_thinking=True, 
                typing=False, 
                set_reply=False
            )
            
            if sent_msg:
                logger.info(f"{getattr(self, 'log_prefix', '')} 成功发送消息到 {platform}:{target_id}")
                return True
            else:
                logger.error(f"{getattr(self, 'log_prefix', '')} 发送消息失败")
                return False
                
        except Exception as e:
            logger.error(f"{getattr(self, 'log_prefix', '')} 向目标发送消息时出错: {e}")
            traceback.print_exc()
            return False

    async def send_text_to_group(self, text: str, group_id: str, platform: str = "qq") -> bool:
        """便捷方法：向指定群聊发送文本消息
        
        Args:
            text: 要发送的文本内容
            group_id: 群聊ID
            platform: 平台，默认为"qq"
            
        Returns:
            bool: 是否发送成功
        """
        return await self.send_message_to_target(
            message_type="text",
            content=text,
            platform=platform,
            target_id=group_id,
            is_group=True
        )

    async def send_text_to_user(self, text: str, user_id: str, platform: str = "qq") -> bool:
        """便捷方法：向指定用户发送私聊文本消息
        
        Args:
            text: 要发送的文本内容
            user_id: 用户ID
            platform: 平台，默认为"qq"
            
        Returns:
            bool: 是否发送成功
        """
        return await self.send_message_to_target(
            message_type="text",
            content=text,
            platform=platform,
            target_id=user_id,
            is_group=False
        )
    
    async def send_message(self, type: str, data: str, target: Optional[str] = "", display_message: str = "") -> bool:
        """发送消息的简化方法

        Args:
            type: 消息类型，如"text"、"image"等
            data: 消息内容
            target: 目标消息（可选）
            display_message: 显示的消息内容（可选）

        Returns:
            bool: 是否发送成功
        """
        try:
            expressor: DefaultExpressor = self._services.get("expressor")
            chat_stream: ChatStream = self._services.get("chat_stream")

            if not expressor or not chat_stream:
                logger.error(f"{self.log_prefix} 无法发送消息：缺少必要的内部服务")
                return False

            # 获取锚定消息（如果有）
            observations = self._services.get("observations", [])

            if len(observations) > 0:
                chatting_observation: ChattingObservation = next(
                    (obs for obs in observations if isinstance(obs, ChattingObservation)), None
                )

                if chatting_observation:
                    anchor_message = chatting_observation.search_message_by_text(target)
                else:
                    anchor_message = None
            else:
                anchor_message = None

            # 如果没有找到锚点消息，创建一个占位符
            if not anchor_message:
                logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message.update_chat_stream(chat_stream)

            response_set = [
                (type, data),
            ]

            # 调用内部方法发送消息
            success = await expressor.send_response_messages(
                anchor_message=anchor_message,
                response_set=response_set,
                display_message=display_message,
            )

            return success
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送消息时出错: {e}")
            traceback.print_exc()
            return False

    async def send_message_by_expressor(self, text: str, target: Optional[str] = None) -> bool:
        """通过expressor发送文本消息的简化方法

        Args:
            text: 要发送的消息文本
            target: 目标消息（可选）

        Returns:
            bool: 是否发送成功
        """
        expressor: DefaultExpressor = self._services.get("expressor")
        chat_stream: ChatStream = self._services.get("chat_stream")

        if not expressor or not chat_stream:
            logger.error(f"{self.log_prefix} 无法发送消息：缺少必要的内部服务")
            return False

        # 构造简化的动作数据
        reply_data = {"text": text, "target": target or "", "emojis": []}

        # 获取锚定消息（如果有）
        observations = self._services.get("observations", [])

        # 查找 ChattingObservation 实例
        chatting_observation = None
        for obs in observations:
            if isinstance(obs, ChattingObservation):
                chatting_observation = obs
                break

        if not chatting_observation:
            logger.warning(f"{self.log_prefix} 未找到 ChattingObservation 实例，创建占位符")
            anchor_message = await create_empty_anchor_message(
                chat_stream.platform, chat_stream.group_info, chat_stream
            )
        else:
            anchor_message = chatting_observation.search_message_by_text(reply_data["target"])
            if not anchor_message:
                logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message.update_chat_stream(chat_stream)

        # 调用内部方法发送消息
        success, _ = await expressor.deal_reply(
            cycle_timers=self.cycle_timers,
            action_data=reply_data,
            anchor_message=anchor_message,
            reasoning=self.reasoning,
            thinking_id=self.thinking_id,
        )

        return success

    async def send_message_by_replyer(self, target: Optional[str] = None, extra_info_block: Optional[str] = None) -> bool:
        """通过replyer发送消息的简化方法

        Args:
            target: 目标消息（可选）
            extra_info_block: 额外信息块（可选）

        Returns:
            bool: 是否发送成功
        """
        replyer: DefaultReplyer = self._services.get("replyer")
        chat_stream: ChatStream = self._services.get("chat_stream")

        if not replyer or not chat_stream:
            logger.error(f"{self.log_prefix} 无法发送消息：缺少必要的内部服务")
            return False

        # 构造简化的动作数据
        reply_data = {"target": target or "", "extra_info_block": extra_info_block}

        # 获取锚定消息（如果有）
        observations = self._services.get("observations", [])

        # 查找 ChattingObservation 实例
        chatting_observation = None
        for obs in observations:
            if isinstance(obs, ChattingObservation):
                chatting_observation = obs
                break

        if not chatting_observation:
            logger.warning(f"{self.log_prefix} 未找到 ChattingObservation 实例，创建占位符")
            anchor_message = await create_empty_anchor_message(
                chat_stream.platform, chat_stream.group_info, chat_stream
            )
        else:
            anchor_message = chatting_observation.search_message_by_text(reply_data["target"])
            if not anchor_message:
                logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message.update_chat_stream(chat_stream)

        # 调用内部方法发送消息
        success, _ = await replyer.deal_reply(
            cycle_timers=self.cycle_timers,
            action_data=reply_data,
            anchor_message=anchor_message,
            reasoning=self.reasoning,
            thinking_id=self.thinking_id,
        )

        return success

    def get_chat_type(self) -> str:
        """获取当前聊天类型

        Returns:
            str: 聊天类型 ("group" 或 "private")
        """
        chat_stream: ChatStream = self._services.get("chat_stream")
        if chat_stream and hasattr(chat_stream, "group_info"):
            return "group" if chat_stream.group_info else "private"
        return "unknown"

    def get_recent_messages(self, count: int = 5) -> List[Dict[str, Any]]:
        """获取最近的消息

        Args:
            count: 要获取的消息数量

        Returns:
            List[Dict]: 消息列表，每个消息包含发送者、内容等信息
        """
        messages = []
        observations = self._services.get("observations", [])

        if observations and len(observations) > 0:
            obs = observations[0]
            if hasattr(obs, "get_talking_message"):
                obs: ObsInfo
                raw_messages = obs.get_talking_message()
                # 转换为简化格式
                for msg in raw_messages[-count:]:
                    simple_msg = {
                        "sender": msg.get("sender", "未知"),
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp", 0),
                    }
                    messages.append(simple_msg)

        return messages 