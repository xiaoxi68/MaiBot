import ast
import random
import json
import os
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from src.common.logger import get_logger
from src.config.config import global_config
from src.llm_models.utils_model import LLMRequest
from src.chat.message_receive.message import UserInfo, Seg, MessageRecv, MessageSending
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.message_receive.uni_message_sender import HeartFCSender
from src.chat.utils.timer_calculator import Timer  # <--- Import Timer
from src.chat.utils.utils import get_chat_type_and_target_info
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.utils.chat_message_builder import build_readable_messages, get_raw_msg_before_timestamp_with_chat
from src.chat.express.expression_selector import expression_selector
from src.chat.knowledge.knowledge_lib import qa_manager
from src.chat.memory_system.memory_activator import MemoryActivator
from src.mood.mood_manager import mood_manager
from src.person_info.relationship_fetcher import relationship_fetcher_manager
from src.person_info.person_info import get_person_info_manager
from src.tools.tool_executor import ToolExecutor
from src.plugin_system.base.component_types import ActionInfo
from typing import Optional
from rich.traceback import install

from src.common.logger import get_logger
from src.config.config import global_config
from src.llm_models.utils_model import LLMRequest
from src.person_info.person_info import get_person_info_manager
from .personality import Personality

install(extra_lines=3)

logger = get_logger("individuality")


class Individuality:
    """个体特征管理类"""

    def __init__(self):
        # 正常初始化实例属性
        self.personality: Personality = None  # type: ignore

        self.name = ""
        self.bot_person_id = ""
        self.meta_info_file_path = "data/personality/meta.json"

        self.model = LLMRequest(
            model=global_config.model.utils,
            request_type="individuality.compress",
        )

    async def initialize(self) -> None:
        """初始化个体特征

        Args:
            bot_nickname: 机器人昵称
            personality_core: 人格核心特点
            personality_side: 人格侧面描述
            identity: 身份细节描述
        """
        bot_nickname=global_config.bot.nickname
        personality_core=global_config.personality.personality_core
        personality_side=global_config.personality.personality_side
        identity=global_config.personality.identity
        
        logger.info("正在初始化个体特征")
        person_info_manager = get_person_info_manager()
        self.bot_person_id = person_info_manager.get_person_id("system", "bot_id")
        self.name = bot_nickname

        # 检查配置变化，如果变化则清空
        personality_changed, identity_changed = await self._check_config_and_clear_if_changed(
            bot_nickname, personality_core, personality_side, identity
        )

        # 初始化人格（现在包含身份）
        self.personality = Personality.initialize(
            bot_nickname=bot_nickname,
            personality_core=personality_core,
            personality_side=personality_side,
            identity=identity,
            compress_personality=global_config.personality.compress_personality,
            compress_identity=global_config.personality.compress_identity,
        )

        logger.info("正在将所有人设写入impression")
        # 将所有人设写入impression
        impression_parts = []
        if personality_core:
            impression_parts.append(f"核心人格: {personality_core}")
        if personality_side:
            impression_parts.append(f"人格侧面: {personality_side}")
        if identity:
            impression_parts.append(f"身份: {identity}")
        logger.info(f"impression_parts: {impression_parts}")

        impression_text = "。".join(impression_parts)
        if impression_text:
            impression_text += "。"

        if impression_text:
            update_data = {
                "platform": "system",
                "user_id": "bot_id",
                "person_name": self.name,
                "nickname": self.name,
            }

            await person_info_manager.update_one_field(
                self.bot_person_id, "impression", impression_text, data=update_data
            )
            logger.debug("已将完整人设更新到bot的impression中")

        # 根据变化情况决定是否重新创建
        personality_result = None
        identity_result = None

        if personality_changed:
            logger.info("检测到人格配置变化，重新生成压缩版本")
            personality_result = await self._create_personality(personality_core, personality_side)
        else:
            logger.info("人格配置未变化，使用缓存版本")
            # 从缓存中获取已有的personality结果
            existing_short_impression = await person_info_manager.get_value(self.bot_person_id, "short_impression")
            if existing_short_impression:
                try:
                    existing_data = ast.literal_eval(existing_short_impression)  # type: ignore
                    if isinstance(existing_data, list) and len(existing_data) >= 1:
                        personality_result = existing_data[0]
                except (json.JSONDecodeError, TypeError, IndexError):
                    logger.warning("无法解析现有的short_impression，将重新生成人格部分")
                    personality_result = await self._create_personality(personality_core, personality_side)
            else:
                logger.info("未找到现有的人格缓存，重新生成")
                personality_result = await self._create_personality(personality_core, personality_side)

        if identity_changed:
            logger.info("检测到身份配置变化，重新生成压缩版本")
            identity_result = await self._create_identity(identity)
        else:
            logger.info("身份配置未变化，使用缓存版本")
            # 从缓存中获取已有的identity结果
            existing_short_impression = await person_info_manager.get_value(self.bot_person_id, "short_impression")
            if existing_short_impression:
                try:
                    existing_data = ast.literal_eval(existing_short_impression)  # type: ignore
                    if isinstance(existing_data, list) and len(existing_data) >= 2:
                        identity_result = existing_data[1]
                except (json.JSONDecodeError, TypeError, IndexError):
                    logger.warning("无法解析现有的short_impression，将重新生成身份部分")
                    identity_result = await self._create_identity(identity)
            else:
                logger.info("未找到现有的身份缓存，重新生成")
                identity_result = await self._create_identity(identity)

        result = [personality_result, identity_result]

        # 更新short_impression字段
        if personality_result and identity_result:
            person_info_manager = get_person_info_manager()
            await person_info_manager.update_one_field(self.bot_person_id, "short_impression", result)
            logger.info("已将人设构建")
        else:
            logger.error("人设构建失败")


    async def get_personality_block(self) -> str:
        person_info_manager = get_person_info_manager()
        bot_person_id = person_info_manager.get_person_id("system", "bot_id")
        
        bot_name = global_config.bot.nickname
        if global_config.bot.alias_names:
            bot_nickname = f",也有人叫你{','.join(global_config.bot.alias_names)}"
        else:
            bot_nickname = ""
        short_impression = await person_info_manager.get_value(bot_person_id, "short_impression")
        # 解析字符串形式的Python列表
        try:
            if isinstance(short_impression, str) and short_impression.strip():
                short_impression = ast.literal_eval(short_impression)
            elif not short_impression:
                logger.warning("short_impression为空，使用默认值")
                short_impression = ["友好活泼", "人类"]
        except (ValueError, SyntaxError) as e:
            logger.error(f"解析short_impression失败: {e}, 原始值: {short_impression}")
            short_impression = ["友好活泼", "人类"]
        # 确保short_impression是列表格式且有足够的元素
        if not isinstance(short_impression, list) or len(short_impression) < 2:
            logger.warning(f"short_impression格式不正确: {short_impression}, 使用默认值")
            short_impression = ["友好活泼", "人类"]
        personality = short_impression[0]
        identity = short_impression[1]
        prompt_personality = f"{personality}，{identity}"
        identity_block = f"你的名字是{bot_name}{bot_nickname}，你{prompt_personality}："
        
        return identity_block


    def _get_config_hash(
        self, bot_nickname: str, personality_core: str, personality_side: str, identity: list
    ) -> tuple[str, str]:
        """获取personality和identity配置的哈希值

        Returns:
            tuple: (personality_hash, identity_hash)
        """
        # 人格配置哈希
        personality_config = {
            "nickname": bot_nickname,
            "personality_core": personality_core,
            "personality_side": personality_side,
            "compress_personality": self.personality.compress_personality if self.personality else True,
        }
        personality_str = json.dumps(personality_config, sort_keys=True)
        personality_hash = hashlib.md5(personality_str.encode("utf-8")).hexdigest()

        # 身份配置哈希
        identity_config = {
            "identity": sorted(identity),
            "compress_identity": self.personality.compress_identity if self.personality else True,
        }
        identity_str = json.dumps(identity_config, sort_keys=True)
        identity_hash = hashlib.md5(identity_str.encode("utf-8")).hexdigest()

        return personality_hash, identity_hash

    async def _check_config_and_clear_if_changed(
        self, bot_nickname: str, personality_core: str, personality_side: str, identity: list
    ) -> tuple[bool, bool]:
        """检查配置是否发生变化，如果变化则清空相应缓存

        Returns:
            tuple: (personality_changed, identity_changed)
        """
        person_info_manager = get_person_info_manager()
        current_personality_hash, current_identity_hash = self._get_config_hash(
            bot_nickname, personality_core, personality_side, identity
        )

        meta_info = self._load_meta_info()
        stored_personality_hash = meta_info.get("personality_hash")
        stored_identity_hash = meta_info.get("identity_hash")

        personality_changed = current_personality_hash != stored_personality_hash
        identity_changed = current_identity_hash != stored_identity_hash

        if personality_changed:
            logger.info("检测到人格配置发生变化")

        if identity_changed:
            logger.info("检测到身份配置发生变化")

        # 如果任何一个发生变化，都需要清空info_list（因为这影响整体人设）
        if personality_changed or identity_changed:
            logger.info("将清空原有的关键词缓存")
            update_data = {
                "platform": "system",
                "user_id": "bot_id",
                "person_name": self.name,
                "nickname": self.name,
            }
            await person_info_manager.update_one_field(self.bot_person_id, "info_list", [], data=update_data)

        # 更新元信息文件
        new_meta_info = {
            "personality_hash": current_personality_hash,
            "identity_hash": current_identity_hash,
        }
        self._save_meta_info(new_meta_info)

        return personality_changed, identity_changed

    def _load_meta_info(self) -> dict:
        """从JSON文件中加载元信息"""
        if os.path.exists(self.meta_info_file_path):
            try:
                with open(self.meta_info_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"读取meta_info文件失败: {e}, 将创建新文件。")
                return {}
        return {}

    def _save_meta_info(self, meta_info: dict):
        """将元信息保存到JSON文件"""
        try:
            os.makedirs(os.path.dirname(self.meta_info_file_path), exist_ok=True)
            with open(self.meta_info_file_path, "w", encoding="utf-8") as f:
                json.dump(meta_info, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存meta_info文件失败: {e}")


    async def _create_personality(self, personality_core: str, personality_side: str) -> str:
        # sourcery skip: merge-list-append, move-assign
        """使用LLM创建压缩版本的impression

        Args:
            personality_core: 核心人格
            personality_side: 人格侧面列表

        Returns:
            str: 压缩后的impression文本
        """
        logger.info("正在构建人格.........")

        # 核心人格保持不变
        personality_parts = []
        if personality_core:
            personality_parts.append(f"{personality_core}")

        # 准备需要压缩的内容
        if self.personality.compress_personality:
            personality_to_compress = f"人格特质: {personality_side}"

            prompt = f"""请将以下人格信息进行简洁压缩，保留主要内容，用简练的中文表达：
{personality_to_compress}

要求：
1. 保持原意不变，尽量使用原文
2. 尽量简洁，不超过30字
3. 直接输出压缩后的内容，不要解释"""

            response, (_, _) = await self.model.generate_response_async(
                prompt=prompt,
            )

            if response.strip():
                personality_parts.append(response.strip())
                logger.info(f"精简人格侧面: {response.strip()}")
            else:
                logger.error(f"使用LLM压缩人设时出错: {response}")
            if personality_parts:
                personality_result = "。".join(personality_parts)
            else:
                personality_result = personality_core
        else:
            personality_result = personality_core
            if personality_side:
                personality_result += f"，{personality_side}"

        return personality_result

    async def _create_identity(self, identity: list) -> str:
        """使用LLM创建压缩版本的impression"""
        logger.info("正在构建身份.........")

        if self.personality.compress_identity:
            identity_to_compress = f"身份背景: {identity}"

            prompt = f"""请将以下身份信息进行简洁压缩，保留主要内容，用简练的中文表达：
{identity_to_compress}

要求：
1. 保持原意不变，尽量使用原文
2. 尽量简洁，不超过30字
3. 直接输出压缩后的内容，不要解释"""

            response, (_, _) = await self.model.generate_response_async(
                prompt=prompt,
            )

            if response.strip():
                identity_result = response.strip()
                logger.info(f"精简身份: {identity_result}")
            else:
                logger.error(f"使用LLM压缩身份时出错: {response}")
        else:
            identity_result = "。".join(identity)

        return identity_result


individuality = None


def get_individuality():
    global individuality
    if individuality is None:
        individuality = Individuality()
    return individuality
