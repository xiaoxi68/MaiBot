from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.heart_flow.observation.observation import Observation
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
import time
import traceback
from src.common.logger import get_logger
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.message_receive.chat_stream import get_chat_manager
from src.person_info.relationship_manager import get_relationship_manager
from .base_processor import BaseProcessor
from typing import List
from typing import Dict
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.relation_info import RelationInfo
from json_repair import repair_json
from src.person_info.person_info import get_person_info_manager
import json
import asyncio
from src.chat.utils.chat_message_builder import (
    get_raw_msg_by_timestamp_with_chat,
    get_raw_msg_by_timestamp_with_chat_inclusive,
    get_raw_msg_before_timestamp_with_chat,
    num_new_messages_since,
)
import os
import pickle


# 配置常量：是否启用小模型即时信息提取
# 开启时：使用小模型并行即时提取，速度更快，但精度可能略低
# 关闭时：使用原来的异步模式，精度更高但速度较慢
ENABLE_INSTANT_INFO_EXTRACTION = True

# 消息段清理配置
SEGMENT_CLEANUP_CONFIG = {
    "enable_cleanup": True,  # 是否启用清理
    "max_segment_age_days": 7,  # 消息段最大保存天数
    "max_segments_per_user": 10,  # 每用户最大消息段数
    "cleanup_interval_hours": 1,  # 清理间隔（小时）
}

logger = get_logger("processor")


def init_prompt():
    relationship_prompt = """
<聊天记录>
{chat_observe_info}
</聊天记录>

<调取记录>
{info_cache_block}
</调取记录>

{name_block}
请你阅读聊天记录，查看是否需要调取某个人的信息，这个人可以是出现在聊天记录中的，也可以是记录中提到的人。
你不同程度上认识群聊里的人，以及他们谈论到的人，你可以根据聊天记录，回忆起有关他们的信息，帮助你参与聊天
1.你需要提供用户名，以及你想要提取的信息名称类型来进行调取
2.请注意，提取的信息类型一定要和用户有关，不要提取无关的信息
3.阅读调取记录，如果已经回忆过某个人的信息，请不要重复调取，除非你忘记了

请以json格式输出，例如：

{{
    "用户A": "ta的昵称",
    "用户B": "ta对你的态度",
    "用户C": "你和ta最近做的事",
    "用户D": "你对ta的印象",
}}


请严格按照以下输出格式，不要输出多余内容，person_name可以有多个：
{{
    "person_name": "信息名称",
    "person_name": "信息名称",
}}

"""
    Prompt(relationship_prompt, "relationship_prompt")

    fetch_info_prompt = """
    
{name_block}
以下是你对{person_name}的了解，请你从中提取用户的有关"{info_type}"的信息，如果用户没有相关信息，请输出none：
<对{person_name}的总体了解>
{person_impression}
</对{person_name}的总体了解>

<你记得{person_name}最近的事>
{points_text}
</你记得{person_name}最近的事>

请严格按照以下json输出格式，不要输出多余内容：
{{
    {info_json_str}
}}
"""
    Prompt(fetch_info_prompt, "fetch_info_prompt")


class RelationshipProcessor(BaseProcessor):
    log_prefix = "关系"

    def __init__(self, subheartflow_id: str):
        super().__init__()

        self.subheartflow_id = subheartflow_id
        self.info_fetching_cache: List[Dict[str, any]] = []
        self.info_fetched_cache: Dict[
            str, Dict[str, any]
        ] = {}  # {person_id: {"info": str, "ttl": int, "start_time": float}}

        # 新的消息段缓存结构：
        # {person_id: [{"start_time": float, "end_time": float, "last_msg_time": float, "message_count": int}, ...]}
        self.person_engaged_cache: Dict[str, List[Dict[str, any]]] = {}

        # 持久化存储文件路径
        self.cache_file_path = os.path.join("data", f"relationship_cache_{self.subheartflow_id}.pkl")

        # 最后处理的消息时间，避免重复处理相同消息
        current_time = time.time()
        self.last_processed_message_time = current_time

        # 最后清理时间，用于定期清理老消息段
        self.last_cleanup_time = 0.0

        self.llm_model = LLMRequest(
            model=global_config.model.relation,
            request_type="focus.relationship",
        )

        # 小模型用于即时信息提取
        if ENABLE_INSTANT_INFO_EXTRACTION:
            self.instant_llm_model = LLMRequest(
                model=global_config.model.utils_small,
                request_type="focus.relationship.instant",
            )

        name = get_chat_manager().get_stream_name(self.subheartflow_id)
        self.log_prefix = f"[{name}] "

        # 加载持久化的缓存
        self._load_cache()

    # ================================
    # 缓存管理模块
    # 负责持久化存储、状态管理、缓存读写
    # ================================

    def _load_cache(self):
        """从文件加载持久化的缓存"""
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, "rb") as f:
                    cache_data = pickle.load(f)
                    # 新格式：包含额外信息的缓存
                    self.person_engaged_cache = cache_data.get("person_engaged_cache", {})
                    self.last_processed_message_time = cache_data.get("last_processed_message_time", 0.0)
                    self.last_cleanup_time = cache_data.get("last_cleanup_time", 0.0)

                logger.info(
                    f"{self.log_prefix} 成功加载关系缓存，包含 {len(self.person_engaged_cache)} 个用户，最后处理时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_processed_message_time)) if self.last_processed_message_time > 0 else '未设置'}"
                )
            except Exception as e:
                logger.error(f"{self.log_prefix} 加载关系缓存失败: {e}")
                self.person_engaged_cache = {}
                self.last_processed_message_time = 0.0
        else:
            logger.info(f"{self.log_prefix} 关系缓存文件不存在，使用空缓存")

    def _save_cache(self):
        """保存缓存到文件"""
        try:
            os.makedirs(os.path.dirname(self.cache_file_path), exist_ok=True)
            cache_data = {
                "person_engaged_cache": self.person_engaged_cache,
                "last_processed_message_time": self.last_processed_message_time,
                "last_cleanup_time": self.last_cleanup_time,
            }
            with open(self.cache_file_path, "wb") as f:
                pickle.dump(cache_data, f)
            logger.debug(f"{self.log_prefix} 成功保存关系缓存")
        except Exception as e:
            logger.error(f"{self.log_prefix} 保存关系缓存失败: {e}")

    # ================================
    # 消息段管理模块
    # 负责跟踪用户消息活动、管理消息段、清理过期数据
    # ================================

    def _update_message_segments(self, person_id: str, message_time: float):
        """更新用户的消息段

        Args:
            person_id: 用户ID
            message_time: 消息时间戳
        """
        if person_id not in self.person_engaged_cache:
            self.person_engaged_cache[person_id] = []

        segments = self.person_engaged_cache[person_id]
        current_time = time.time()

        # 获取该消息前5条消息的时间作为潜在的开始时间
        before_messages = get_raw_msg_before_timestamp_with_chat(self.subheartflow_id, message_time, limit=5)
        if before_messages:
            # 由于get_raw_msg_before_timestamp_with_chat返回按时间升序排序的消息，最后一个是最接近message_time的
            # 我们需要第一个消息作为开始时间，但应该确保至少包含5条消息或该用户之前的消息
            potential_start_time = before_messages[0]["time"]
        else:
            # 如果没有前面的消息，就从当前消息开始
            potential_start_time = message_time

        # 如果没有现有消息段，创建新的
        if not segments:
            new_segment = {
                "start_time": potential_start_time,
                "end_time": message_time,
                "last_msg_time": message_time,
                "message_count": self._count_messages_in_timerange(potential_start_time, message_time),
            }
            segments.append(new_segment)
            logger.info(
                f"{self.log_prefix} 为用户 {person_id} 创建新消息段: 时间范围 {time.strftime('%H:%M:%S', time.localtime(potential_start_time))} - {time.strftime('%H:%M:%S', time.localtime(message_time))}, 消息数: {new_segment['message_count']}"
            )
            self._save_cache()
            return

        # 获取最后一个消息段
        last_segment = segments[-1]

        # 计算从最后一条消息到当前消息之间的消息数量（不包含边界）
        messages_between = self._count_messages_between(last_segment["last_msg_time"], message_time)

        if messages_between <= 10:
            # 在10条消息内，延伸当前消息段
            last_segment["end_time"] = message_time
            last_segment["last_msg_time"] = message_time
            # 重新计算整个消息段的消息数量
            last_segment["message_count"] = self._count_messages_in_timerange(
                last_segment["start_time"], last_segment["end_time"]
            )
            logger.info(f"{self.log_prefix} 延伸用户 {person_id} 的消息段: {last_segment}")
        else:
            # 超过10条消息，结束当前消息段并创建新的
            # 结束当前消息段：延伸到原消息段最后一条消息后5条消息的时间
            after_messages = get_raw_msg_by_timestamp_with_chat(
                self.subheartflow_id, last_segment["last_msg_time"], current_time, limit=5, limit_mode="earliest"
            )
            if after_messages and len(after_messages) >= 5:
                # 如果有足够的后续消息，使用第5条消息的时间作为结束时间
                last_segment["end_time"] = after_messages[4]["time"]
            else:
                # 如果没有足够的后续消息，保持原有的结束时间
                pass

            # 重新计算当前消息段的消息数量
            last_segment["message_count"] = self._count_messages_in_timerange(
                last_segment["start_time"], last_segment["end_time"]
            )

            # 创建新的消息段
            new_segment = {
                "start_time": potential_start_time,
                "end_time": message_time,
                "last_msg_time": message_time,
                "message_count": self._count_messages_in_timerange(potential_start_time, message_time),
            }
            segments.append(new_segment)
            logger.info(f"{self.log_prefix} 为用户 {person_id} 创建新消息段（超过10条消息间隔）: {new_segment}")

        self._save_cache()

    def _count_messages_in_timerange(self, start_time: float, end_time: float) -> int:
        """计算指定时间范围内的消息数量（包含边界）"""
        messages = get_raw_msg_by_timestamp_with_chat_inclusive(self.subheartflow_id, start_time, end_time)
        return len(messages)

    def _count_messages_between(self, start_time: float, end_time: float) -> int:
        """计算两个时间点之间的消息数量（不包含边界），用于间隔检查"""
        return num_new_messages_since(self.subheartflow_id, start_time, end_time)

    def _get_total_message_count(self, person_id: str) -> int:
        """获取用户所有消息段的总消息数量"""
        if person_id not in self.person_engaged_cache:
            return 0

        total_count = 0
        for segment in self.person_engaged_cache[person_id]:
            total_count += segment["message_count"]

        return total_count

    def _cleanup_old_segments(self) -> bool:
        """清理老旧的消息段

        Returns:
            bool: 是否执行了清理操作
        """
        if not SEGMENT_CLEANUP_CONFIG["enable_cleanup"]:
            return False

        current_time = time.time()

        # 检查是否需要执行清理（基于时间间隔）
        cleanup_interval_seconds = SEGMENT_CLEANUP_CONFIG["cleanup_interval_hours"] * 3600
        if current_time - self.last_cleanup_time < cleanup_interval_seconds:
            return False

        logger.info(f"{self.log_prefix} 开始执行老消息段清理...")

        cleanup_stats = {
            "users_cleaned": 0,
            "segments_removed": 0,
            "total_segments_before": 0,
            "total_segments_after": 0,
        }

        max_age_seconds = SEGMENT_CLEANUP_CONFIG["max_segment_age_days"] * 24 * 3600
        max_segments_per_user = SEGMENT_CLEANUP_CONFIG["max_segments_per_user"]

        users_to_remove = []

        for person_id, segments in self.person_engaged_cache.items():
            cleanup_stats["total_segments_before"] += len(segments)
            original_segment_count = len(segments)

            # 1. 按时间清理：移除过期的消息段
            segments_after_age_cleanup = []
            for segment in segments:
                segment_age = current_time - segment["end_time"]
                if segment_age <= max_age_seconds:
                    segments_after_age_cleanup.append(segment)
                else:
                    cleanup_stats["segments_removed"] += 1
                    logger.debug(
                        f"{self.log_prefix} 移除用户 {person_id} 的过期消息段: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(segment['start_time']))} - {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(segment['end_time']))}"
                    )

            # 2. 按数量清理：如果消息段数量仍然过多，保留最新的
            if len(segments_after_age_cleanup) > max_segments_per_user:
                # 按end_time排序，保留最新的
                segments_after_age_cleanup.sort(key=lambda x: x["end_time"], reverse=True)
                segments_removed_count = len(segments_after_age_cleanup) - max_segments_per_user
                cleanup_stats["segments_removed"] += segments_removed_count
                segments_after_age_cleanup = segments_after_age_cleanup[:max_segments_per_user]
                logger.debug(
                    f"{self.log_prefix} 用户 {person_id} 消息段数量过多，移除 {segments_removed_count} 个最老的消息段"
                )

            # 使用清理后的消息段

            # 更新缓存
            if len(segments_after_age_cleanup) == 0:
                # 如果没有剩余消息段，标记用户为待移除
                users_to_remove.append(person_id)
            else:
                self.person_engaged_cache[person_id] = segments_after_age_cleanup
                cleanup_stats["total_segments_after"] += len(segments_after_age_cleanup)

            if original_segment_count != len(segments_after_age_cleanup):
                cleanup_stats["users_cleaned"] += 1

        # 移除没有消息段的用户
        for person_id in users_to_remove:
            del self.person_engaged_cache[person_id]
            logger.debug(f"{self.log_prefix} 移除用户 {person_id}：没有剩余消息段")

        # 更新最后清理时间
        self.last_cleanup_time = current_time

        # 保存缓存
        if cleanup_stats["segments_removed"] > 0 or len(users_to_remove) > 0:
            self._save_cache()
            logger.info(
                f"{self.log_prefix} 清理完成 - 影响用户: {cleanup_stats['users_cleaned']}, 移除消息段: {cleanup_stats['segments_removed']}, 移除用户: {len(users_to_remove)}"
            )
            logger.info(
                f"{self.log_prefix} 消息段统计 - 清理前: {cleanup_stats['total_segments_before']}, 清理后: {cleanup_stats['total_segments_after']}"
            )
        else:
            logger.debug(f"{self.log_prefix} 清理完成 - 无需清理任何内容")

        return cleanup_stats["segments_removed"] > 0 or len(users_to_remove) > 0

    def force_cleanup_user_segments(self, person_id: str) -> bool:
        """强制清理指定用户的所有消息段

        Args:
            person_id: 用户ID

        Returns:
            bool: 是否成功清理
        """
        if person_id in self.person_engaged_cache:
            segments_count = len(self.person_engaged_cache[person_id])
            del self.person_engaged_cache[person_id]
            self._save_cache()
            logger.info(f"{self.log_prefix} 强制清理用户 {person_id} 的 {segments_count} 个消息段")
            return True
        return False

    def get_cache_status(self) -> str:
        """获取缓存状态信息，用于调试和监控"""
        if not self.person_engaged_cache:
            return f"{self.log_prefix} 关系缓存为空"

        status_lines = [f"{self.log_prefix} 关系缓存状态："]
        status_lines.append(
            f"最后处理消息时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_processed_message_time)) if self.last_processed_message_time > 0 else '未设置'}"
        )
        status_lines.append(
            f"最后清理时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_cleanup_time)) if self.last_cleanup_time > 0 else '未执行'}"
        )
        status_lines.append(f"总用户数：{len(self.person_engaged_cache)}")
        status_lines.append(
            f"清理配置：{'启用' if SEGMENT_CLEANUP_CONFIG['enable_cleanup'] else '禁用'} (最大保存{SEGMENT_CLEANUP_CONFIG['max_segment_age_days']}天, 每用户最多{SEGMENT_CLEANUP_CONFIG['max_segments_per_user']}段)"
        )
        status_lines.append("")

        for person_id, segments in self.person_engaged_cache.items():
            total_count = self._get_total_message_count(person_id)
            status_lines.append(f"用户 {person_id}:")
            status_lines.append(f"  总消息数：{total_count} ({total_count}/45)")
            status_lines.append(f"  消息段数：{len(segments)}")

            for i, segment in enumerate(segments):
                start_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(segment["start_time"]))
                end_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(segment["end_time"]))
                last_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(segment["last_msg_time"]))
                status_lines.append(
                    f"    段{i + 1}: {start_str} -> {end_str} (最后消息: {last_str}, 消息数: {segment['message_count']})"
                )
            status_lines.append("")

        return "\n".join(status_lines)

    # ================================
    # 主要处理流程
    # 统筹各模块协作、对外提供服务接口
    # ================================

    async def process_info(self, observations: List[Observation] = None, *infos) -> List[InfoBase]:
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
        observations: List[Observation] = None,
    ):
        """
        在回复前进行思考，生成内心想法并收集工具调用结果
        """
        # 0. 执行定期清理
        self._cleanup_old_segments()

        # 1. 从观察信息中提取所需数据
        # 需要兼容私聊

        chat_observe_info = ""
        current_time = time.time()
        if observations:
            for observation in observations:
                if isinstance(observation, ChattingObservation):
                    chat_observe_info = observation.get_observe_info()

                    # 从聊天观察中提取用户信息并更新消息段
                    # 获取最新的非bot消息来更新消息段
                    latest_messages = get_raw_msg_by_timestamp_with_chat(
                        self.subheartflow_id,
                        self.last_processed_message_time,
                        current_time,
                        limit=50,  # 获取自上次处理后的消息
                    )
                    if latest_messages:
                        # 处理所有新的非bot消息
                        for latest_msg in latest_messages:
                            user_id = latest_msg.get("user_id")
                            platform = latest_msg.get("user_platform") or latest_msg.get("chat_info_platform")
                            msg_time = latest_msg.get("time", 0)

                            if (
                                user_id
                                and platform
                                and user_id != global_config.bot.qq_account
                                and msg_time > self.last_processed_message_time
                            ):
                                from src.person_info.person_info import PersonInfoManager

                                person_id = PersonInfoManager.get_person_id(platform, user_id)
                                self._update_message_segments(person_id, msg_time)
                                logger.debug(
                                    f"{self.log_prefix} 更新用户 {person_id} 的消息段，消息时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg_time))}"
                                )
                                self.last_processed_message_time = max(self.last_processed_message_time, msg_time)
                    break

        # 1. 检查是否有用户达到关系构建条件（总消息数达到45条）
        users_to_build_relationship = []
        for person_id, segments in self.person_engaged_cache.items():
            total_message_count = self._get_total_message_count(person_id)
            if total_message_count >= 45:
                users_to_build_relationship.append(person_id)
                logger.info(
                    f"{self.log_prefix} 用户 {person_id} 满足关系构建条件，总消息数：{total_message_count}，消息段数：{len(segments)}"
                )
            elif total_message_count > 0:
                # 记录进度信息
                logger.debug(
                    f"{self.log_prefix} 用户 {person_id} 进度：{total_message_count}/45 条消息，{len(segments)} 个消息段"
                )

        # 2. 为满足条件的用户构建关系
        for person_id in users_to_build_relationship:
            segments = self.person_engaged_cache[person_id]
            # 异步执行关系构建
            asyncio.create_task(self.update_impression_on_segments(person_id, self.subheartflow_id, segments))
            # 移除已处理的用户缓存
            del self.person_engaged_cache[person_id]
            self._save_cache()

        # 2. 减少info_fetched_cache中所有信息的TTL
        for person_id in list(self.info_fetched_cache.keys()):
            for info_type in list(self.info_fetched_cache[person_id].keys()):
                self.info_fetched_cache[person_id][info_type]["ttl"] -= 1
                if self.info_fetched_cache[person_id][info_type]["ttl"] <= 0:
                    # 在删除前查找匹配的info_fetching_cache记录
                    matched_record = None
                    min_time_diff = float("inf")
                    for record in self.info_fetching_cache:
                        if (
                            record["person_id"] == person_id
                            and record["info_type"] == info_type
                            and not record["forget"]
                        ):
                            time_diff = abs(
                                record["start_time"] - self.info_fetched_cache[person_id][info_type]["start_time"]
                            )
                            if time_diff < min_time_diff:
                                min_time_diff = time_diff
                                matched_record = record

                    if matched_record:
                        matched_record["forget"] = True
                        logger.info(f"{self.log_prefix} 用户 {person_id} 的 {info_type} 信息已过期，标记为遗忘。")

                    del self.info_fetched_cache[person_id][info_type]
            if not self.info_fetched_cache[person_id]:
                del self.info_fetched_cache[person_id]

        # 5. 为需要处理的人员准备LLM prompt
        nickname_str = ",".join(global_config.bot.alias_names)
        name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"

        info_cache_block = ""
        if self.info_fetching_cache:
            for info_fetching in self.info_fetching_cache:
                if info_fetching["forget"]:
                    info_cache_block += f"在{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info_fetching['start_time']))}，你回忆了[{info_fetching['person_name']}]的[{info_fetching['info_type']}]，但是现在你忘记了\n"
                else:
                    info_cache_block += f"在{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info_fetching['start_time']))}，你回忆了[{info_fetching['person_name']}]的[{info_fetching['info_type']}]，还记着呢\n"

        prompt = (await global_prompt_manager.get_prompt_async("relationship_prompt")).format(
            name_block=name_block,
            time_now=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            chat_observe_info=chat_observe_info,
            info_cache_block=info_cache_block,
        )

        try:
            # logger.debug(f"{self.log_prefix} 人物信息prompt: \n{prompt}\n")
            content, _ = await self.llm_model.generate_response_async(prompt=prompt)
            if content:
                # print(f"content: {content}")
                content_json = json.loads(repair_json(content))

                # 收集即时提取任务
                instant_tasks = []
                async_tasks = []

                person_info_manager = get_person_info_manager()
                for person_name, info_type in content_json.items():
                    person_id = person_info_manager.get_person_id_by_person_name(person_name)
                    if person_id:
                        self.info_fetching_cache.append(
                            {
                                "person_id": person_id,
                                "person_name": person_name,
                                "info_type": info_type,
                                "start_time": time.time(),
                                "forget": False,
                            }
                        )
                        if len(self.info_fetching_cache) > 20:
                            self.info_fetching_cache.pop(0)
                    else:
                        logger.warning(f"{self.log_prefix} 未找到用户 {person_name} 的ID，跳过调取信息。")
                        continue

                    logger.info(f"{self.log_prefix} 调取用户 {person_name} 的 {info_type} 信息。")

                    # 这里不需要检查person_engaged_cache，因为消息段的管理由_update_message_segments处理
                    # 信息提取和消息段管理是独立的流程

                    if ENABLE_INSTANT_INFO_EXTRACTION:
                        # 收集即时提取任务
                        instant_tasks.append((person_id, info_type, time.time()))
                    else:
                        # 使用原来的异步模式
                        async_tasks.append(
                            asyncio.create_task(self.fetch_person_info(person_id, [info_type], start_time=time.time()))
                        )

                # 执行即时提取任务
                if ENABLE_INSTANT_INFO_EXTRACTION and instant_tasks:
                    await self._execute_instant_extraction_batch(instant_tasks)

                # 启动异步任务（如果不是即时模式）
                if async_tasks:
                    # 异步任务不需要等待完成
                    pass

            else:
                logger.warning(f"{self.log_prefix} LLM返回空结果，关系识别失败。")

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行LLM请求或处理响应时出错: {e}")
            logger.error(traceback.format_exc())

        # 7. 合并缓存和新处理的信息
        persons_infos_str = ""
        # 处理已获取到的信息
        if self.info_fetched_cache:
            for person_id in self.info_fetched_cache:
                person_infos_str = ""
                for info_type in self.info_fetched_cache[person_id]:
                    person_name = self.info_fetched_cache[person_id][info_type]["person_name"]
                    if not self.info_fetched_cache[person_id][info_type]["unknow"]:
                        info_content = self.info_fetched_cache[person_id][info_type]["info"]
                        person_infos_str += f"[{info_type}]：{info_content}；"
                    else:
                        person_infos_str += f"你不了解{person_name}有关[{info_type}]的信息，不要胡乱回答，你可以直接说你不知道，或者你忘记了；"
                if person_infos_str:
                    persons_infos_str += f"你对 {person_name} 的了解：{person_infos_str}\n"

        # 处理正在调取但还没有结果的项目（只在非即时提取模式下显示）
        if not ENABLE_INSTANT_INFO_EXTRACTION:
            pending_info_dict = {}
            for record in self.info_fetching_cache:
                if not record["forget"]:
                    current_time = time.time()
                    # 只处理不超过2分钟的调取请求，避免过期请求一直显示
                    if current_time - record["start_time"] <= 120:  # 10分钟内的请求
                        person_id = record["person_id"]
                        person_name = record["person_name"]
                        info_type = record["info_type"]

                        # 检查是否已经在info_fetched_cache中有结果
                        if person_id in self.info_fetched_cache and info_type in self.info_fetched_cache[person_id]:
                            continue

                        # 按人物组织正在调取的信息
                        if person_name not in pending_info_dict:
                            pending_info_dict[person_name] = []
                        pending_info_dict[person_name].append(info_type)

            # 添加正在调取的信息到返回字符串
            for person_name, info_types in pending_info_dict.items():
                info_types_str = "、".join(info_types)
                persons_infos_str += f"你正在识图回忆有关 {person_name} 的 {info_types_str} 信息，稍等一下再回答...\n"

        return persons_infos_str

    # ================================
    # 关系构建模块
    # 负责触发关系构建、整合消息段、更新用户印象
    # ================================

    async def update_impression_on_segments(self, person_id: str, chat_id: str, segments: List[Dict[str, any]]):
        """
        基于消息段更新用户印象

        Args:
            person_id: 用户ID
            chat_id: 聊天ID
            segments: 消息段列表
        """
        logger.info(f"开始为 {person_id} 基于 {len(segments)} 个消息段更新印象")
        try:
            processed_messages = []

            for i, segment in enumerate(segments):
                start_time = segment["start_time"]
                end_time = segment["end_time"]
                segment["message_count"]
                start_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_time))

                # 获取该段的消息（包含边界）
                segment_messages = get_raw_msg_by_timestamp_with_chat_inclusive(
                    self.subheartflow_id, start_time, end_time
                )
                logger.info(
                    f"消息段 {i + 1}: {start_date} - {time.strftime('%Y-%m-%d %H:%M', time.localtime(end_time))}, 消息数: {len(segment_messages)}"
                )

                if segment_messages:
                    # 如果不是第一个消息段，在消息列表前添加间隔标识
                    if i > 0:
                        # 创建一个特殊的间隔消息
                        gap_message = {
                            "time": start_time - 0.1,  # 稍微早于段开始时间
                            "user_id": "system",
                            "user_platform": "system",
                            "user_nickname": "系统",
                            "user_cardname": "",
                            "display_message": f"...（中间省略一些消息）{start_date} 之后的消息如下...",
                            "is_action_record": True,
                            "chat_info_platform": segment_messages[0].get("chat_info_platform", ""),
                            "chat_id": chat_id,
                        }
                        processed_messages.append(gap_message)

                    # 添加该段的所有消息
                    processed_messages.extend(segment_messages)

            if processed_messages:
                # 按时间排序所有消息（包括间隔标识）
                processed_messages.sort(key=lambda x: x["time"])

                logger.info(f"为 {person_id} 获取到总共 {len(processed_messages)} 条消息（包含间隔标识）用于印象更新")
                relationship_manager = get_relationship_manager()

                # 调用原有的更新方法
                await relationship_manager.update_person_impression(
                    person_id=person_id, timestamp=time.time(), bot_engaged_messages=processed_messages
                )
            else:
                logger.info(f"没有找到 {person_id} 的消息段对应的消息，不更新印象")

        except Exception as e:
            logger.error(f"为 {person_id} 更新印象时发生错误: {e}")
            logger.error(traceback.format_exc())

    # ================================
    # 信息调取模块
    # 负责实时分析对话需求、提取用户信息、管理信息缓存
    # ================================

    async def _execute_instant_extraction_batch(self, instant_tasks: list):
        """
        批量执行即时提取任务
        """
        if not instant_tasks:
            return

        logger.info(f"{self.log_prefix} [即时提取] 开始批量提取 {len(instant_tasks)} 个信息")

        # 创建所有提取任务
        extraction_tasks = []
        for person_id, info_type, start_time in instant_tasks:
            # 检查缓存中是否已存在且未过期的信息
            if person_id in self.info_fetched_cache and info_type in self.info_fetched_cache[person_id]:
                logger.info(f"{self.log_prefix} 用户 {person_id} 的 {info_type} 信息已存在且未过期，跳过调取。")
                continue

            task = asyncio.create_task(self._fetch_single_info_instant(person_id, info_type, start_time))
            extraction_tasks.append(task)

        # 并行执行所有提取任务并等待完成
        if extraction_tasks:
            await asyncio.gather(*extraction_tasks, return_exceptions=True)
            logger.info(f"{self.log_prefix} [即时提取] 批量提取完成")

    async def _fetch_single_info_instant(self, person_id: str, info_type: str, start_time: float):
        """
        使用小模型提取单个信息类型
        """
        person_info_manager = get_person_info_manager()
        nickname_str = ",".join(global_config.bot.alias_names)
        name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"

        person_name = await person_info_manager.get_value(person_id, "person_name")

        person_impression = await person_info_manager.get_value(person_id, "impression")
        if not person_impression:
            impression_block = "你对ta没有什么深刻的印象"
        else:
            impression_block = f"{person_impression}"

        points = await person_info_manager.get_value(person_id, "points")
        if points:
            points_text = "\n".join([f"{point[2]}:{point[0]}" for point in points])
        else:
            points_text = "你不记得ta最近发生了什么"

        prompt = (await global_prompt_manager.get_prompt_async("fetch_info_prompt")).format(
            name_block=name_block,
            info_type=info_type,
            person_impression=impression_block,
            person_name=person_name,
            info_json_str=f'"{info_type}": "信息内容"',
            points_text=points_text,
        )

        try:
            # 使用小模型进行即时提取
            content, _ = await self.instant_llm_model.generate_response_async(prompt=prompt)

            logger.info(f"{self.log_prefix} [即时提取] {person_name} 的 {info_type} 结果: {content}")

            if content:
                content_json = json.loads(repair_json(content))
                if info_type in content_json:
                    info_content = content_json[info_type]
                    if info_content != "none" and info_content:
                        if person_id not in self.info_fetched_cache:
                            self.info_fetched_cache[person_id] = {}
                        self.info_fetched_cache[person_id][info_type] = {
                            "info": info_content,
                            "ttl": 8,  # 小模型提取的信息TTL稍短
                            "start_time": start_time,
                            "person_name": person_name,
                            "unknow": False,
                        }
                        logger.info(
                            f"{self.log_prefix} [即时提取] 成功获取 {person_name} 的 {info_type}: {info_content}"
                        )
                    else:
                        if person_id not in self.info_fetched_cache:
                            self.info_fetched_cache[person_id] = {}
                        self.info_fetched_cache[person_id][info_type] = {
                            "info": "unknow",
                            "ttl": 8,
                            "start_time": start_time,
                            "person_name": person_name,
                            "unknow": True,
                        }
                        logger.info(f"{self.log_prefix} [即时提取] {person_name} 的 {info_type} 信息不明确")
            else:
                logger.warning(
                    f"{self.log_prefix} [即时提取] 小模型返回空结果，获取 {person_name} 的 {info_type} 信息失败。"
                )
        except Exception as e:
            logger.error(f"{self.log_prefix} [即时提取] 执行小模型请求获取用户信息时出错: {e}")
            logger.error(traceback.format_exc())

    async def fetch_person_info(self, person_id: str, info_types: list[str], start_time: float):
        """
        获取某个人的信息
        """
        # 检查缓存中是否已存在且未过期的信息
        info_types_to_fetch = []

        for info_type in info_types:
            if person_id in self.info_fetched_cache and info_type in self.info_fetched_cache[person_id]:
                logger.info(f"{self.log_prefix} 用户 {person_id} 的 {info_type} 信息已存在且未过期，跳过调取。")
                continue
            info_types_to_fetch.append(info_type)

        if not info_types_to_fetch:
            return

        nickname_str = ",".join(global_config.bot.alias_names)
        name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"

        person_info_manager = get_person_info_manager()
        person_name = await person_info_manager.get_value(person_id, "person_name")

        info_type_str = ""
        info_json_str = ""
        for info_type in info_types_to_fetch:
            info_type_str += f"{info_type},"
            info_json_str += f'"{info_type}": "信息内容",'
        info_type_str = info_type_str[:-1]
        info_json_str = info_json_str[:-1]

        person_impression = await person_info_manager.get_value(person_id, "impression")
        if not person_impression:
            impression_block = "你对ta没有什么深刻的印象"
        else:
            impression_block = f"{person_impression}"

        points = await person_info_manager.get_value(person_id, "points")

        if points:
            points_text = "\n".join([f"{point[2]}:{point[0]}" for point in points])
        else:
            points_text = "你不记得ta最近发生了什么"

        prompt = (await global_prompt_manager.get_prompt_async("fetch_info_prompt")).format(
            name_block=name_block,
            info_type=info_type_str,
            person_impression=impression_block,
            person_name=person_name,
            info_json_str=info_json_str,
            points_text=points_text,
        )

        try:
            content, _ = await self.llm_model.generate_response_async(prompt=prompt)

            # logger.info(f"{self.log_prefix} fetch_person_info prompt: \n{prompt}\n")
            logger.info(f"{self.log_prefix} fetch_person_info 结果: {content}")

            if content:
                try:
                    content_json = json.loads(repair_json(content))
                    for info_type, info_content in content_json.items():
                        if info_content != "none" and info_content:
                            if person_id not in self.info_fetched_cache:
                                self.info_fetched_cache[person_id] = {}
                            self.info_fetched_cache[person_id][info_type] = {
                                "info": info_content,
                                "ttl": 10,
                                "start_time": start_time,
                                "person_name": person_name,
                                "unknow": False,
                            }
                        else:
                            if person_id not in self.info_fetched_cache:
                                self.info_fetched_cache[person_id] = {}

                            self.info_fetched_cache[person_id][info_type] = {
                                "info": "unknow",
                                "ttl": 10,
                                "start_time": start_time,
                                "person_name": person_name,
                                "unknow": True,
                            }
                except Exception as e:
                    logger.error(f"{self.log_prefix} 解析LLM返回的信息时出错: {e}")
                    logger.error(traceback.format_exc())
            else:
                logger.warning(f"{self.log_prefix} LLM返回空结果，获取用户 {person_name} 的 {info_type_str} 信息失败。")
        except Exception as e:
            logger.error(f"{self.log_prefix} 执行LLM请求获取用户信息时出错: {e}")
            logger.error(traceback.format_exc())


init_prompt()
