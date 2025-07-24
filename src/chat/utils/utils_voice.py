import base64

from src.config.config import global_config
from src.llm_models.utils_model import LLMRequest

from src.common.logger import get_logger
from rich.traceback import install
install(extra_lines=3)

logger = get_logger("chat_voice")

async def get_voice_text(voice_base64: str) -> str:
    """获取音频文件描述"""
    if not global_config.voice.enable_asr:
        logger.warning("语音识别未启用，无法处理语音消息")
        return "[语音]"
    try:
        # 解码base64音频数据
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
        logger.error(f"语音转文字失败: {str(e)}")
        return "[语音]"

