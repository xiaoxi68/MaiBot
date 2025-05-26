from src.common.logger_manager import get_logger
from src.chat.focus_chat.planners.actions.plugin_action import PluginAction, register_action
from typing import Tuple

logger = get_logger("tts_action")


@register_action
class TTSAction(PluginAction):
    """TTS语音转换动作处理类"""

    action_name = "tts_action"
    action_description = "将文本转换为语音进行播放，适用于需要语音输出的场景"
    action_parameters = {
        "text": "需要转换为语音的文本内容，必填，内容应当适合语音播报，语句流畅、清晰",
    }
    action_require = [
        "当需要发送语音信息时使用",
        "当用户明确要求使用语音功能时使用",
        "当表达内容更适合用语音而不是文字传达时使用",
        "当用户想听到语音回答而非阅读文本时使用",
    ]
    default = True  # 设为默认动作
    associated_types = ["tts_text"]

    async def process(self) -> Tuple[bool, str]:
        """处理TTS文本转语音动作"""
        logger.info(f"{self.log_prefix} 执行TTS动作: {self.reasoning}")

        # 获取要转换的文本
        text = self.action_data.get("text")

        if not text:
            logger.error(f"{self.log_prefix} 执行TTS动作时未提供文本内容")
            return False, "执行TTS动作失败：未提供文本内容"

        # 确保文本适合TTS使用
        processed_text = self._process_text_for_tts(text)

        try:
            # 发送TTS消息
            await self.send_message(type="tts_text", data=processed_text)

            logger.info(f"{self.log_prefix} TTS动作执行成功，文本长度: {len(processed_text)}")
            return True, "TTS动作执行成功"

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行TTS动作时出错: {e}")
            return False, f"执行TTS动作时出错: {e}"

    def _process_text_for_tts(self, text: str) -> str:
        """
        处理文本使其更适合TTS使用
        - 移除不必要的特殊字符和表情符号
        - 修正标点符号以提高语音质量
        - 优化文本结构使语音更流畅
        """
        # 这里可以添加文本处理逻辑
        # 例如：移除多余的标点、表情符号，优化语句结构等

        # 简单示例实现
        processed_text = text

        # 移除多余的标点符号
        import re

        processed_text = re.sub(r"([!?,.;:。！？，、；：])\1+", r"\1", processed_text)

        # 确保句子结尾有合适的标点
        if not any(processed_text.endswith(end) for end in [".", "?", "!", "。", "！", "？"]):
            processed_text = processed_text + "。"

        return processed_text
