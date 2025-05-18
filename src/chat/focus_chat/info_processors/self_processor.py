from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.heart_flow.observation.observation import Observation
from src.chat.models.utils_model import LLMRequest
from src.config.config import global_config
import time
import traceback
from src.common.logger_manager import get_logger
from src.individuality.individuality import Individuality
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.message_receive.chat_stream import chat_manager
from src.chat.person_info.relationship_manager import relationship_manager
from .base_processor import BaseProcessor
from typing import List, Optional
from src.chat.heart_flow.observation.hfcloop_observation import HFCloopObservation
from typing import Dict
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.self_info import SelfInfo

logger = get_logger("processor")


def init_prompt():
    indentify_prompt = """
你的名字是{bot_name},你是一个AI，但是你伪装成了一个人类，你的人格是，{prompt_personality}。
你的头像形象是一只橙色的鱼，头上有绿色的树叶。

{relation_prompt}
{memory_str}

现在是{time_now}，你正在上网，和qq群里的网友们聊天，以下是正在进行的聊天内容：
{chat_observe_info}

现在请你根据现有的信息，思考自我认同
1. 你是一个什么样的人,你和群里的人关系如何
2. 思考有没有人提到你，或者图片与你有关
3. 你的自我认同是否有助于你的回答，如果你需要自我相关的信息来帮你参与聊天，请输出，否则请输出十个字以内的简短自我认同
4. 一般情况下不用输出自我认同，只需要输出十几个字的简短自我认同就好，除非有明显需要自我认同的场景

请回复的平淡一些，简短一些，说中文，不要浮夸，平淡一些。
请注意不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。只输出内容。

"""
    Prompt(indentify_prompt, "indentify_prompt")


class SelfProcessor(BaseProcessor):
    log_prefix = "自我认同"

    def __init__(self, subheartflow_id: str):
        super().__init__()

        self.subheartflow_id = subheartflow_id

        self.llm_model = LLMRequest(
            model=global_config.model.sub_heartflow,
            temperature=global_config.model.sub_heartflow["temp"],
            max_tokens=800,
            request_type="self_identify",
        )

        name = chat_manager.get_stream_name(self.subheartflow_id)
        self.log_prefix = f"[{name}] "

    async def process_info(
        self, observations: Optional[List[Observation]] = None, running_memorys: Optional[List[Dict]] = None, *infos
    ) -> List[InfoBase]:
        """处理信息对象

        Args:
            *infos: 可变数量的InfoBase类型的信息对象

        Returns:
            List[InfoBase]: 处理后的结构化信息列表
        """
        self_info_str = await self.self_indentify(observations, running_memorys)

        if self_info_str:
            self_info = SelfInfo()
            self_info.set_self_info(self_info_str)
        else:
            self_info = None
            return None

        return [self_info]

    async def self_indentify(
        self, observations: Optional[List[Observation]] = None, running_memorys: Optional[List[Dict]] = None
    ):
        """
        在回复前进行思考，生成内心想法并收集工具调用结果

        参数:
            observations: 观察信息

        返回:
            如果return_prompt为False:
                tuple: (current_mind, past_mind) 当前想法和过去的想法列表
            如果return_prompt为True:
                tuple: (current_mind, past_mind, prompt) 当前想法、过去的想法列表和使用的prompt
        """

        memory_str = ""
        if running_memorys:
            memory_str = "以下是当前在聊天中，你回忆起的记忆：\n"
            for running_memory in running_memorys:
                memory_str += f"{running_memory['topic']}: {running_memory['content']}\n"

        if observations is None:
            observations = []
        for observation in observations:
            if isinstance(observation, ChattingObservation):
                # 获取聊天元信息
                is_group_chat = observation.is_group_chat
                chat_target_info = observation.chat_target_info
                chat_target_name = "对方"  # 私聊默认名称
                if not is_group_chat and chat_target_info:
                    # 优先使用person_name，其次user_nickname，最后回退到默认值
                    chat_target_name = (
                        chat_target_info.get("person_name") or chat_target_info.get("user_nickname") or chat_target_name
                    )
                # 获取聊天内容
                chat_observe_info = observation.get_observe_info()
                person_list = observation.person_list
            if isinstance(observation, HFCloopObservation):
                # hfcloop_observe_info = observation.get_observe_info()
                pass

        individuality = Individuality.get_instance()
        personality_block = individuality.get_prompt(x_person=2, level=2)

        relation_prompt = ""
        for person in person_list:
            relation_prompt += await relationship_manager.build_relationship_info(person, is_id=True)

        prompt = (await global_prompt_manager.get_prompt_async("indentify_prompt")).format(
            bot_name=individuality.name,
            prompt_personality=personality_block,
            memory_str=memory_str,
            relation_prompt=relation_prompt,
            time_now=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            chat_observe_info=chat_observe_info,
        )

        content = ""
        try:
            content, _ = await self.llm_model.generate_response_async(prompt=prompt)
            if not content:
                logger.warning(f"{self.log_prefix} LLM返回空结果，自我识别失败。")
        except Exception as e:
            # 处理总体异常
            logger.error(f"{self.log_prefix} 执行LLM请求或处理响应时出错: {e}")
            logger.error(traceback.format_exc())
            content = "自我识别过程中出现错误"

        if content == "None":
            content = ""
        # 记录初步思考结果
        logger.debug(f"{self.log_prefix} 自我识别prompt: \n{prompt}\n")
        logger.info(f"{self.log_prefix} 自我识别结果: {content}")

        return content


init_prompt()
