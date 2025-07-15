import asyncio
import json
import time

from src.chat.message_receive.message import MessageRecv
from src.llm_models.utils_model import LLMRequest
from src.common.logger import get_logger
from src.chat.utils.chat_message_builder import build_readable_messages, get_raw_msg_by_timestamp_with_chat_inclusive
from src.config.config import global_config
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.manager.async_task_manager import AsyncTask, async_task_manager
from src.plugin_system.apis import send_api

async def send_loading(chat_id: str, content: str):
    await send_api.custom_to_stream(
        message_type="loading",
        content=content,
        stream_id=chat_id,
        storage_message=False,
        show_log=True,
    )
    
async def send_unloading(chat_id: str):
    await send_api.custom_to_stream(
        message_type="loading",
        content="",
        stream_id=chat_id,
        storage_message=False,
        show_log=True,
    )
    