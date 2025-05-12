import time
from typing import List, Dict, Optional, Any, Tuple, Coroutine
from src.common.logger_manager import get_logger
from src.plugins.models.utils_model import LLMRequest
from src.config.config import global_config
from src.plugins.utils.chat_message_builder import get_raw_msg_by_timestamp_random, build_readable_messages
from src.plugins.heartFC_chat.heartflow_prompt_builder import Prompt, global_prompt_manager
import os
import json

logger = get_logger("expressor")


def init_prompt() -> None:
    learn_expression_prompt = """
{chat_str}

请从上面这段群聊中概括除了人名为"麦麦"之外的人的语言风格，只考虑文字，不要考虑表情包和图片
不要涉及具体的人名，只考虑语言风格
思考回复语法，长度和情感
思考有没有特殊的梗，一并总结成语言风格
总结成如下格式的规律，总结的内容要详细，但具有概括性：
当"xxx"时，可以"xxx", xxx不超过10个字

例如：
当"表示十分惊叹"时，使用"我嘞个xxxx"
当"表示讽刺的赞同，不想讲道理"时，使用"对对对"
当"想表达某个观点，但不想明说"，使用"反讽"
当"想说明某个观点，但懒得明说"，使用"懂的都懂"

现在请你概括
"""
    Prompt(learn_expression_prompt, "learn_expression_prompt")


class ExpressionLearner:
    def __init__(self) -> None:
        self.express_learn_model: LLMRequest = LLMRequest(
            model=global_config.llm_normal,
            temperature=global_config.llm_normal["temp"],
            max_tokens=256,
            request_type="response_heartflow",
        )

    async def get_expression_by_chat_id(self, chat_id: str) -> List[Dict[str, str]]:
        """从/data/expression/对应chat_id/expressions.json中读取表达方式"""
        file_path: str = os.path.join("data", "expression", str(chat_id), "expressions.json")
        if not os.path.exists(file_path):
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            expressions: List[dict] = json.load(f)
        return expressions

    async def learn_and_store_expression(self) -> List[Tuple[str, str, str]]:
        """选择从当前到最近1小时内的随机10条消息，然后学习这些消息的表达方式"""
        logger.info("开始学习表达方式...")
        expressions: Optional[List[Tuple[str, str, str]]] = await self.learn_expression()
        logger.info(f"学习到{len(expressions) if expressions else 0}条表达方式")
        # expressions: List[(chat_id, situation, style)]
        if not expressions:
            logger.info("没有学习到表达方式")
            return []
        # 按chat_id分组
        chat_dict: Dict[str, List[Dict[str, str]]] = {}
        for chat_id, situation, style in expressions:
            if chat_id not in chat_dict:
                chat_dict[chat_id] = []
            chat_dict[chat_id].append({"situation": situation, "style": style})
        # 存储到/data/expression/对应chat_id/expressions.json
        for chat_id, expr_list in chat_dict.items():
            dir_path = os.path.join("data", "expression", str(chat_id))
            os.makedirs(dir_path, exist_ok=True)
            file_path = os.path.join(dir_path, "expressions.json")
            # 若已存在，先读出合并
            if os.path.exists(file_path):
                old_data: List[Dict[str, str]] = []
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        old_data = json.load(f)
                except Exception:
                    old_data = []
                expr_list = old_data + expr_list
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(expr_list, f, ensure_ascii=False, indent=2)
        return expressions

    async def learn_expression(self) -> Optional[List[Tuple[str, str, str]]]:
        """选择从当前到最近1小时内的随机10条消息，然后学习这些消息的表达方式

        Args:
            chat_stream (ChatStream): _description_
        """
        current_time = time.time()
        random_msg: Optional[List[Dict[str, Any]]] = get_raw_msg_by_timestamp_random(current_time - 3600 * 24, current_time, limit=10)
        if not random_msg:
            return None
        # 转化成str
        chat_id: str = random_msg[0]["chat_id"]
        random_msg_str: str = await build_readable_messages(random_msg, timestamp_mode="normal")

        prompt: str = await global_prompt_manager.format_prompt(
            "learn_expression_prompt",
            chat_str=random_msg_str,
        )
        
        logger.info(f"学习表达方式的prompt: {prompt}")

        response, _ = await self.express_learn_model.generate_response_async(prompt)
        
        logger.info(f"学习表达方式的response: {response}")

        expressions: List[Tuple[str, str, str]] = self.parse_expression_response(response, chat_id)

        return expressions

    def parse_expression_response(self, response: str, chat_id: str) -> List[Tuple[str, str, str]]:
        """
        解析LLM返回的表达风格总结，每一行提取"当"和"使用"之间的内容，存储为(situation, style)元组
        """
        expressions: List[Tuple[str, str, str]] = []
        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue
            # 查找"当"和下一个引号
            idx_when = line.find('当"')
            if idx_when == -1:
                continue
            idx_quote1 = idx_when + 1
            idx_quote2 = line.find('"', idx_quote1 + 1)
            if idx_quote2 == -1:
                continue
            situation = line[idx_quote1 + 1 : idx_quote2]
            # 查找"使用"
            idx_use = line.find('使用"', idx_quote2)
            if idx_use == -1:
                continue
            idx_quote3 = idx_use + 2
            idx_quote4 = line.find('"', idx_quote3 + 1)
            if idx_quote4 == -1:
                continue
            style = line[idx_quote3 + 1 : idx_quote4]
            expressions.append((chat_id, situation, style))
        return expressions

init_prompt()

expression_learner = ExpressionLearner()
