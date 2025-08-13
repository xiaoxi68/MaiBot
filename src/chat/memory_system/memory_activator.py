import json

from json_repair import repair_json
from typing import List, Dict


from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config, model_config
from src.common.logger import get_logger
from src.chat.utils.prompt_builder import Prompt
from src.chat.memory_system.Hippocampus import hippocampus_manager
from src.chat.utils.utils import parse_keywords_string


logger = get_logger("memory_activator")


def get_keywords_from_json(json_str) -> List:
    """
    从JSON字符串中提取关键词列表

    Args:
        json_str: JSON格式的字符串

    Returns:
        List[str]: 关键词列表
    """
    try:
        # 使用repair_json修复JSON格式
        fixed_json = repair_json(json_str)

        # 如果repair_json返回的是字符串，需要解析为Python对象
        result = json.loads(fixed_json) if isinstance(fixed_json, str) else fixed_json
        return result.get("keywords", [])
    except Exception as e:
        logger.error(f"解析关键词JSON失败: {e}")
        return []


def init_prompt():
    # --- Group Chat Prompt ---
    memory_activator_prompt = """
    你是一个记忆分析器，你需要根据以下信息来进行回忆
    以下是一段聊天记录，请根据这些信息，总结出几个关键词作为记忆回忆的触发词
    
    聊天记录:
    {obs_info_text}
    你想要回复的消息:
    {target_message}
    
    历史关键词（请避免重复提取这些关键词）：
    {cached_keywords}
    
    请输出一个json格式，包含以下字段：
    {{
        "keywords": ["关键词1", "关键词2", "关键词3",......]
    }}
    不要输出其他多余内容，只输出json格式就好
    """

    Prompt(memory_activator_prompt, "memory_activator_prompt")


class MemoryActivator:
    def __init__(self):
        self.key_words_model = LLMRequest(
            model_set=model_config.model_task_config.utils_small,
            request_type="memory.activator",
        )


    async def activate_memory_with_chat_history(self, target_message, chat_history_prompt) -> List[Dict]:
        """
        激活记忆
        """
        # 如果记忆系统被禁用，直接返回空列表
        if not global_config.memory.enable_memory:
            return []
        
        keywords_list = set()
        
        for msg in chat_history_prompt:
            keywords = parse_keywords_string(msg.get("key_words", ""))
            if keywords:
                if len(keywords_list) < 30:
                # 最多容纳30个关键词
                    keywords_list.update(keywords)
                    print(keywords_list)
                else:
                    break
        
        if not keywords_list:
            return []
        
        related_memory = await hippocampus_manager.get_memory_from_topic(
            valid_keywords=list(keywords_list), max_memory_num=10, max_memory_length=3, max_depth=3
        )
        

        logger.info(f"当前记忆关键词: {keywords_list} ")
        logger.info(f"获取到的记忆: {related_memory}")

        return related_memory


init_prompt()
