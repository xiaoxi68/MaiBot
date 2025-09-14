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



def init_lpmm_prompt():
    Prompt(
        """
你是一个专门获取知识的助手。你的名字是{bot_name}。现在是{time_now}。
群里正在进行的聊天内容：
{chat_history}

现在，{sender}发送了内容:{target_message},你想要回复ta。
请仔细分析聊天内容，考虑以下几点：
1. 内容中是否包含需要查询信息的问题
2. 是否有明确的知识获取指令

If you need to use the search tool, please directly call the function "lpmm_search_knowledge". If you do not need to use any tool, simply output "No tool needed".
""",
        name="lpmm_get_knowledge_prompt",
    )
    
    
