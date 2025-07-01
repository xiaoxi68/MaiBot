from typing import List, Optional, Union
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
from src.chat.message_receive.message import MessageThinking
from src.common.logger import get_logger
from src.person_info.person_info import PersonInfoManager, get_person_info_manager
from src.chat.utils.utils import process_llm_response
from src.plugin_system.apis import generator_api
from src.chat.focus_chat.memory_activator import MemoryActivator


logger = get_logger("normal_chat_response")


class NormalChatGenerator:
    def __init__(self):
        model_config_1 = global_config.model.replyer_1.copy()
        model_config_2 = global_config.model.replyer_2.copy()

        prob_first = global_config.normal_chat.normal_chat_first_probability
        
        model_config_1['weight'] = prob_first
        model_config_2['weight'] = 1.0 - prob_first

        self.model_configs = [model_config_1, model_config_2]
        
        self.model_sum = LLMRequest(model=global_config.model.memory_summary, temperature=0.7, request_type="relation")
        self.memory_activator = MemoryActivator()

    async def generate_response(
        self,
        message: MessageThinking,
        available_actions=None,
    ):
        logger.info(
            f"NormalChat思考:{message.processed_plain_text[:30] + '...' if len(message.processed_plain_text) > 30 else message.processed_plain_text}"
        )
        person_id = PersonInfoManager.get_person_id(
            message.chat_stream.user_info.platform, message.chat_stream.user_info.user_id
        )
        person_info_manager = get_person_info_manager()
        person_name = await person_info_manager.get_value(person_id, "person_name")
        relation_info = await person_info_manager.get_value(person_id, "short_impression")
        reply_to_str = f"{person_name}:{message.processed_plain_text}"
        
        structured_info = ""

        try:
            success, reply_set, prompt = await generator_api.generate_reply(
                chat_stream=message.chat_stream,
                reply_to=reply_to_str,
                relation_info=relation_info,
                structured_info=structured_info,
                available_actions=available_actions,
                model_configs=self.model_configs,
                request_type="normal.replyer",
                return_prompt=True
            )

            if not success or not reply_set:
                logger.info(f"对 {message.processed_plain_text} 的回复生成失败")
                return None

            content = " ".join([item[1] for item in reply_set if item[0] == "text"])
            logger.debug(f"对 {message.processed_plain_text} 的回复：{content}")
            
            if content:
                logger.info(f"{global_config.bot.nickname}的备选回复是：{content}")
                content = process_llm_response(content)

            return content

        except Exception:
            logger.exception("生成回复时出错")
            return None

        return content

    async def _get_emotion_tags(self, content: str, processed_plain_text: str):
        """提取情感标签，结合立场和情绪"""
        try:
            # 构建提示词，结合回复内容、被回复的内容以及立场分析
            prompt = f"""
            请严格根据以下对话内容，完成以下任务：
            1. 判断回复者对被回复者观点的直接立场：
            - "支持"：明确同意或强化被回复者观点
            - "反对"：明确反驳或否定被回复者观点
            - "中立"：不表达明确立场或无关回应
            2. 从"开心,愤怒,悲伤,惊讶,平静,害羞,恐惧,厌恶,困惑"中选出最匹配的1个情感标签
            3. 按照"立场-情绪"的格式直接输出结果，例如："反对-愤怒"
            4. 考虑回复者的人格设定为{global_config.personality.personality_core}

            对话示例：
            被回复：「A就是笨」
            回复：「A明明很聪明」 → 反对-愤怒

            当前对话：
            被回复：「{processed_plain_text}」
            回复：「{content}」

            输出要求：
            - 只需输出"立场-情绪"结果，不要解释
            - 严格基于文字直接表达的对立关系判断
            """

            # 调用模型生成结果
            result, (reasoning_content, model_name) = await self.model_sum.generate_response_async(prompt)
            result = result.strip()

            # 解析模型输出的结果
            if "-" in result:
                stance, emotion = result.split("-", 1)
                valid_stances = ["支持", "反对", "中立"]
                valid_emotions = ["开心", "愤怒", "悲伤", "惊讶", "害羞", "平静", "恐惧", "厌恶", "困惑"]
                if stance in valid_stances and emotion in valid_emotions:
                    return stance, emotion  # 返回有效的立场-情绪组合
                else:
                    logger.debug(f"无效立场-情感组合:{result}")
                    return "中立", "平静"  # 默认返回中立-平静
            else:
                logger.debug(f"立场-情感格式错误:{result}")
                return "中立", "平静"  # 格式错误时返回默认值

        except Exception as e:
            logger.debug(f"获取情感标签时出错: {e}")
            return "中立", "平静"  # 出错时返回默认值
