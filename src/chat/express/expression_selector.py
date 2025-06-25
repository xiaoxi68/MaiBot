from .exprssion_learner import get_expression_learner
import random
from typing import List, Dict, Tuple
from json_repair import repair_json
import json
import os
import time
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
from src.common.logger import get_logger
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager

logger = get_logger("expression_selector")


def init_prompt():
    expression_evaluation_prompt = """
你的名字是{bot_name}

以下是正在进行的聊天内容：
{chat_observe_info}

以下是可选的表达情境：
{all_situations}

请你分析聊天内容的语境、情绪、话题类型，从上述情境中选择最适合当前聊天情境的{min_num}-{max_num}个情境。
考虑因素包括：
1. 聊天的情绪氛围（轻松、严肃、幽默等）
2. 话题类型（日常、技术、游戏、情感等）
3. 情境与当前语境的匹配度

请以JSON格式输出，只需要输出选中的情境编号：
例如：
{{
    "selected_situations": [2, 3, 5, 7, 19, 22, 25, 38, 39, 45, 48 , 64]
}}
例如：
{{
    "selected_situations": [1, 4, 7, 9, 23, 38, 44]
}}

请严格按照JSON格式输出，不要包含其他内容：
"""
    Prompt(expression_evaluation_prompt, "expression_evaluation_prompt")


def weighted_sample(population: List[Dict], weights: List[float], k: int) -> List[Dict]:
    """按权重随机抽样"""
    if not population or not weights or k <= 0:
        return []

    if len(population) <= k:
        return population.copy()

    # 使用累积权重的方法进行加权抽样
    selected = []
    population_copy = population.copy()
    weights_copy = weights.copy()

    for _ in range(k):
        if not population_copy:
            break

        # 选择一个元素
        chosen_idx = random.choices(range(len(population_copy)), weights=weights_copy)[0]
        selected.append(population_copy.pop(chosen_idx))
        weights_copy.pop(chosen_idx)

    return selected


class ExpressionSelector:
    def __init__(self):
        self.expression_learner = get_expression_learner()
        # TODO: API-Adapter修改标记
        self.llm_model = LLMRequest(
            model=global_config.model.utils_small,
            request_type="expression.selector",
        )

    def get_random_expressions(
        self, chat_id: str, style_num: int, grammar_num: int, personality_num: int
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        (
            learnt_style_expressions,
            learnt_grammar_expressions,
            personality_expressions,
        ) = self.expression_learner.get_expression_by_chat_id(chat_id)

        # 按权重抽样（使用count作为权重）
        if learnt_style_expressions:
            style_weights = [expr.get("count", 1) for expr in learnt_style_expressions]
            selected_style = weighted_sample(learnt_style_expressions, style_weights, style_num)
        else:
            selected_style = []

        if learnt_grammar_expressions:
            grammar_weights = [expr.get("count", 1) for expr in learnt_grammar_expressions]
            selected_grammar = weighted_sample(learnt_grammar_expressions, grammar_weights, grammar_num)
        else:
            selected_grammar = []

        if personality_expressions:
            personality_weights = [expr.get("count", 1) for expr in personality_expressions]
            selected_personality = weighted_sample(personality_expressions, personality_weights, personality_num)
        else:
            selected_personality = []

        return selected_style, selected_grammar, selected_personality

    def update_expression_count(self, chat_id: str, expression: Dict[str, str], increment: float = 0.1):
        """更新表达方式的count值

        Args:
            chat_id: 聊天ID
            expression: 表达方式字典
            increment: 增量值，默认0.1
        """
        if expression.get("type") == "style_personality":
            # personality表达方式存储在全局文件中
            file_path = os.path.join("data", "expression", "personality", "expressions.json")
        else:
            # style和grammar表达方式存储在对应chat_id目录中
            expr_type = expression.get("type", "style")
            if expr_type == "style":
                file_path = os.path.join("data", "expression", "learnt_style", str(chat_id), "expressions.json")
            elif expr_type == "grammar":
                file_path = os.path.join("data", "expression", "learnt_grammar", str(chat_id), "expressions.json")
            else:
                return

        if not os.path.exists(file_path):
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                expressions = json.load(f)

            # 找到匹配的表达方式并更新count
            for expr in expressions:
                if expr.get("situation") == expression.get("situation") and expr.get("style") == expression.get(
                    "style"
                ):
                    current_count = expr.get("count", 1)

                    # 简单加0.1，但限制最高为5
                    new_count = min(current_count + increment, 5.0)
                    expr["count"] = new_count
                    expr["last_active_time"] = time.time()

                    logger.info(f"表达方式激活: 原count={current_count:.3f}, 增量={increment}, 新count={new_count:.3f}")
                    break

            # 保存更新后的文件
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(expressions, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"更新表达方式count失败: {e}")

    async def select_suitable_expressions_llm(
        self, chat_id: str, chat_info: str, max_num: int = 10, min_num: int = 5
    ) -> List[Dict[str, str]]:
        """使用LLM选择适合的表达方式"""

        # 1. 获取35个随机表达方式（现在按权重抽取）
        style_exprs, grammar_exprs, personality_exprs = self.get_random_expressions(chat_id, 25, 25, 10)

        # 2. 构建所有表达方式的索引和情境列表
        all_expressions = []
        all_situations = []

        # 添加style表达方式
        for expr in style_exprs:
            if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                expr_with_type = expr.copy()
                expr_with_type["type"] = "style"
                all_expressions.append(expr_with_type)
                all_situations.append(f"{len(all_expressions)}.{expr['situation']}")

        # 添加grammar表达方式
        for expr in grammar_exprs:
            if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                expr_with_type = expr.copy()
                expr_with_type["type"] = "grammar"
                all_expressions.append(expr_with_type)
                all_situations.append(f"{len(all_expressions)}.{expr['situation']}")

        # 添加personality表达方式
        for expr in personality_exprs:
            if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                expr_with_type = expr.copy()
                expr_with_type["type"] = "style_personality"
                all_expressions.append(expr_with_type)
                all_situations.append(f"{len(all_expressions)}.{expr['situation']}")

        if not all_expressions:
            logger.warning("没有找到可用的表达方式")
            return []

        all_situations_str = "\n".join(all_situations)

        # 3. 构建prompt（只包含情境，不包含完整的表达方式）
        prompt = (await global_prompt_manager.get_prompt_async("expression_evaluation_prompt")).format(
            bot_name=global_config.bot.nickname,
            chat_observe_info=chat_info,
            all_situations=all_situations_str,
            min_num=min_num,
            max_num=max_num,
        )

        # 4. 调用LLM
        try:
            content, (_, _) = await self.llm_model.generate_response_async(prompt=prompt)

            # logger.info(f"{self.log_prefix} LLM返回结果: {content}")

            if not content:
                logger.warning("LLM返回空结果")
                return []

            # 5. 解析结果
            result = repair_json(content)
            if isinstance(result, str):
                result = json.loads(result)

            if not isinstance(result, dict) or "selected_situations" not in result:
                logger.error("LLM返回格式错误")
                return []

            selected_indices = result["selected_situations"]

            # 根据索引获取完整的表达方式
            valid_expressions = []
            for idx in selected_indices:
                if isinstance(idx, int) and 1 <= idx <= len(all_expressions):
                    expression = all_expressions[idx - 1]  # 索引从1开始
                    valid_expressions.append(expression)

                    # 对选中的表达方式count数+0.1
                    self.update_expression_count(chat_id, expression, 0.001)

            # logger.info(f"LLM从{len(all_expressions)}个情境中选择了{len(valid_expressions)}个")
            return valid_expressions

        except Exception as e:
            logger.error(f"LLM处理表达方式选择时出错: {e}")
            return []


init_prompt()

try:
    expression_selector = ExpressionSelector()
except Exception as e:
    print(f"ExpressionSelector初始化失败: {e}")
