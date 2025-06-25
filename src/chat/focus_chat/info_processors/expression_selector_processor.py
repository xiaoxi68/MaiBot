import time
import random
from typing import List
from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.heart_flow.observation.observation import Observation
from src.common.logger import get_logger
from src.chat.message_receive.chat_stream import get_chat_manager
from .base_processor import BaseProcessor
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.expression_selection_info import ExpressionSelectionInfo
from src.chat.express.expression_selector import expression_selector

logger = get_logger("processor")


class ExpressionSelectorProcessor(BaseProcessor):
    log_prefix = "表达选择器"

    def __init__(self, subheartflow_id: str):
        super().__init__()

        self.subheartflow_id = subheartflow_id
        self.last_selection_time = 0
        self.selection_interval = 10  # 40秒间隔
        self.cached_expressions = []  # 缓存上一次选择的表达方式


        name = get_chat_manager().get_stream_name(self.subheartflow_id)
        self.log_prefix = f"[{name}] 表达选择器"

    async def process_info(self, observations: List[Observation] = None, *infos) -> List[InfoBase]:
        """处理信息对象

        Args:
            observations: 观察对象列表

        Returns:
            List[InfoBase]: 处理后的表达选择信息列表
        """
        current_time = time.time()

        # 检查频率限制
        if current_time - self.last_selection_time < self.selection_interval:
            logger.debug(f"{self.log_prefix} 距离上次选择不足{self.selection_interval}秒，使用缓存的表达方式")
            # 使用缓存的表达方式
            if self.cached_expressions:
                # 从缓存的15个中随机选5个
                final_expressions = random.sample(self.cached_expressions, min(5, len(self.cached_expressions)))

                # 创建表达选择信息
                expression_info = ExpressionSelectionInfo()
                expression_info.set_selected_expressions(final_expressions)

                logger.info(f"{self.log_prefix} 使用缓存选择了{len(final_expressions)}个表达方式")
                return [expression_info]
            else:
                logger.debug(f"{self.log_prefix} 没有缓存的表达方式，跳过选择")
                return []

        # 获取聊天内容
        chat_info = ""
        if observations:
            for observation in observations:
                if isinstance(observation, ChattingObservation):
                    # chat_info = observation.get_observe_info()
                    chat_info = observation.talking_message_str_truncate_short
                    break

        if not chat_info:
            logger.debug(f"{self.log_prefix} 没有聊天内容，跳过表达方式选择")
            return []

        try:
            # LLM模式：调用LLM选择5-10个，然后随机选5个
            selected_expressions = await expression_selector.select_suitable_expressions_llm(self.subheartflow_id, chat_info)
            cache_size = len(selected_expressions) if selected_expressions else 0
            mode_desc = f"LLM模式（已缓存{cache_size}个）"

            if selected_expressions:
                self.cached_expressions = selected_expressions
                self.last_selection_time = current_time

                # 创建表达选择信息
                expression_info = ExpressionSelectionInfo()
                expression_info.set_selected_expressions(selected_expressions)

                logger.info(f"{self.log_prefix} 为当前聊天选择了{len(selected_expressions)}个表达方式（{mode_desc}）")
                return [expression_info]
            else:
                logger.debug(f"{self.log_prefix} 未选择任何表达方式")
                return []

        except Exception as e:
            logger.error(f"{self.log_prefix} 处理表达方式选择时出错: {e}")
            return []

