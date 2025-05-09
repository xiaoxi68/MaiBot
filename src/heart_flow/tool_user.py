from .observation import ChattingObservation
from src.plugins.models.utils_model import LLMRequest
from src.config.config import global_config
import time
import traceback
from src.common.logger_manager import get_logger
from src.individuality.individuality import Individuality
import random
from ..plugins.utils.prompt_builder import Prompt, global_prompt_manager
from src.do_tool.tool_use import ToolUser
from src.plugins.utils.json_utils import safe_json_dumps, process_llm_tool_calls
from src.heart_flow.chat_state_info import ChatStateInfo
from src.plugins.chat.chat_stream import chat_manager
from src.plugins.heartFC_chat.heartFC_Cycleinfo import CycleInfo
import difflib
from src.plugins.person_info.relationship_manager import relationship_manager
from src.plugins.memory_system.Hippocampus import HippocampusManager
import jieba
from src.common.logger_manager import get_logger
from src.heart_flow.sub_mind import SubMind
logger = get_logger("tool_use")

def init_prompt():
    # ... 原有代码 ...
    
    # 添加工具执行器提示词
    tool_executor_prompt = """
你是一个专门执行工具的助手。你的名字是{bot_name}。现在是{time_now}。

你要在群聊中扮演以下角色：
{prompt_personality}

你当前的额外信息：
{extra_info}

你的心情是：{mood_info}

{relation_prompt}

群里正在进行的聊天内容：
{chat_observe_info}

请仔细分析聊天内容，考虑以下几点：
1. 内容中是否包含需要查询信息的问题
2. 是否需要执行特定操作
3. 是否有明确的工具使用指令
4. 考虑用户与你的关系以及当前的对话氛围

如果需要使用工具，请直接调用相应的工具函数。如果不需要使用工具，请简单输出"无需使用工具"。
尽量只在确实必要时才使用工具。
"""
    Prompt(tool_executor_prompt, "tool_executor_prompt")

class ToolExecutor:
    def __init__(self, subheartflow_id: str):
        self.subheartflow_id = subheartflow_id
        self.log_prefix = f"[{subheartflow_id}:ToolExecutor] "
        self.llm_model = LLMRequest(
            model=global_config.llm_sub_heartflow,  # 为工具执行器配置单独的模型
            temperature=global_config.llm_sub_heartflow["temp"],
            max_tokens=800,
            request_type="tool_execution",
        )
        self.structured_info = []
        
    async def execute_tools(self, sub_mind: SubMind, chat_target_name="对方", is_group_chat=False):
        """并行执行工具，返回结构化信息"""
        # 初始化工具
        tool_instance = ToolUser()
        tools = tool_instance._define_tools()
        
        observation: ChattingObservation = sub_mind.observations[0] if sub_mind.observations else None
        
        # 获取观察内容
        chat_observe_info = observation.get_observe_info()
        person_list = observation.person_list
        
        # extra structured info
        extra_structured_info = sub_mind.structured_info_str
        
        # 构建关系信息
        relation_prompt = "【关系信息】\n"
        for person in person_list:
            relation_prompt += await relationship_manager.build_relationship_info(person, is_id=True)
        
        # 获取个性信息
        individuality = Individuality.get_instance()
        prompt_personality = individuality.get_prompt(x_person=2, level=2)
        
        # 获取心情信息
        mood_info = observation.chat_state.mood if hasattr(observation, "chat_state") else ""
        
        # 获取时间信息
        time_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        
        # 构建专用于工具调用的提示词
        prompt = await global_prompt_manager.format_prompt(
            "tool_executor_prompt",
            extra_info=extra_structured_info,
            chat_observe_info=chat_observe_info,
            chat_target_name=chat_target_name,
            is_group_chat=is_group_chat,
            relation_prompt=relation_prompt,
            prompt_personality=prompt_personality,
            mood_info=mood_info,
            bot_name=individuality.name,
            time_now=time_now
        )
        
        # 调用LLM，专注于工具使用
        response, _, tool_calls = await self.llm_model.generate_response_tool_async(
            prompt=prompt, tools=tools
        )
        
        # 处理工具调用和结果收集，类似于SubMind中的逻辑
        new_structured_items = []
        if tool_calls:
            success, valid_tool_calls, error_msg = process_llm_tool_calls(tool_calls)
            if success and valid_tool_calls:
                for tool_call in valid_tool_calls:
                    try:
                        result = await tool_instance._execute_tool_call(tool_call)
                        if result:
                            new_item = {
                                "type": result.get("type", "unknown_type"),
                                "id": result.get("id", f"tool_exec_{time.time()}"),
                                "content": result.get("content", ""),
                                "ttl": 3,
                            }
                            new_structured_items.append(new_item)
                    except Exception as e:
                        logger.error(f"{self.log_prefix}工具执行失败: {e}")
        
        return new_structured_items


init_prompt()