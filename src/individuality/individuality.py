import json
from typing import Optional

from numpy import double

from common.logger_manager import get_logger
from config.config import global_config
from manager.model_manager import global_model_manager
from manager.local_store_manager import local_storage

from maibot_api_adapter.payload_content.message import MessageBuilder
from maibot_api_adapter.payload_content.resp_format import RespFormat, RespFormatType
from rich.traceback import install

install(extra_lines=3)

logger = get_logger("individuality")


class Individuality:
    """个体特征管理类"""

    def __init__(self):
        self.personality_core: str = ""
        self.personality_detail: str = ""
        self.appearance_overview: str = ""
        self.appearance_detail: str = ""

        # self._character_gen = global_model_manager["character_gen"]
        # """个体特征生成模型"""

    async def init(self):
        await self._load_character()

    async def _gen_personality(self):
        prompt = (
            MessageBuilder()
            .add_text_content(f"""
请你根据提供的描述文本完成以下任务：
    1. 以"一个"开头，在一句话内概括"{global_config.bot.nickname}"的核心人格。
    2. 以"有时会"开头，对"{global_config.bot.nickname}"进行分条的人格侧写。如果除了核心人格无法分析出其它人格侧写，你可以根据核心人格生成几条可能的人格侧写。
请将你的回答以Json格式返回。

描述文本：
{global_config.character.personality}
""")
            .build()
        )

        resp_format = RespFormat(
            RespFormatType.JSON_SCHEMA,
            {
                "name": "character_personality",
                "schema": {
                    "type": "object",
                    "properties": {
                        "personality_core": {"type": "string", "description": "人格核心特点"},
                        "personality_sides": {"type": "string", "description": "详细的人格描述"},
                    },
                    "required": ["personality_core", "personality_sides"],
                },
            },
        )

        try:
            response = await global_model_manager["character_gen"].get_response(
                messages=[prompt],
                response_format=resp_format,
            )

            character_data = json.loads(response.content)
            self.personality_core = character_data.get("personality_core", "")
            if self.personality_core.endswith("。"):
                # 如果核心人格以句号结尾，则去掉句号
                self.personality_core = self.personality_core[:-1]
            self.personality_sides = character_data.get("personality_sides", "")
        except json.JSONDecodeError as e:
            logger.error(f"解析个体特征JSON失败: {e}")
            return  # TODO: 处理退出程序
        except RuntimeError as e:
            logger.error(f"生成个体特征时发生错误: {e}")
            return  # TODO: 处理退出程序

    async def _gen_appearance(self):
        prompt = (
            MessageBuilder()
            .add_text_content(f"""
请你根据提供的描述文本完成以下任务：
    1. 在一句话内概括"{global_config.bot.nickname}"的外貌特征。
    2. 对"{global_config.bot.nickname}"的外貌进行分条的详细描述。如果提供的描述文本不足以进行细节描写，你可以自行添加一些细节。
注意：以上内容中不要出现人称或名字。

描述文本：
{global_config.character.appearance}
""")
            .build()
        )

        resp_format = RespFormat(
            RespFormatType.JSON_SCHEMA,
            {
                "name": "character_appearance",
                "schema": {
                    "type": "object",
                    "properties": {
                        "appearance_overview": {"type": "string", "description": "外貌概括"},
                        "appearance_detail": {"type": "string", "description": "详细的外貌描述"},
                    },
                    "required": ["appearance_overview", "appearance_detail"],
                },
            },
        )

        try:
            response = await global_model_manager["character_gen"].get_response(
                messages=[prompt],
                response_format=resp_format,
            )

            character_data = json.loads(response.content)
            self.appearance_overview = character_data.get("appearance_overview", "")
            if self.appearance_overview.endswith("。"):
                # 如果外貌概括以句号结尾，则去掉句号
                self.appearance_overview = self.appearance_overview[:-1]
            self.appearance_detail = character_data.get("appearance_detail", "")
        except json.JSONDecodeError as e:
            logger.error(f"解析外貌特征JSON失败: {e}")
            return  # TODO: 处理退出程序
        except RuntimeError as e:
            logger.error(f"生成外貌特征时发生错误: {e}")
            return  # TODO: 处理退出程序

    async def _load_character(self):
        """加载个体特征"""
        if stored_character := local_storage["character"]:
            self.personality_core = stored_character.get("personality_core", "")
            self.personality_sides = stored_character.get("personality_sides", "")
            self.appearance_overview = stored_character.get("appearance_overview", "")
            self.appearance_detail = stored_character.get("appearance_detail", "")

        if not self.personality_core or not self.personality_sides:
            # 如果没有加载到个体特征，则调用LLM生成
            logger.warning("未检测到人格设定，正在生成...")
            await self._gen_personality()
            if not stored_character["personality_core"] or not stored_character["personality_sides"]:
                raise RuntimeError("人格特征生成失败。")
            logger.info("人格特征生成完成，可在 local_storage['character'] 中查看/修改。")

        if not self.appearance_overview or not self.appearance_detail:
            # 如果没有加载到外貌特征，则调用LLM生成
            logger.warning("未检测到外貌设定，正在生成...")
            await self._gen_appearance()
            if not stored_character["appearance_overview"] or not stored_character["appearance_detail"]:
                raise RuntimeError("外貌特征生成失败。")
            logger.info("人格特征生成完成，可在 local_storage['character'] 中查看/修改。")

        stored_character = {
            "personality_core": self.personality_core,
            "personality_sides": self.personality_sides,
            "appearance_overview": self.appearance_overview,
            "appearance_detail": self.appearance_detail,
            "_comment_": "此处存储生成的个体特征，包括人格核心特点、人格侧面描述、外貌概括和详细外貌描述。你可以在此修改你觉得不满意的描述，修改将在重启后生效。",
        }

        local_storage["character"] = stored_character

    def get_personality_prompt(self, x_person: int = 2, detail: bool = False) -> str:
        """获取人格描述的提示语

        :param x_person: 人称代词 (0: 无人称, 1: 我, 2: 你)
        :param detail: 是否进行详细描述
        :return: 格式化的人格描述字符串
        """
        if x_person not in [0, 1, 2]:
            raise ValueError("x_person must be 0 (无人称), 1 (我) or 2 (你).")
        if not self.personality_core or not self.personality_sides:
            raise RuntimeError("人格特征尚未初始化，请先调用 init() 方法。")

        if x_person == 2:
            p_word = "你"
        elif x_person == 1:
            p_word = "我"
        else:  # x_person == 0
            # 对于无人称，直接描述核心特征
            p_word = ""

        return (
            f"{p_word}是{self.personality_core}。{p_word}{self.personality_sides}"
            if detail
            else f"{p_word}是{self.personality_core}。"
        )

    def get_appearance_prompt(self, x_person: int = 2, detail: bool = False) -> str:
        """获取外貌描述的提示语

        :param x_person: 人称代词 (0: 无人称, 1: 我, 2: 你)
        :param detail: 是否进行详细描述
        :return: 格式化的外貌描述字符串
        """
        if x_person not in [0, 1, 2]:
            raise ValueError("x_person must be 0 (无人称), 1 (我) or 2 (你).")
        if not self.appearance_overview or not self.appearance_detail:
            raise RuntimeError("外貌特征尚未初始化，请先调用 init() 方法。")

        if x_person == 2:
            p_word = "你"
        elif x_person == 1:
            p_word = "我"
        else:
            # 对于无人称，直接描述核心特征
            p_word = ""

        return (
            f"{p_word}，{self.appearance_overview}。{p_word}{self.appearance_detail}"
            if detail
            else f"{p_word}，{self.appearance_overview}。"
        )


individuality = Individuality()
