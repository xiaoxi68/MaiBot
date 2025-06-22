from typing import Optional
import asyncio
from .personality import Personality
from .identity import Identity
from .expression_style import PersonalityExpression
import random
import json
import os
import hashlib
from rich.traceback import install
from src.common.logger import get_logger
from src.person_info.person_info import get_person_info_manager

install(extra_lines=3)

logger = get_logger("individuality")


class Individuality:
    """个体特征管理类"""

    def __init__(self):
        # 正常初始化实例属性
        self.personality: Optional[Personality] = None
        self.identity: Optional[Identity] = None
        self.express_style: PersonalityExpression = PersonalityExpression()

        self.name = ""
        self.bot_person_id = ""
        self.meta_info_file_path = "data/personality/meta.json"

    async def initialize(
        self,
        bot_nickname: str,
        personality_core: str,
        personality_sides: list,
        identity_detail: list,
    ) -> None:
        """初始化个体特征

        Args:
            bot_nickname: 机器人昵称
            personality_core: 人格核心特点
            personality_sides: 人格侧面描述
            identity_detail: 身份细节描述
        """
        person_info_manager = get_person_info_manager()
        self.bot_person_id = person_info_manager.get_person_id("system", "bot_id")
        self.name = bot_nickname

        # 检查配置变化，如果变化则清空
        await self._check_config_and_clear_if_changed(
            bot_nickname, personality_core, personality_sides, identity_detail
        )

        # 初始化人格
        self.personality = Personality.initialize(
            bot_nickname=bot_nickname, personality_core=personality_core, personality_sides=personality_sides
        )

        # 初始化身份
        self.identity = Identity(identity_detail=identity_detail)

        # 将所有人设写入impression
        impression_parts = []
        if personality_core:
            impression_parts.append(f"核心人格: {personality_core}")
        if personality_sides:
            impression_parts.append(f"人格侧面: {'、'.join(personality_sides)}")
        if identity_detail:
            impression_parts.append(f"身份: {'、'.join(identity_detail)}")

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
            logger.info("已将完整人设更新到bot的impression中")

        asyncio.create_task(self.express_style.extract_and_store_personality_expressions())

    def to_dict(self) -> dict:
        """将个体特征转换为字典格式"""
        return {
            "personality": self.personality.to_dict() if self.personality else None,
            "identity": self.identity.to_dict() if self.identity else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Individuality":
        """从字典创建个体特征实例"""
        instance = cls()
        if data.get("personality"):
            instance.personality = Personality.from_dict(data["personality"])
        if data.get("identity"):
            instance.identity = Identity.from_dict(data["identity"])
        return instance

    def get_personality_prompt(self, level: int, x_person: int = 2) -> str:
        """
        获取人格特征的prompt

        Args:
            level (int): 详细程度 (1: 核心, 2: 核心+随机侧面, 3: 核心+所有侧面)
            x_person (int, optional): 人称代词 (0: 无人称, 1: 我, 2: 你). 默认为 2.

        Returns:
            str: 生成的人格prompt字符串
        """
        if x_person not in [0, 1, 2]:
            return "无效的人称代词，请使用 0 (无人称), 1 (我) 或 2 (你)。"
        if not self.personality:
            return "人格特征尚未初始化。"

        if x_person == 2:
            p_pronoun = "你"
            prompt_personality = f"{p_pronoun}{self.personality.personality_core}"
        elif x_person == 1:
            p_pronoun = "我"
            prompt_personality = f"{p_pronoun}{self.personality.personality_core}"
        else:  # x_person == 0
            # 对于无人称，直接描述核心特征
            prompt_personality = f"{self.personality.personality_core}"

        # 根据level添加人格侧面
        if level >= 2 and self.personality.personality_sides:
            personality_sides = list(self.personality.personality_sides)
            random.shuffle(personality_sides)
            if level == 2:
                prompt_personality += f"，有时也会{personality_sides[0]}"
            elif level == 3:
                sides_str = "、".join(personality_sides)
                prompt_personality += f"，有时也会{sides_str}"
        prompt_personality += "。"
        return prompt_personality

    def get_identity_prompt(self, level: int, x_person: int = 2) -> str:
        """
        获取身份特征的prompt

        Args:
            level (int): 详细程度 (1: 随机细节, 2: 所有细节, 3: 同2)
            x_person (int, optional): 人称代词 (0: 无人称, 1: 我, 2: 你). 默认为 2.

        Returns:
            str: 生成的身份prompt字符串
        """
        if x_person not in [0, 1, 2]:
            return "无效的人称代词，请使用 0 (无人称), 1 (我) 或 2 (你)。"
        if not self.identity:
            return "身份特征尚未初始化。"

        if x_person == 2:
            i_pronoun = "你"
        elif x_person == 1:
            i_pronoun = "我"
        else:  # x_person == 0
            i_pronoun = ""  # 无人称

        identity_parts = []

        # 根据level添加身份细节
        if level >= 1 and self.identity.identity_detail:
            identity_detail = list(self.identity.identity_detail)
            random.shuffle(identity_detail)
            if level == 1:
                identity_parts.append(f"{identity_detail[0]}")
            elif level >= 2:
                details_str = "、".join(identity_detail)
                identity_parts.append(f"{details_str}")

        if identity_parts:
            details_str = "，".join(identity_parts)
            if x_person in [1, 2]:
                return f"{i_pronoun}，{details_str}。"
            else:  # x_person == 0
                # 无人称时，直接返回细节，不加代词和开头的逗号
                return f"{details_str}。"
        else:
            if x_person in [1, 2]:
                return f"{i_pronoun}的身份信息不完整。"
            else:  # x_person == 0
                return "身份信息不完整。"

    def get_prompt(self, level: int, x_person: int = 2) -> str:
        """
        获取合并的个体特征prompt

        Args:
            level (int): 详细程度 (1: 核心/随机细节, 2: 核心+随机侧面/全部细节, 3: 全部)
            x_person (int, optional): 人称代词 (0: 无人称, 1: 我, 2: 你). 默认为 2.

        Returns:
            str: 生成的合并prompt字符串
        """
        if x_person not in [0, 1, 2]:
            return "无效的人称代词，请使用 0 (无人称), 1 (我) 或 2 (你)。"

        if not self.personality or not self.identity:
            return "个体特征尚未完全初始化。"

        # 调用新的独立方法
        prompt_personality = self.get_personality_prompt(level, x_person)
        prompt_identity = self.get_identity_prompt(level, x_person)

        # 移除可能存在的错误信息，只合并有效的 prompt
        valid_prompts = []
        if "尚未初始化" not in prompt_personality and "无效的人称" not in prompt_personality:
            valid_prompts.append(prompt_personality)
        if (
            "尚未初始化" not in prompt_identity
            and "无效的人称" not in prompt_identity
            and "信息不完整" not in prompt_identity
        ):
            # 从身份 prompt 中移除代词和句号，以便更好地合并
            identity_content = prompt_identity
            if x_person == 2 and identity_content.startswith("你，"):
                identity_content = identity_content[2:]
            elif x_person == 1 and identity_content.startswith("我，"):
                identity_content = identity_content[2:]
            # 对于 x_person == 0，身份提示不带前缀，无需移除

            if identity_content.endswith("。"):
                identity_content = identity_content[:-1]
            valid_prompts.append(identity_content)

        # --- 合并 Prompt ---
        final_prompt = " ".join(valid_prompts)

        return final_prompt.strip()

    def get_traits(self, factor):
        """
        获取个体特征的特质
        """
        if factor == "openness":
            return self.personality.openness
        elif factor == "conscientiousness":
            return self.personality.conscientiousness
        elif factor == "extraversion":
            return self.personality.extraversion
        elif factor == "agreeableness":
            return self.personality.agreeableness
        elif factor == "neuroticism":
            return self.personality.neuroticism
        return None

    def _get_config_hash(
        self, bot_nickname: str, personality_core: str, personality_sides: list, identity_detail: list
    ) -> str:
        """获取当前personality和identity配置的哈希值"""
        config_data = {
            "nickname": bot_nickname,
            "personality_core": personality_core,
            "personality_sides": sorted(personality_sides),
            "identity_detail": sorted(identity_detail),
        }
        config_str = json.dumps(config_data, sort_keys=True)
        return hashlib.md5(config_str.encode("utf-8")).hexdigest()

    async def _check_config_and_clear_if_changed(
        self, bot_nickname: str, personality_core: str, personality_sides: list, identity_detail: list
    ):
        """检查配置是否发生变化，如果变化则清空info_list"""
        person_info_manager = get_person_info_manager()
        current_hash = self._get_config_hash(bot_nickname, personality_core, personality_sides, identity_detail)

        meta_info = self._load_meta_info()
        stored_hash = meta_info.get("config_hash")

        if current_hash != stored_hash:
            logger.info("检测到人格配置发生变化，将清空原有的关键词缓存。")

            # 清空数据库中的info_list
            update_data = {
                "platform": "system",
                "user_id": "bot_id",
                "person_name": self.name,
                "nickname": self.name,
            }
            await person_info_manager.update_one_field(self.bot_person_id, "info_list", [], data=update_data)

            # 更新元信息文件，重置计数器
            new_meta_info = {"config_hash": current_hash}
            self._save_meta_info(new_meta_info)

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

    async def get_keyword_info(self, keyword: str) -> str:
        """获取指定关键词的信息

        Args:
            keyword: 关键词

        Returns:
            str: 随机选择的一条信息，如果没有则返回空字符串
        """
        person_info_manager = get_person_info_manager()
        info_list_json = await person_info_manager.get_value(self.bot_person_id, "info_list")
        if info_list_json:
            try:
                # get_value might return a pre-deserialized list if it comes from a cache,
                # or a JSON string if it comes from DB.
                info_list = json.loads(info_list_json) if isinstance(info_list_json, str) else info_list_json

                for item in info_list:
                    if isinstance(item, dict) and item.get("info_type") == keyword:
                        return item.get("info_content", "")
            except (json.JSONDecodeError, TypeError):
                logger.error(f"解析info_list失败: {info_list_json}")
                return ""
        return ""

    async def get_all_keywords(self) -> list:
        """获取所有已缓存的关键词列表"""
        person_info_manager = get_person_info_manager()
        info_list_json = await person_info_manager.get_value(self.bot_person_id, "info_list")
        keywords = []
        if info_list_json:
            try:
                info_list = json.loads(info_list_json) if isinstance(info_list_json, str) else info_list_json
                for item in info_list:
                    if isinstance(item, dict) and "info_type" in item:
                        keywords.append(item["info_type"])
            except (json.JSONDecodeError, TypeError):
                logger.error(f"解析info_list失败: {info_list_json}")
        return keywords


individuality = None


def get_individuality():
    global individuality
    if individuality is None:
        individuality = Individuality()
    return individuality
