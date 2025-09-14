import traceback
import time
import asyncio
import random
import re

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from src.mais4u.mai_think import mai_thinking_manager
from src.common.logger import get_logger
from src.common.data_models.database_data_model import DatabaseMessages
from src.common.data_models.info_data_model import ActionPlannerInfo
from src.common.data_models.llm_data_model import LLMGenerationDataModel
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest
from src.chat.message_receive.message import UserInfo, Seg, MessageRecv, MessageSending
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.message_receive.uni_message_sender import UniversalMessageSender
from src.chat.utils.timer_calculator import Timer  # <--- Import Timer
from src.chat.utils.utils import get_chat_type_and_target_info
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.utils.chat_message_builder import (
    build_readable_messages,
    get_raw_msg_before_timestamp_with_chat,
    replace_user_references,
)
from src.chat.express.expression_selector import expression_selector
# from src.chat.memory_system.memory_activator import MemoryActivator
from src.mood.mood_manager import mood_manager
from src.person_info.person_info import Person, is_person_known
from src.plugin_system.base.component_types import ActionInfo, EventType
from src.plugin_system.apis import llm_api



def init_replyer_prompt():
    Prompt("你正在qq群里聊天，下面是群里正在聊的内容:", "chat_target_group1")
    Prompt("你正在和{sender_name}聊天，这是你们之前聊的内容：", "chat_target_private1")
    Prompt("正在群里聊天", "chat_target_group2")
    Prompt("和{sender_name}聊天", "chat_target_private2")

    Prompt(
        """
{expression_habits_block}
{relation_info_block}

{chat_target}
{time_block}
{chat_info}
{identity}

你现在的心情是：{mood_state}
你正在{chat_target_2},{reply_target_block}
你想要对上述的发言进行回复，回复的具体内容（原句）是：{raw_reply}
原因是：{reason}
现在请你将这条具体内容改写成一条适合在群聊中发送的回复消息。
你需要使用合适的语法和句法，参考聊天内容，组织一条日常且口语化的回复。请你修改你想表达的原句，符合你的表达风格和语言习惯
{reply_style}
你可以完全重组回复，保留最基本的表达含义就好，但重组后保持语意通顺。
{keywords_reaction_prompt}
{moderation_prompt}
不要输出多余内容(包括前后缀，冒号和引号，括号，表情包，emoji,at或 @等 )，只输出一条回复就好。
现在，你说：
""",
        "default_expressor_prompt",
    )




    Prompt(
"""{knowledge_prompt}{relation_info_block}{tool_info_block}{extra_info_block}
{expression_habits_block}

你正在qq群里聊天，下面是群里正在聊的内容:
{time_block}
{background_dialogue_prompt}
{core_dialogue_prompt}

{reply_target_block}。
{identity}
你正在群里聊天,现在请你读读之前的聊天记录，然后给出日常且口语化的回复，平淡一些，
尽量简短一些。{keywords_reaction_prompt}请注意把握聊天内容，不要回复的太有条理，可以有个性。
{reply_style}
请注意不要输出多余内容(包括前后缀，冒号和引号，括号，表情等)，只输出回复内容。
{moderation_prompt}不要输出多余内容(包括前后缀，冒号和引号，括号，表情包，at或 @等 )。""",
        "replyer_prompt",
    )



    Prompt(
        """{identity}
{time_block}
你现在正在一个QQ群里聊天，以下是正在进行的聊天内容：
{background_dialogue_prompt}

{expression_habits_block}{tool_info_block}
{knowledge_prompt}{relation_info_block}
{extra_info_block}

你现在想补充说明你刚刚自己的发言内容：{target}，原因是{reason}
请你根据聊天内容，组织一条新回复。注意，{target} 是刚刚你自己的发言，你要在这基础上进一步发言，请按照你自己的角度来继续进行回复。
注意保持上下文的连贯性。
你现在的心情是：{mood_state}
{reply_style}
{keywords_reaction_prompt}
请注意不要输出多余内容(包括前后缀，冒号和引号，at或 @等 )。只输出回复内容。
{moderation_prompt}
不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，emoji,at或 @等 )。只输出一条回复就好
现在，你说：
""",
        "replyer_self_prompt",
    )