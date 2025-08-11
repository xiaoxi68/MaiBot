import time
import json
import re
import asyncio
from typing import Any, Optional

from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest
from src.chat.utils.chat_message_builder import (
    get_raw_msg_by_timestamp_with_chat_inclusive,
    build_readable_messages,
)
from src.person_info.group_info import get_group_info_manager
from src.plugin_system.apis import message_api
from json_repair import repair_json


logger = get_logger("group_relationship_manager")


class GroupRelationshipManager:
    def __init__(self):
        self.group_llm = LLMRequest(
            model_set=model_config.model_task_config.utils, request_type="relationship.group"
        )
        self.last_group_impression_time = 0.0
        self.last_group_impression_message_count = 0

    async def build_relation(self, chat_id: str, platform: str) -> None:
        """构建群关系，类似 relationship_builder.build_relation() 的调用方式"""
        current_time = time.time()
        talk_frequency = global_config.chat.get_current_talk_frequency(chat_id)
        
        # 计算间隔时间，基于活跃度动态调整：最小10分钟，最大30分钟
        interval_seconds = max(600, int(1800 / max(0.5, talk_frequency)))

        # 统计新消息数量
        # 先获取所有新消息，然后过滤掉麦麦的消息和命令消息
        all_new_messages = message_api.get_messages_by_time_in_chat(
            chat_id=chat_id,
            start_time=self.last_group_impression_time,
            end_time=current_time,
            filter_mai=True,
            filter_command=True,
        )
        new_messages_since_last_impression = len(all_new_messages)

        # 触发条件：时间间隔 OR 消息数量阈值
        if (current_time - self.last_group_impression_time >= interval_seconds) or \
           (new_messages_since_last_impression >= 100):
            logger.info(f"[{chat_id}] 触发群印象构建 (时间间隔: {current_time - self.last_group_impression_time:.0f}s, 消息数: {new_messages_since_last_impression})")
            
            # 异步执行群印象构建
            asyncio.create_task(
                self.build_group_impression(
                    chat_id=chat_id,
                    platform=platform,
                    lookback_hours=12,
                    max_messages=300
                )
            )
            
            self.last_group_impression_time = current_time
            self.last_group_impression_message_count = 0
        else:
            # 更新消息计数
            self.last_group_impression_message_count = new_messages_since_last_impression
            logger.debug(f"[{chat_id}] 群印象构建等待中 (时间: {current_time - self.last_group_impression_time:.0f}s/{interval_seconds}s, 消息: {new_messages_since_last_impression}/100)")

    async def build_group_impression(
        self,
        chat_id: str,
        platform: str,
        lookback_hours: int = 24,
        max_messages: int = 300,
    ) -> Optional[str]:
        """基于最近聊天记录构建群印象并存储
        返回生成的topic
        """
        now = time.time()
        start_ts = now - lookback_hours * 3600

        # 拉取最近消息（包含边界）
        messages = get_raw_msg_by_timestamp_with_chat_inclusive(chat_id, start_ts, now)
        if not messages:
            logger.info(f"[{chat_id}] 无近期消息，跳过群印象构建")
            return None

        # 限制数量，优先最新
        messages = sorted(messages, key=lambda m: m.get("time", 0))[-max_messages:]

        # 构建可读文本
        readable = build_readable_messages(
            messages=messages, replace_bot_name=True, timestamp_mode="normal_no_YMD", truncate=True
        )
        if not readable:
            logger.info(f"[{chat_id}] 构建可读消息文本为空，跳过")
            return None

        # 确保群存在
        group_info_manager = get_group_info_manager()
        group_id = await group_info_manager.get_or_create_group(platform, chat_id)

        group_name = await group_info_manager.get_value(group_id, "group_name") or chat_id
        alias_str = ", ".join(global_config.bot.alias_names)

        prompt = f"""
你的名字是{global_config.bot.nickname}，{global_config.bot.nickname}的别名是{alias_str}。
你现在在群「{group_name}」（平台：{platform}）中。
请你根据以下群内最近的聊天记录，总结这个群给你的印象。

要求：
- 关注群的氛围（友好/活跃/娱乐/学习/严肃等）、常见话题、互动风格、活跃时段或频率、是否有显著文化/梗。
- 用白话表达，避免夸张或浮夸的词汇；语气自然、接地气。
- 不要暴露任何个人隐私信息。
- 请严格按照json格式输出，不要有其他多余内容：
{{
  "impression": "不超过200字的群印象长描述，白话、自然",
  "topic": "一句话概括群主要聊什么，白话"
}}

群内聊天（节选）：
{readable}
"""
        # 生成印象
        content, _ = await self.group_llm.generate_response_async(prompt=prompt)
        raw_text = (content or "").strip()

        def _strip_code_fences(text: str) -> str:
            if text.startswith("```") and text.endswith("```"):
                # 去除首尾围栏
                return re.sub(r"^```[a-zA-Z0-9_\-]*\n|\n```$", "", text, flags=re.S)
            # 提取围栏中的主体
            match = re.search(r"```[a-zA-Z0-9_\-]*\n([\s\S]*?)\n```", text)
            return match.group(1) if match else text

        parsed_text = _strip_code_fences(raw_text)

        long_impression: str = ""
        topic_val: Any = ""

        # 参考关系模块：先repair_json再loads，兼容返回列表/字典/字符串
        try:
            fixed = repair_json(parsed_text)
            data = json.loads(fixed) if isinstance(fixed, str) else fixed
            if isinstance(data, list) and data and isinstance(data[0], dict):
                data = data[0]
            if isinstance(data, dict):
                long_impression = str(data.get("impression") or "").strip()
                topic_val = data.get("topic", "")
            else:
                # 不是字典，直接作为文本
                text_fallback = str(data)
                long_impression = text_fallback[:400].strip()
                topic_val = ""
        except Exception:
            long_impression = parsed_text[:400].strip()
            topic_val = ""

        # 兜底
        if not long_impression and not topic_val:
            logger.info(f"[{chat_id}] LLM未产生有效群印象，跳过")
            return None

        # 写入数据库
        await group_info_manager.update_one_field(group_id, "group_impression", long_impression)
        if topic_val:
            await group_info_manager.update_one_field(group_id, "topic", topic_val)
        await group_info_manager.update_one_field(group_id, "last_active", now)

        logger.info(f"[{chat_id}] 群印象更新完成: topic={topic_val}")
        return str(topic_val) if topic_val else ""


group_relationship_manager: Optional[GroupRelationshipManager] = None


def get_group_relationship_manager() -> GroupRelationshipManager:
    global group_relationship_manager
    if group_relationship_manager is None:
        group_relationship_manager = GroupRelationshipManager()
    return group_relationship_manager
