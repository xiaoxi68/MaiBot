import math
import random

from src.chat.message_receive.message import MessageRecv
from src.llm_models.utils_model import LLMRequest
from ..common.logger import get_logger
from src.chat.utils.chat_message_builder import build_readable_messages, get_raw_msg_by_timestamp_with_chat_inclusive
from src.config.config import global_config
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
logger = get_logger("mood")

def init_prompt():
    Prompt(
        """
{chat_talking_prompt}
以上是群里正在进行的聊天记录

{indentify_block}
你刚刚的情绪状态是：{mood_state}

现在，发送了消息，引起了你的注意，你对其进行了阅读和思考，请你输出一句话描述你新的情绪状态
请只输出情绪状态，不要输出其他内容：
""",
        "change_mood_prompt",
    )

class ChatMood:
    def __init__(self,chat_id:str):
        self.chat_id:str = chat_id
        self.mood_state:str = "感觉很平静"
        
        
        self.mood_model = LLMRequest(
            model=global_config.model.utils,
            temperature=0.7,
            request_type="mood",
        )
        
        self.last_change_time = 0
        
    async def update_mood_by_message(self,message:MessageRecv,interested_rate:float):
        
        during_last_time = message.message_info.time - self.last_change_time
        
        base_probability = 0.05
        time_multiplier = 4 * (1 - math.exp(-0.01 * during_last_time))

        if interested_rate <= 0:
            interest_multiplier = 0
        else:
            interest_multiplier = 3 * math.pow(interested_rate, 0.25)
            
        logger.info(f"base_probability: {base_probability}, time_multiplier: {time_multiplier}, interest_multiplier: {interest_multiplier}")
        update_probability = min(1.0, base_probability * time_multiplier * interest_multiplier)

        if random.random() > update_probability:
            return
        
        
        
        message_time = message.message_info.time
        message_list_before_now = get_raw_msg_by_timestamp_with_chat_inclusive(
            chat_id=self.chat_id,
            timestamp_start=self.last_change_time,
            timestamp_end=message_time,
            limit=15,
            limit_mode="last",
        )
        chat_talking_prompt = build_readable_messages(
            message_list_before_now,
            replace_bot_name=True,
            merge_messages=False,
            timestamp_mode="normal_no_YMD",
            read_mark=0.0,
            truncate=True,
            show_actions=True,
        )
        
        
        bot_name = global_config.bot.nickname
        if global_config.bot.alias_names:
            bot_nickname = f",也有人叫你{','.join(global_config.bot.alias_names)}"
        else:
            bot_nickname = ""

        prompt_personality = global_config.personality.personality_core
        indentify_block = f"你的名字是{bot_name}{bot_nickname}，你{prompt_personality}："
        
        prompt = await global_prompt_manager.format_prompt(
            "change_mood_prompt",
            chat_talking_prompt=chat_talking_prompt,
            indentify_block=indentify_block,
            mood_state=self.mood_state,
        )
        
        logger.info(f"prompt: {prompt}")
        response, (reasoning_content, model_name) = await self.mood_model.generate_response_async(prompt=prompt)
        logger.info(f"response: {response}")
        logger.info(f"reasoning_content: {reasoning_content}")
        
        
        self.mood_state = response
        
        
        self.last_change_time = message_time
        
        
class MoodManager:

    def __init__(self):
        self.mood_list:list[ChatMood] = []
        """当前情绪状态"""
        
    def get_mood_by_chat_id(self, chat_id:str) -> ChatMood:
        for mood in self.mood_list:
            if mood.chat_id == chat_id:
                return mood
        
        new_mood = ChatMood(chat_id)
        self.mood_list.append(new_mood)
        return new_mood
    
    def reset_mood_by_chat_id(self, chat_id:str):
        for mood in self.mood_list:
            if mood.chat_id == chat_id:
                mood.mood_state = "感觉很平静"
                return
        self.mood_list.append(ChatMood(chat_id))

    

init_prompt()

mood_manager = MoodManager()
"""全局情绪管理器"""
