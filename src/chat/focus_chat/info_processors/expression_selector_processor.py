import time
import random
from typing import List, Dict
from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.heart_flow.observation.observation import Observation
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
from src.common.logger import get_logger
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.message_receive.chat_stream import get_chat_manager
from .base_processor import BaseProcessor
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.expression_selection_info import ExpressionSelectionInfo
from src.chat.express.exprssion_learner import get_expression_learner
from json_repair import repair_json
import json

logger = get_logger("processor")


def weighted_sample_no_replacement(items, weights, k) -> list:
    """
    加权随机抽样，不允许重复

    Args:
        items: 待抽样的项目列表
        weights: 对应项目的权重列表
        k: 抽样数量

    Returns:
        抽样结果列表
    """
    if not items or k <= 0:
        return []

    k = min(k, len(items))
    selected = []
    remaining_items = list(items)
    remaining_weights = list(weights)

    for _ in range(k):
        if not remaining_items:
            break

        # 计算累积权重
        total_weight = sum(remaining_weights)
        if total_weight <= 0:
            # 如果权重都为0或负数，则随机选择
            selected_index = random.randint(0, len(remaining_items) - 1)
        else:
            # 加权随机选择
            rand_val = random.uniform(0, total_weight)
            cumulative_weight = 0
            selected_index = 0
            for i, weight in enumerate(remaining_weights):
                cumulative_weight += weight
                if rand_val <= cumulative_weight:
                    selected_index = i
                    break

        # 添加选中的项目
        selected.append(remaining_items[selected_index])
        # 移除已选中的项目
        remaining_items.pop(selected_index)
        remaining_weights.pop(selected_index)

    return selected


def init_prompt():
    expression_evaluation_prompt = """
你的名字是{bot_name}

以下是正在进行的聊天内容：
{chat_observe_info}

以下是可选的表达情境：
{all_situations}

请你分析聊天内容的语境、情绪、话题类型，从上述情境中选择最适合当前聊天情境的10个情境。
考虑因素包括：
1. 聊天的情绪氛围（轻松、严肃、幽默等）
2. 话题类型（日常、技术、游戏、情感等）
3. 情境与当前语境的匹配度

请以JSON格式输出，只需要输出选中的情境编号：
{{
    "selected_situations": [1, 3, 5, 7, 9, 12, 15, 18, 21, 25]
}}

请严格按照JSON格式输出，不要包含其他内容：
"""
    Prompt(expression_evaluation_prompt, "expression_evaluation_prompt")


class ExpressionSelectorProcessor(BaseProcessor):
    log_prefix = "表达选择器"

    def __init__(self, subheartflow_id: str):
        super().__init__()

        self.subheartflow_id = subheartflow_id
        self.last_selection_time = 0
        self.selection_interval = 60  # 1分钟间隔
        self.cached_expressions = []  # 缓存上一次选择的表达方式

        # 表达方式选择模式
        self.selection_mode = getattr(global_config.expression, "selection_mode", "llm")  # "llm" 或 "random"

        self.llm_model = LLMRequest(
            model=global_config.model.utils_small,
            request_type="focus.processor.expression_selector",
        )

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
                    chat_info = observation.get_observe_info()
                    break

        if not chat_info:
            logger.debug(f"{self.log_prefix} 没有聊天内容，跳过表达方式选择")
            return []

        try:
            # 根据模式选择表达方式
            if self.selection_mode == "llm":
                # LLM模式：调用LLM选择15个，然后随机选5个
                selected_expressions = await self._select_suitable_expressions_llm(chat_info)
                cache_size = len(selected_expressions) if selected_expressions else 0
                mode_desc = f"LLM模式（已缓存{cache_size}个）"
            else:
                # 随机模式：直接随机选择5个
                selected_expressions = await self._select_suitable_expressions_random(chat_info)
                cache_size = len(selected_expressions) if selected_expressions else 0
                mode_desc = f"随机模式（已缓存{cache_size}个）"

            if selected_expressions:
                # 缓存选择的表达方式
                self.cached_expressions = selected_expressions
                # 更新最后选择时间
                self.last_selection_time = current_time

                # 从选择的表达方式中随机选5个
                final_expressions = random.sample(selected_expressions, min(4, len(selected_expressions)))

                # 创建表达选择信息
                expression_info = ExpressionSelectionInfo()
                expression_info.set_selected_expressions(final_expressions)

                logger.info(f"{self.log_prefix} 为当前聊天选择了{len(final_expressions)}个表达方式（{mode_desc}）")
                return [expression_info]
            else:
                logger.debug(f"{self.log_prefix} 未选择任何表达方式")
                return []

        except Exception as e:
            logger.error(f"{self.log_prefix} 处理表达方式选择时出错: {e}")
            return []

    async def _get_random_expressions(self) -> tuple[List[Dict], List[Dict], List[Dict]]:
        """随机获取表达方式：20个style，20个grammar，20个personality"""
        expression_learner = get_expression_learner()

        # 获取所有表达方式
        (
            learnt_style_expressions,
            learnt_grammar_expressions,
            personality_expressions,
        ) = await expression_learner.get_expression_by_chat_id(self.subheartflow_id)

        # 随机选择
        selected_style = random.sample(learnt_style_expressions, min(15, len(learnt_style_expressions)))
        selected_grammar = random.sample(learnt_grammar_expressions, min(15, len(learnt_grammar_expressions)))
        selected_personality = random.sample(personality_expressions, min(5, len(personality_expressions)))

        return selected_style, selected_grammar, selected_personality

    async def _select_suitable_expressions_llm(self, chat_info: str) -> List[Dict[str, str]]:
        """使用LLM选择适合的表达方式"""

        # 1. 获取35个随机表达方式
        style_exprs, grammar_exprs, personality_exprs = await self._get_random_expressions()

        # 2. 构建所有表达方式的索引和情境列表
        all_expressions = []
        all_situations = []

        # 添加style表达方式
        for expr in style_exprs:
            if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                expr_with_type = expr.copy()
                expr_with_type["type"] = "style"
                all_expressions.append(expr_with_type)
                all_situations.append(f"{len(all_expressions)}. [语言风格] {expr['situation']}")

        # 添加grammar表达方式
        for expr in grammar_exprs:
            if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                expr_with_type = expr.copy()
                expr_with_type["type"] = "grammar"
                all_expressions.append(expr_with_type)
                all_situations.append(f"{len(all_expressions)}. [句法语法] {expr['situation']}")

        # 添加personality表达方式
        for expr in personality_exprs:
            if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                expr_with_type = expr.copy()
                expr_with_type["type"] = "personality"
                all_expressions.append(expr_with_type)
                all_situations.append(f"{len(all_expressions)}. [个性表达] {expr['situation']}")

        if not all_expressions:
            logger.warning(f"{self.log_prefix} 没有找到可用的表达方式")
            return []

        all_situations_str = "\n".join(all_situations)

        # 3. 构建prompt（只包含情境，不包含完整的表达方式）
        prompt = (await global_prompt_manager.get_prompt_async("expression_evaluation_prompt")).format(
            bot_name=global_config.bot.nickname,
            chat_observe_info=chat_info,
            all_situations=all_situations_str,
        )

        # 4. 调用LLM
        try:
            content, _ = await self.llm_model.generate_response_async(prompt=prompt)

            # logger.info(f"{self.log_prefix} LLM返回结果: {content}")

            if not content:
                logger.warning(f"{self.log_prefix} LLM返回空结果")
                return []

            # 5. 解析结果
            result = repair_json(content)
            if isinstance(result, str):
                result = json.loads(result)

            if not isinstance(result, dict) or "selected_situations" not in result:
                logger.error(f"{self.log_prefix} LLM返回格式错误")
                return []

            selected_indices = result["selected_situations"]

            # 根据索引获取完整的表达方式
            valid_expressions = []
            for idx in selected_indices:
                if isinstance(idx, int) and 1 <= idx <= len(all_expressions):
                    valid_expressions.append(all_expressions[idx - 1])  # 索引从1开始

            logger.info(f"{self.log_prefix} LLM从{len(all_expressions)}个情境中选择了{len(valid_expressions)}个")
            return valid_expressions

        except Exception as e:
            logger.error(f"{self.log_prefix} LLM处理表达方式选择时出错: {e}")
            return []

    async def _select_suitable_expressions_random(self, chat_info: str) -> List[Dict[str, str]]:
        """随机选择表达方式（原replyer逻辑）"""

        # 获取所有表达方式
        expression_learner = get_expression_learner()
        (
            learnt_style_expressions,
            learnt_grammar_expressions,
            personality_expressions,
        ) = await expression_learner.get_expression_by_chat_id(self.subheartflow_id)

        selected_expressions = []

        # 1. learnt_style_expressions相似度匹配选择3条
        if learnt_style_expressions:
            similar_exprs = self._find_similar_expressions(chat_info, learnt_style_expressions, 3)
            for expr in similar_exprs:
                if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                    expr_copy = expr.copy()
                    expr_copy["type"] = "style"
                    selected_expressions.append(expr_copy)

        # 2. learnt_grammar_expressions加权随机选2条
        if learnt_grammar_expressions:
            weights = [expr.get("count", 1) for expr in learnt_grammar_expressions]
            selected_learnt = weighted_sample_no_replacement(learnt_grammar_expressions, weights, 2)
            for expr in selected_learnt:
                if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                    expr_copy = expr.copy()
                    expr_copy["type"] = "grammar"
                    selected_expressions.append(expr_copy)

        # 3. personality_expressions随机选1条
        if personality_expressions:
            expr = random.choice(personality_expressions)
            if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                expr_copy = expr.copy()
                expr_copy["type"] = "personality"
                selected_expressions.append(expr_copy)

        logger.info(f"{self.log_prefix} 随机模式选择了{len(selected_expressions)}个表达方式")
        return selected_expressions

    def _find_similar_expressions(self, input_text: str, expressions: List[Dict], top_k: int = 3) -> List[Dict]:
        """使用简单的文本匹配找出相似的表达方式（简化版，避免依赖sklearn）"""
        if not expressions or not input_text:
            return random.sample(expressions, min(top_k, len(expressions))) if expressions else []

        # 简单的关键词匹配
        scored_expressions = []
        input_words = set(input_text.lower().split())

        for expr in expressions:
            situation = expr.get("situation", "").lower()
            situation_words = set(situation.split())

            # 计算交集大小作为相似度
            similarity = len(input_words & situation_words)
            scored_expressions.append((similarity, expr))

        # 按相似度排序
        scored_expressions.sort(key=lambda x: x[0], reverse=True)

        # 如果没有匹配的，随机选择
        if all(score == 0 for score, _ in scored_expressions):
            return random.sample(expressions, min(top_k, len(expressions)))

        # 返回top_k个最相似的
        return [expr for _, expr in scored_expressions[:top_k]]


init_prompt()
