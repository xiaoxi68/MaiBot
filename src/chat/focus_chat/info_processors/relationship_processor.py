from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.heart_flow.observation.observation import Observation
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
import time
import traceback
from src.common.logger_manager import get_logger
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.message_receive.chat_stream import chat_manager
from src.person_info.relationship_manager import relationship_manager
from .base_processor import BaseProcessor
from typing import List, Optional
from typing import Dict
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.relation_info import RelationInfo
from json_repair import repair_json
from src.person_info.person_info import person_info_manager
import json
import asyncio
from src.chat.utils.chat_message_builder import get_raw_msg_by_timestamp_with_chat

logger = get_logger("processor")


def init_prompt():
    relationship_prompt = """
<聊天记录>
{chat_observe_info}
</聊天记录>

<人物信息>
{relation_prompt}
</人物信息>

请区分聊天记录的内容和你之前对人的了解，聊天记录是现在发生的事情，人物信息是之前对某个人的持久的了解。

{name_block}
现在请你总结提取某人的信息，提取成一串文本
1. 根据聊天记录的需求，如果需要你和某个人的信息，请输出你和这个人之间精简的信息
2. 如果没有特别需要提及的信息，就不用输出这个人的信息
3. 如果有人问你对他的看法或者关系，请输出你和这个人之间的信息
4. 你可以完全不输出任何信息，或者不输出某个人

请从这些信息中提取出你对某人的了解信息，信息提取成一串文本：

请严格按照以下输出格式，不要输出多余内容，person_name可以有多个：
{{
    "person_name": "信息",
    "person_name2": "信息",
    "person_name3": "信息",
}}

"""
    Prompt(relationship_prompt, "relationship_prompt")


class RelationshipProcessor(BaseProcessor):
    log_prefix = "关系"

    def __init__(self, subheartflow_id: str):
        super().__init__()

        self.subheartflow_id = subheartflow_id
        self.person_cache: Dict[str, Dict[str, any]] = {}  # {person_id: {"info": str, "ttl": int, "start_time": float}}
        self.pending_updates: Dict[str, Dict[str, any]] = (
            {}
        )  # {person_id: {"start_time": float, "end_time": float, "grace_period_ttl": int, "chat_id": str}}
        self.grace_period_rounds = 5

        self.llm_model = LLMRequest(
            model=global_config.model.relation,
            max_tokens=800,
            request_type="relation",
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
        relation_info_str = await self.relation_identify(observations)

        if relation_info_str:
            relation_info = RelationInfo()
            relation_info.set_relation_info(relation_info_str)
        else:
            relation_info = None
            return None

        return [relation_info]

    async def relation_identify(
        self,
        observations: Optional[List[Observation]] = None,
    ):
        """
        在回复前进行思考，生成内心想法并收集工具调用结果
        """
        # 0. 从观察信息中提取所需数据
        person_list = []
        chat_observe_info = ""
        is_group_chat = False
        if observations:
            for observation in observations:
                if isinstance(observation, ChattingObservation):
                    is_group_chat = observation.is_group_chat
                    chat_observe_info = observation.get_observe_info()
                    person_list = observation.person_list
                    break

        # 1. 处理等待更新的条目（仅检查TTL，不检查是否被重提）
        persons_to_update_now = []  # 等待期结束，需要立即更新的用户
        for person_id, data in list(self.pending_updates.items()):
            data["grace_period_ttl"] -= 1
            if data["grace_period_ttl"] <= 0:
                persons_to_update_now.append(person_id)

        # 触发等待期结束的更新任务
        for person_id in persons_to_update_now:
            if person_id in self.pending_updates:
                update_data = self.pending_updates.pop(person_id)
                logger.info(f"{self.log_prefix} 用户 {person_id} 等待期结束，开始印象更新。")
                asyncio.create_task(
                    self.update_impression_on_cache_expiry(
                        person_id, update_data["chat_id"], update_data["start_time"], update_data["end_time"]
                    )
                )

        # 2. 维护活动缓存，并将过期条目移至等待区或立即更新
        persons_moved_to_pending = []
        for person_id, cache_data in self.person_cache.items():
            cache_data["ttl"] -= 1
            if cache_data["ttl"] <= 0:
                persons_moved_to_pending.append(person_id)

        for person_id in persons_moved_to_pending:
            if person_id in self.person_cache:
                cache_item = self.person_cache.pop(person_id)
                start_time = cache_item.get("start_time")
                end_time = time.time()
                time_elapsed = end_time - start_time

                impression_messages = get_raw_msg_by_timestamp_with_chat(self.subheartflow_id, start_time, end_time)
                message_count = len(impression_messages)

                if message_count > 50 or (time_elapsed > 600 and message_count > 20):
                    logger.info(
                        f"{self.log_prefix} 用户 {person_id} 缓存过期，满足立即更新条件 (消息数: {message_count}, 持续时间: {time_elapsed:.0f}s)，立即更新。"
                    )
                    asyncio.create_task(
                        self.update_impression_on_cache_expiry(person_id, self.subheartflow_id, start_time, end_time)
                    )
                else:
                    logger.info(f"{self.log_prefix} 用户 {person_id} 缓存过期，进入更新等待区。")
                    self.pending_updates[person_id] = {
                        "start_time": start_time,
                        "end_time": end_time,
                        "grace_period_ttl": self.grace_period_rounds,
                        "chat_id": self.subheartflow_id,
                    }

        # 3. 准备LLM输入和直接使用缓存
        if not person_list:
            return ""

        cached_person_info_str = ""
        persons_to_process = []
        person_name_list_for_llm = []

        for person_id in person_list:
            if person_id in self.person_cache:
                logger.info(f"{self.log_prefix} 关系识别 (缓存): {person_id}")
                person_name = await person_info_manager.get_value(person_id, "person_name")
                info = self.person_cache[person_id]["info"]
                cached_person_info_str += f"你对 {person_name} 的了解：{info}\n"
            else:
                # 所有不在活动缓存中的用户（包括等待区的）都将由LLM处理
                persons_to_process.append(person_id)
                person_name_list_for_llm.append(await person_info_manager.get_value(person_id, "person_name"))

        # 4. 如果没有需要LLM处理的人员，直接返回缓存信息
        if not persons_to_process:
            final_result = cached_person_info_str.strip()
            if final_result:
                logger.info(f"{self.log_prefix} 关系识别 (全部缓存): {final_result}")
            return final_result

        # 5. 为需要处理的人员准备LLM prompt
        nickname_str = ",".join(global_config.bot.alias_names)
        name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"
        relation_prompt_init = "你对群聊里的人的印象是：\n" if is_group_chat else "你对对方的印象是：\n"
        relation_prompt = ""
        for person_id in persons_to_process:
            relation_prompt += f"{await relationship_manager.build_relationship_info(person_id, is_id=True)}\n\n"

        if relation_prompt:
            relation_prompt = relation_prompt_init + relation_prompt
        else:
            relation_prompt = relation_prompt_init + "没有特别在意的人\n"

        prompt = (await global_prompt_manager.get_prompt_async("relationship_prompt")).format(
            name_block=name_block,
            relation_prompt=relation_prompt,
            time_now=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            chat_observe_info=chat_observe_info,
        )

        # 6. 调用LLM并处理结果
        newly_processed_info_str = ""
        try:
            logger.info(f"{self.log_prefix} 关系识别prompt: \n{prompt}\n")
            content, _ = await self.llm_model.generate_response_async(prompt=prompt)
            if content:
                print(f"content: {content}")
                content_json = json.loads(repair_json(content))

                for person_name, person_info in content_json.items():
                    if person_name in person_name_list_for_llm:
                        try:
                            idx = person_name_list_for_llm.index(person_name)
                            person_id = persons_to_process[idx]

                            # 关键：检查此人是否在等待区，如果是，则为"唤醒"
                            start_time = time.time()  # 新用户的默认start_time
                            if person_id in self.pending_updates:
                                logger.info(f"{self.log_prefix} 用户 {person_id} 在等待期被LLM重提，重新激活缓存。")
                                revived_item = self.pending_updates.pop(person_id)
                                start_time = revived_item["start_time"]

                            self.person_cache[person_id] = {
                                "info": person_info,
                                "ttl": 5,
                                "start_time": start_time,
                            }
                            newly_processed_info_str += f"你对 {person_name} 的了解：{person_info}\n"
                        except (ValueError, IndexError):
                            continue
            else:
                logger.warning(f"{self.log_prefix} LLM返回空结果，关系识别失败。")

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行LLM请求或处理响应时出错: {e}")
            logger.error(traceback.format_exc())
            newly_processed_info_str = "关系识别过程中出现错误"

        # 7. 合并缓存和新处理的信息
        person_info_str = (cached_person_info_str + newly_processed_info_str).strip()

        if person_info_str == "None":
            person_info_str = ""
        
        logger.info(f"{self.log_prefix} 关系识别: {person_info_str}")

        return person_info_str

    async def update_impression_on_cache_expiry(
        self, person_id: str, chat_id: str, start_time: float, end_time: float
    ):
        """
        在缓存过期时，获取聊天记录并更新用户印象
        """
        logger.info(f"缓存过期，开始为 {person_id} 更新印象。时间范围：{start_time} -> {end_time}")
        try:
            

            impression_messages = get_raw_msg_by_timestamp_with_chat(chat_id, start_time, end_time)
            if impression_messages:
                logger.info(f"为 {person_id} 获取到 {len(impression_messages)} 条消息用于印象更新。")
                await relationship_manager.update_person_impression(
                    person_id=person_id, timestamp=end_time, bot_engaged_messages=impression_messages
                )
            else:
                logger.info(f"在指定时间范围内没有找到 {person_id} 的消息，不更新印象。")

        except Exception as e:
            logger.error(f"为 {person_id} 更新印象时发生错误: {e}")
            logger.error(traceback.format_exc())


init_prompt()
