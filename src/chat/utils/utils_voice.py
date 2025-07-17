import base64
import os
import time
import hashlib
import uuid
from typing import Optional, Tuple
from PIL import Image
import io
import numpy as np
import asyncio


from src.common.database.database import db
from src.common.database.database_model import Images, ImageDescriptions
from src.config.config import global_config
from src.llm_models.utils_model import LLMRequest

from src.common.logger import get_logger
from rich.traceback import install
import traceback
install(extra_lines=3)

logger = get_logger("chat_voice")

async def get_voice_text(voice_base64: str) -> str:
    """获取音频文件描述"""
    try:
        # 计算图片哈希
        # 确保base64字符串只包含ASCII字符
        if isinstance(voice_base64, str):
            voice_base64 = voice_base64.encode("ascii", errors="ignore").decode("ascii")
        voice_bytes = base64.b64decode(voice_base64)
        _llm = LLMRequest(model=global_config.model.voice, request_type="voice")
        text = await _llm.generate_response_for_voice(voice_bytes)
        if text is None:
            logger.warning("未能生成语音文本")
            return "[语音(文本生成失败)]"
        
        logger.debug(f"描述是{text}")

        return f"[语音：{text}]"
    except Exception as e:
        traceback.print_exc()
        logger.error(f"语音转文字失败: {str(e)}")
        return "[语音]"

