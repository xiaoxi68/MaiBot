from src.heart_flow.observation.chatting_observation import ChattingObservation
from src.heart_flow.observation.working_observation import WorkingObservation
from src.heart_flow.observation.hfcloop_observation import HFCloopObservation
from src.plugins.models.utils_model import LLMRequest
from src.config.config import global_config
from src.common.logger_manager import get_logger
from src.plugins.utils.prompt_builder import Prompt, global_prompt_manager
from src.plugins.heartFC_chat.hfc_utils import get_keywords_from_json
from datetime import datetime
from src.plugins.memory_system.Hippocampus import HippocampusManager
from typing import List, Dict


logger = get_logger("memory_activator")

Prompt(
    """
    你是一个记忆分析器，你需要根据以下信息来进行会议
    以下是一场聊天中的信息，请根据这些信息，总结出几个关键词作为记忆回忆的触发词
    
    {obs_info_text}
    
    请输出一个json格式，包含以下字段：
    {
        "keywords": ["关键词1", "关键词2", "关键词3",......]
    }
    不要输出其他多余内容，只输出json格式就好
    """,
    "memory_activator_prompt",
)


class MemoryActivator:
    def __init__(self):
        self.summart_model = LLMRequest(
            model=global_config.llm_observation, temperature=0.7, max_tokens=300, request_type="chat_observation"
        )
        self.running_memory = []

    async def activate_memory(self, observations) -> List[Dict]:
        obs_info_text = ""
        for observation in observations:
            if isinstance(observation, ChattingObservation):
                obs_info_text += observation.get_observe_info()
            elif isinstance(observation, WorkingObservation):
                working_info = observation.get_observe_info()
                for working_info_item in working_info:
                    obs_info_text += f"{working_info_item['type']}: {working_info_item['content']}\n"
            elif isinstance(observation, HFCloopObservation):
                obs_info_text += observation.get_observe_info()

        prompt = global_prompt_manager.format_prompt("memory_activator_prompt", obs_info_text=obs_info_text)

        response = self.summart_model.generate_response(prompt)

        keywords = get_keywords_from_json(response)

        # 调用记忆系统获取相关记忆
        related_memory = await HippocampusManager.get_instance().get_memory_from_topic(
            valid_keywords=keywords, max_memory_num=3, max_memory_length=2, max_depth=3
        )

        logger.debug(f"获取到的记忆: {related_memory}")

        if related_memory:
            for topic, memory in related_memory:
                self.running_memory.append({"topic": topic, "content": memory, "timestamp": datetime.now().isoformat()})
                logger.debug(f"添加新记忆: {topic} - {memory}")

        return self.running_memory
