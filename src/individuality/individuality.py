from typing import Optional
from .personality import Personality
from .identity import Identity
from .expression_style import PersonalityExpression
import random
import json
import os
import hashlib
import traceback
from rich.traceback import install
from json_repair import repair_json
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.manager.async_task_manager import AsyncTask
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
from src.common.logger import get_logger

install(extra_lines=3)

logger = get_logger("individuality")


def init_prompt():
    """初始化用于关键词提取的prompts"""

    extract_keywords_prompt = """
请分析以下对{bot_name}的描述，提取出其中的独立关键词。每个关键词应该是可以用来从某一角度概括的方面，例如：
性格，身高，喜好，外貌，身份，兴趣，爱好，习惯，等等..........

描述内容：
{personality_sides}

要求：
1. 选择关键词，对{bot_name}的某一方面进行概括
2. 用json格式输出，以下是示例格式：
{{
    "性格":"性格开朗",
    "兴趣":"喜欢唱歌",
    "身份":"大学生",
}}
以上是一个例子，你可以输出多个关键词，现在请你根据描述内容进行总结{bot_name}，输出json格式：

请输出json格式，不要输出任何解释或其他内容
"""
    Prompt(extract_keywords_prompt, "extract_keywords_prompt")


class Individuality:
    """个体特征管理类"""

    def __init__(self):
        # 正常初始化实例属性
        self.personality: Optional[Personality] = None
        self.identity: Optional[Identity] = None
        self.express_style: PersonalityExpression = PersonalityExpression()

        self.name = ""

        # 关键词缓存相关
        self.keyword_info_cache: dict = {}  # {keyword: [info_list]}
        self.fetch_info_file_path = "data/personality/fetch_info.json"
        self.meta_info_file_path = "data/personality/meta_info.json"

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
        # 初始化人格
        self.personality = Personality.initialize(
            bot_nickname=bot_nickname, personality_core=personality_core, personality_sides=personality_sides
        )

        # 初始化身份
        self.identity = Identity(identity_detail=identity_detail)

        await self.express_style.extract_and_store_personality_expressions()

        self.name = bot_nickname

        # 预处理关键词和生成信息缓存
        await self._preprocess_personality_keywords(personality_sides, identity_detail)

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

    def _get_config_hash(self, personality_sides: list, identity_detail: list) -> str:
        """获取当前personality和identity配置的哈希值"""
        # 将配置转换为字符串并排序，确保一致性
        config_str = json.dumps(
            {"personality_sides": sorted(personality_sides), "identity_detail": sorted(identity_detail)}, sort_keys=True
        )

        return hashlib.md5(config_str.encode("utf-8")).hexdigest()

    def _load_meta_info(self) -> dict:
        """从JSON文件中加载元信息"""
        if os.path.exists(self.meta_info_file_path):
            try:
                with open(self.meta_info_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取meta_info文件失败: {e}")
                return {}
        return {}

    def _save_meta_info(self, meta_info: dict):
        """将元信息保存到JSON文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.meta_info_file_path), exist_ok=True)
            with open(self.meta_info_file_path, "w", encoding="utf-8") as f:
                json.dump(meta_info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存meta_info文件失败: {e}")

    def _check_config_change_and_clear(self, personality_sides: list, identity_detail: list):
        """检查配置是否发生变化，如果变化则清空fetch_info.json"""
        current_config_hash = self._get_config_hash(personality_sides, identity_detail)
        meta_info = self._load_meta_info()

        stored_config_hash = meta_info.get("config_hash", "")

        if current_config_hash != stored_config_hash:
            logger.info("检测到personality或identity配置发生变化，清空fetch_info数据")

            # 清空fetch_info文件
            if os.path.exists(self.fetch_info_file_path):
                try:
                    os.remove(self.fetch_info_file_path)
                    logger.info("已清空fetch_info文件")
                except Exception as e:
                    logger.error(f"清空fetch_info文件失败: {e}")

            # 更新元信息
            meta_info["config_hash"] = current_config_hash
            self._save_meta_info(meta_info)
            logger.info("已更新配置哈希值")

    def _load_fetch_info_from_file(self) -> dict:
        """从JSON文件中加载已保存的fetch_info数据"""
        if os.path.exists(self.fetch_info_file_path):
            try:
                with open(self.fetch_info_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取fetch_info文件失败: {e}")
                return {}
        return {}

    def _save_fetch_info_to_file(self, fetch_info_data: dict):
        """将fetch_info数据保存到JSON文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.fetch_info_file_path), exist_ok=True)
            with open(self.fetch_info_file_path, "w", encoding="utf-8") as f:
                json.dump(fetch_info_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存fetch_info文件失败: {e}")

    async def _preprocess_personality_keywords(self, personality_sides: list, identity_detail: list):
        """预处理personality关键词，提取关键词并生成缓存"""
        try:
            logger.info("开始预处理personality关键词...")

            # 检查配置变化
            self._check_config_change_and_clear(personality_sides, identity_detail)

            # 加载已有的预处理数据（如果存在）
            fetch_info_data = self._load_fetch_info_from_file()
            logger.info(f"加载已有数据，现有关键词数量: {len(fetch_info_data)}")

            # 构建完整描述（personality + identity）
            personality_sides_str = ""
            for personality_side in personality_sides:
                personality_sides_str += f"{personality_side}，"

            # 添加identity内容
            for detail in identity_detail:
                personality_sides_str += f"{detail}，"

            if not personality_sides_str:
                logger.info("没有personality和identity配置，跳过预处理")
                return

            # 提取关键词
            extract_prompt = (await global_prompt_manager.get_prompt_async("extract_keywords_prompt")).format(
                personality_sides=personality_sides_str, bot_name=self.name
            )

            llm_model = LLMRequest(
                model=global_config.model.utils_small,
                request_type="individuality.keyword_extract",
            )

            keywords_result, _ = await llm_model.generate_response_async(prompt=extract_prompt)
            logger.info(f"LLM返回的原始关键词结果: '{keywords_result}'")

            if not keywords_result or keywords_result.strip() == "none":
                logger.info("未提取到有效关键词")
                return

            # 使用json_repair修复并解析JSON
            keyword_dict = json.loads(repair_json(keywords_result))
            logger.info(f"成功解析JSON格式的关键词: {keyword_dict}")

            # 从字典中提取关键词列表，跳过"keywords"键
            keyword_set = []
            for key, _value in keyword_dict.items():
                if key.lower() != "keywords" and key.strip():
                    keyword_set.append(key.strip())

            logger.info(f"最终提取的关键词列表: {keyword_set}")
            logger.info(f"共提取到 {len(keyword_set)} 个关键词")

            # 处理每个关键词的信息
            updated_count = 0
            new_count = 0

            for keyword in keyword_set:
                try:
                    logger.info(f"正在处理关键词: '{keyword}' (长度: {len(keyword)})")

                    # 检查是否已存在该关键词
                    if keyword in fetch_info_data:
                        logger.info(f"关键词 '{keyword}' 已存在，将添加新信息...")
                        action_type = "追加"
                    else:
                        logger.info(f"正在为新关键词 '{keyword}' 生成信息...")
                        action_type = "新增"
                        fetch_info_data[keyword] = []  # 初始化为空列表

                    # 从JSON结果中获取关键词的信息
                    existing_info_from_json = keyword_dict.get(keyword, "")
                    if (
                        existing_info_from_json
                        and existing_info_from_json.strip()
                        and existing_info_from_json != keyword
                    ):
                        # 如果JSON中有有效信息且不只是重复关键词本身，直接使用
                        logger.info(f"从JSON结果中获取到关键词 '{keyword}' 的信息: '{existing_info_from_json}'")
                        if existing_info_from_json not in fetch_info_data[keyword]:
                            fetch_info_data[keyword].append(existing_info_from_json)
                            if action_type == "追加":
                                updated_count += 1
                            else:
                                new_count += 1
                            logger.info(f"{action_type}关键词 '{keyword}' 的信息成功")
                        else:
                            logger.info(f"关键词 '{keyword}' 的信息已存在，跳过重复添加")
                    else:
                        logger.info(f"关键词 '{keyword}' 在JSON中没有有效信息，跳过")

                except Exception as e:
                    logger.error(f"为关键词 '{keyword}' 生成信息时出错: {e}")
                    continue

            # 保存合并后的数据到文件和内存缓存
            if updated_count > 0 or new_count > 0:
                self._save_fetch_info_to_file(fetch_info_data)
                logger.info(
                    f"预处理完成，新增 {new_count} 个关键词，追加 {updated_count} 个关键词信息，总计 {len(fetch_info_data)} 个关键词"
                )
            else:
                logger.info("预处理完成，但没有生成任何新的有效信息")

            # 将数据加载到内存缓存
            self.keyword_info_cache = fetch_info_data
            logger.info(f"关键词缓存已加载，共 {len(self.keyword_info_cache)} 个关键词")

            # 注册定时任务（延迟执行，避免阻塞初始化）
            import asyncio

            asyncio.create_task(self._register_keyword_update_task_delayed())

        except Exception as e:
            logger.error(f"预处理personality关键词时出错: {e}")
            traceback.print_exc()

    async def _register_keyword_update_task_delayed(self):
        """延迟注册关键词更新定时任务"""
        try:
            # 等待一小段时间确保系统完全初始化
            import asyncio

            await asyncio.sleep(5)

            from src.manager.async_task_manager import async_task_manager

            logger = get_logger("individuality")

            # 创建定时任务
            task = KeywordUpdateTask(
                personality_sides=list(global_config.personality.personality_sides),
                identity_detail=list(global_config.identity.identity_detail),
                individuality_instance=self,
            )

            # 注册任务
            await async_task_manager.add_task(task)
            logger.info("关键词更新定时任务已注册")

        except Exception as e:
            logger.error(f"注册关键词更新定时任务失败: {e}")
            traceback.print_exc()

    def get_keyword_info(self, keyword: str) -> str:
        """获取指定关键词的信息

        Args:
            keyword: 关键词

        Returns:
            str: 随机选择的一条信息，如果没有则返回空字符串
        """
        if keyword in self.keyword_info_cache and self.keyword_info_cache[keyword]:
            return random.choice(self.keyword_info_cache[keyword])
        return ""

    def get_all_keywords(self) -> list:
        """获取所有已缓存的关键词列表"""
        return list(self.keyword_info_cache.keys())


individuality = None


def get_individuality():
    global individuality
    if individuality is None:
        individuality = Individuality()
    return individuality


class KeywordUpdateTask(AsyncTask):
    """关键词更新定时任务"""

    def __init__(self, personality_sides: list, identity_detail: list, individuality_instance):
        # 调用父类构造函数
        super().__init__(
            task_name="keyword_update_task",
            wait_before_start=3600,  # 1小时后开始
            run_interval=3600,  # 每小时运行一次
        )

        self.personality_sides = personality_sides
        self.identity_detail = identity_detail
        self.individuality_instance = individuality_instance

        # 任务控制参数
        self.max_runs = 20
        self.current_runs = 0
        self.original_config_hash = individuality_instance._get_config_hash(personality_sides, identity_detail)

    async def run(self):
        """执行任务"""
        try:
            from src.common.logger import get_logger

            logger = get_logger("individuality.task")

            # 检查是否超过最大运行次数
            if self.current_runs >= self.max_runs:
                logger.info(f"关键词更新任务已达到最大运行次数({self.max_runs})，停止执行")
                # 设置为0间隔来停止循环任务
                self.run_interval = 0
                return

            # 检查配置是否发生变化
            current_config_hash = self.individuality_instance._get_config_hash(
                self.personality_sides, self.identity_detail
            )
            if current_config_hash != self.original_config_hash:
                logger.info("检测到personality或identity配置发生变化，停止定时任务")
                # 设置为0间隔来停止循环任务
                self.run_interval = 0
                return

            self.current_runs += 1
            logger.info(f"开始执行关键词更新任务 (第{self.current_runs}/{self.max_runs}次)")

            # 执行关键词预处理
            await self.individuality_instance._preprocess_personality_keywords(
                self.personality_sides, self.identity_detail
            )

            logger.info(f"关键词更新任务完成 (第{self.current_runs}/{self.max_runs}次)")

        except Exception as e:
            logger.error(f"关键词更新任务执行失败: {e}")
            traceback.print_exc()


# 初始化prompt模板
init_prompt()
