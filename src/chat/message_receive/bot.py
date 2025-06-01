import traceback
from typing import Dict, Any

from maim_message import BaseMessageInfo, MessageBase, Seg

from src.common.logger_manager import get_logger
from src.manager.mood_manager import mood_manager
from src.chat.focus_chat.heartflow_message_processor import HeartFCMessageReceiver
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager


# 配置主程序日志格式
logger = get_logger("chat")


class ChatBot:
    def __init__(self):
        self.bot = None  # bot 实例引用
        self._started = False
        self.mood_manager = mood_manager  # 获取情绪管理器单例
        self.heartflow_message_receiver = HeartFCMessageReceiver()  # 新增

    async def message_process(self, message_data: Dict[str, Any]) -> None:
        """处理转化后的统一格式消息

        根据配置信息和消息内容对消息数据进行预处理，并分发到合适的消息处理器中
        """
        try:
            # 将group_id和user_id转换为字符串
            # 此处的group_id和user_id都是基于PlatForm的id
            if message_data["message_info"].get("group_info") is not None:
                message_data["message_info"]["group_info"]["group_id"] = str(
                    message_data["message_info"]["group_info"]["group_id"]
                )
            message_data["message_info"]["user_info"]["user_id"] = str(
                message_data["message_info"]["user_info"]["user_id"]
            )

            logger.trace(f"预处理消息:{str(message_data)[:120]}...")

            message = MessageBase(
                BaseMessageInfo.from_dict(message_data.get("message_info", {})),
                Seg.from_dict(message_data.get("message_segment", {})),
                message_data.get("raw_message"),
            )
            group_id = message.message_info.group_info.group_id if message.message_info.group_info else None

            # 确认从接口发来的message是否有自定义的prompt模板信息
            if message.message_info.template_info and not message.message_info.template_info.template_default:
                template_group_name = message.message_info.template_info.template_name
                template_items = message.message_info.template_info.template_items
                async with global_prompt_manager.async_message_scope(template_group_name):
                    if isinstance(template_items, dict):
                        for k in template_items.keys():
                            await Prompt.create_async(template_items[k], k)
                            logger.debug(f"注册{template_items[k]},{k}")
            else:
                template_group_name = None

            async def preprocess():
                logger.trace("开始预处理消息...")
                # 如果在私聊中
                if group_id is None:
                    # TODO: PFC回归？
                    logger.trace("检测到私聊消息，进入普通心流私聊处理")
                    await self.heartflow_message_receiver.process_message(message)
                # 群聊默认进入心流消息处理逻辑
                else:
                    logger.trace(f"检测到群聊消息，群ID: {group_id}")
                    await self.heartflow_message_receiver.process_message(message)

            if template_group_name:
                async with global_prompt_manager.async_message_scope(template_group_name):
                    await preprocess()
            else:
                await preprocess()

        except Exception as e:
            logger.error(f"预处理消息失败: {e}")
            traceback.print_exc()


# 创建全局ChatBot实例
chat_bot = ChatBot()
