from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.heart_flow.observation.observation import Observation
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
import time
import traceback
from src.common.logger import get_logger
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.message_receive.chat_stream import get_chat_manager
from .base_processor import BaseProcessor
from typing import List, Dict
from src.chat.heart_flow.observation.hfcloop_observation import HFCloopObservation
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.self_info import SelfInfo
from src.individuality.individuality import get_individuality

logger = get_logger("processor")


def init_prompt():
    indentify_prompt = """
{time_now}，以下是正在进行的聊天内容：
<聊天记录>
{chat_observe_info}
</聊天记录>

{name_block}
请你根据以上聊天记录，思考聊天记录中是否有人提到你自己相关的信息，或者有人询问你的相关信息。

请选择你需要查询的关键词来回答聊天中的问题。如果需要多个关键词，请用逗号隔开。
如果聊天中没有涉及任何关于你的问题，请输出none。

现在请输出你要查询的关键词，注意只输出关键词就好，不要输出其他内容：
"""
    Prompt(indentify_prompt, "indentify_prompt")


class SelfProcessor(BaseProcessor):
    log_prefix = "自我认同"

    def __init__(self, subheartflow_id: str):
        super().__init__()

        self.subheartflow_id = subheartflow_id

        self.info_fetched_cache: Dict[str, Dict[str, any]] = {}

        self.llm_model = LLMRequest(
            model=global_config.model.utils_small,
            request_type="focus.processor.self_identify",
        )

        name = get_chat_manager().get_stream_name(self.subheartflow_id)
        self.log_prefix = f"[{name}] "

    async def process_info(self, observations: List[Observation] = None, *infos) -> List[InfoBase]:
        """处理信息对象

        Args:
            *infos: 可变数量的InfoBase类型的信息对象

        Returns:
            List[InfoBase]: 处理后的结构化信息列表
        """
        self_info_str = await self.self_indentify(observations)

        if self_info_str:
            self_info = SelfInfo()
            self_info.set_self_info(self_info_str)
        else:
            self_info = None
            return None

        return [self_info]

    async def self_indentify(
        self,
        observations: List[Observation] = None,
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
            if isinstance(observation, HFCloopObservation):
                pass

        nickname_str = ""
        for nicknames in global_config.bot.alias_names:
            nickname_str += f"{nicknames},"
        name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"

        # 获取所有可用的关键词
        individuality = get_individuality()
        available_keywords = individuality.get_all_keywords()
        available_keywords_str = "、".join(available_keywords) if available_keywords else "暂无关键词"

        prompt = (await global_prompt_manager.get_prompt_async("indentify_prompt")).format(
            name_block=name_block,
            time_now=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            chat_observe_info=chat_observe_info[-200:],
            available_keywords=available_keywords_str,
            bot_name=global_config.bot.nickname,
        )

        keyword = ""

        try:
            keyword, _ = await self.llm_model.generate_response_async(prompt=prompt)

            # print(f"prompt: {prompt}\nkeyword: {keyword}")

            if not keyword:
                logger.warning(f"{self.log_prefix} LLM返回空结果，自我识别失败。")
        except Exception as e:
            # 处理总体异常
            logger.error(f"{self.log_prefix} 执行LLM请求或处理响应时出错: {e}")
            logger.error(traceback.format_exc())
            keyword = "我是谁，我从哪来，要到哪去"

        # 解析关键词
        keyword = keyword.strip()
        if not keyword or keyword == "none":
            keyword_set = []
        else:
            # 只保留非空关键词，去除多余空格
            keyword_set = [k.strip() for k in keyword.split(",") if k.strip()]

        # 从individuality缓存中查询关键词信息
        for keyword in keyword_set:
            if keyword not in self.info_fetched_cache:
                # 直接从individuality的json缓存中获取关键词信息
                fetched_info = individuality.get_keyword_info(keyword)

                if fetched_info:
                    self.info_fetched_cache[keyword] = {
                        "info": fetched_info,
                        "ttl": 5,
                    }
                    logger.info(f"{self.log_prefix} 从个体特征缓存中获取关键词 '{keyword}' 的信息")

        # 管理TTL（生存时间）
        expired_keywords = []
        for fetched_keyword, info in self.info_fetched_cache.items():
            if info["ttl"] > 0:
                info["ttl"] -= 1
            else:
                expired_keywords.append(fetched_keyword)

        # 删除过期的关键词
        for expired_keyword in expired_keywords:
            del self.info_fetched_cache[expired_keyword]

        fetched_info_str = ""
        for keyword, info in self.info_fetched_cache.items():
            fetched_info_str += f"你的：{keyword}信息是: {info['info']}\n"

        return fetched_info_str


init_prompt()
