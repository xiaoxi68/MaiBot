import asyncio
import json
import time

from src.chat.message_receive.message import MessageRecv
from src.llm_models.utils_model import LLMRequest
from src.common.logger import get_logger
from src.chat.utils.chat_message_builder import build_readable_messages, get_raw_msg_by_timestamp_with_chat_inclusive
from src.config.config import global_config
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.manager.async_task_manager import AsyncTask, async_task_manager
from src.plugin_system.apis import send_api

logger = get_logger("mood")


async def send_joy_action(chat_id: str):
    action_content = {"action": "Joy_eye", "data": 1.0}
    await send_api.custom_to_stream(message_type="face_emotion", content=action_content, stream_id=chat_id)
    logger.info(f"[{chat_id}] 已发送 Joy 动作: {action_content}")

    await asyncio.sleep(5.0)

    end_action_content = {"action": "Joy_eye", "data": 0.0}
    await send_api.custom_to_stream(message_type="face_emotion", content=end_action_content, stream_id=chat_id)
    logger.info(f"[{chat_id}] 已发送 Joy 结束动作: {end_action_content}")


def init_prompt():
    Prompt(
        """
{chat_talking_prompt}
以上是直播间里正在进行的对话

{indentify_block}
你刚刚的情绪状态是：{mood_state}

现在，发送了消息，引起了你的注意，你对其进行了阅读和思考，请你输出一句话描述你新的情绪状态，不要输出任何其他内容
请只输出情绪状态，不要输出其他内容：
""",
        "change_mood_prompt_vtb",
    )
    Prompt(
        """
{chat_talking_prompt}
以上是直播间里最近的对话

{indentify_block}
你之前的情绪状态是：{mood_state}

距离你上次关注直播间消息已经过去了一段时间，你冷静了下来，请你输出一句话描述你现在的情绪状态
请只输出情绪状态，不要输出其他内容：
""",
        "regress_mood_prompt_vtb",
    )
    Prompt(
        """
{chat_talking_prompt}
以上是直播间里正在进行的对话

{indentify_block}
你刚刚的情绪状态是：{mood_state}
具体来说，从1-10分，你的情绪状态是：
喜(Joy): {joy}
怒(Anger): {anger}
哀(Sorrow): {sorrow}
乐(Pleasure): {pleasure}
惧(Fear): {fear}

现在，发送了消息，引起了你的注意，你对其进行了阅读和思考。请基于对话内容，评估你新的情绪状态。
请以JSON格式输出你新的情绪状态，包含“喜怒哀乐惧”五个维度，每个维度的取值范围为1-10。
键值请使用英文: "joy", "anger", "sorrow", "pleasure", "fear".
例如: {{"joy": 5, "anger": 1, "sorrow": 1, "pleasure": 5, "fear": 1}}
不要输出任何其他内容，只输出JSON。
""",
        "change_mood_numerical_prompt",
    )
    Prompt(
        """
{chat_talking_prompt}
以上是直播间里最近的对话

{indentify_block}
你之前的情绪状态是：{mood_state}
具体来说，从1-10分，你的情绪状态是：
喜(Joy): {joy}
怒(Anger): {anger}
哀(Sorrow): {sorrow}
乐(Pleasure): {pleasure}
惧(Fear): {fear}

距离你上次关注直播间消息已经过去了一段时间，你冷静了下来。请基于此，评估你现在的情绪状态。
请以JSON格式输出你新的情绪状态，包含“喜怒哀乐惧”五个维度，每个维度的取值范围为1-10。
键值请使用英文: "joy", "anger", "sorrow", "pleasure", "fear".
例如: {{"joy": 5, "anger": 1, "sorrow": 1, "pleasure": 5, "fear": 1}}
不要输出任何其他内容，只输出JSON。
""",
        "regress_mood_numerical_prompt",
    )


class ChatMood:
    def __init__(self, chat_id: str):
        self.chat_id: str = chat_id
        self.mood_state: str = "感觉很平静"
        self.mood_values: dict[str, int] = {"joy": 5, "anger": 1, "sorrow": 1, "pleasure": 5, "fear": 1}

        self.regression_count: int = 0

        self.mood_model = LLMRequest(
            model=global_config.model.emotion,
            temperature=0.7,
            request_type="mood_text",
        )
        self.mood_model_numerical = LLMRequest(
            model=global_config.model.emotion,
            temperature=0.4,
            request_type="mood_numerical",
        )

        self.last_change_time = 0

    def _parse_numerical_mood(self, response: str) -> dict[str, int] | None:
        try:
            # The LLM might output markdown with json inside
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            data = json.loads(response)

            # Validate
            required_keys = {"joy", "anger", "sorrow", "pleasure", "fear"}
            if not required_keys.issubset(data.keys()):
                logger.warning(f"Numerical mood response missing keys: {response}")
                return None

            for key in required_keys:
                value = data[key]
                if not isinstance(value, int) or not (1 <= value <= 10):
                    logger.warning(f"Numerical mood response invalid value for {key}: {value} in {response}")
                    return None

            return {key: data[key] for key in required_keys}

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse numerical mood JSON: {response}")
            return None
        except Exception as e:
            logger.error(f"Error parsing numerical mood: {e}, response: {response}")
            return None

    async def update_mood_by_message(self, message: MessageRecv):
        self.regression_count = 0

        message_time = message.message_info.time
        message_list_before_now = get_raw_msg_by_timestamp_with_chat_inclusive(
            chat_id=self.chat_id,
            timestamp_start=self.last_change_time,
            timestamp_end=message_time,
            limit=15,
            limit_mode="last",
        )
        chat_talking_prompt = build_readable_messages(
            message_list_before_now,
            replace_bot_name=True,
            merge_messages=False,
            timestamp_mode="normal_no_YMD",
            read_mark=0.0,
            truncate=True,
            show_actions=True,
        )

        bot_name = global_config.bot.nickname
        if global_config.bot.alias_names:
            bot_nickname = f",也有人叫你{','.join(global_config.bot.alias_names)}"
        else:
            bot_nickname = ""

        prompt_personality = global_config.personality.personality_core
        indentify_block = f"你的名字是{bot_name}{bot_nickname}，你{prompt_personality}："

        async def _update_text_mood():
            prompt = await global_prompt_manager.format_prompt(
                "change_mood_prompt_vtb",
                chat_talking_prompt=chat_talking_prompt,
                indentify_block=indentify_block,
                mood_state=self.mood_state,
            )
            logger.debug(f"text mood prompt: {prompt}")
            response, (reasoning_content, model_name) = await self.mood_model.generate_response_async(prompt=prompt)
            logger.info(f"text mood response: {response}")
            logger.debug(f"text mood reasoning_content: {reasoning_content}")
            return response

        async def _update_numerical_mood():
            prompt = await global_prompt_manager.format_prompt(
                "change_mood_numerical_prompt",
                chat_talking_prompt=chat_talking_prompt,
                indentify_block=indentify_block,
                mood_state=self.mood_state,
                joy=self.mood_values["joy"],
                anger=self.mood_values["anger"],
                sorrow=self.mood_values["sorrow"],
                pleasure=self.mood_values["pleasure"],
                fear=self.mood_values["fear"],
            )
            logger.info(f"numerical mood prompt: {prompt}")
            response, (reasoning_content, model_name) = await self.mood_model_numerical.generate_response_async(
                prompt=prompt
            )
            logger.info(f"numerical mood response: {response}")
            logger.debug(f"numerical mood reasoning_content: {reasoning_content}")
            return self._parse_numerical_mood(response)

        results = await asyncio.gather(_update_text_mood(), _update_numerical_mood())
        text_mood_response, numerical_mood_response = results

        if text_mood_response:
            self.mood_state = text_mood_response

        if numerical_mood_response:
            self.mood_values = numerical_mood_response
            if self.mood_values.get("joy", 0) > 5:
                asyncio.create_task(send_joy_action(self.chat_id))

        self.last_change_time = message_time

    async def regress_mood(self):
        message_time = time.time()
        message_list_before_now = get_raw_msg_by_timestamp_with_chat_inclusive(
            chat_id=self.chat_id,
            timestamp_start=self.last_change_time,
            timestamp_end=message_time,
            limit=15,
            limit_mode="last",
        )
        chat_talking_prompt = build_readable_messages(
            message_list_before_now,
            replace_bot_name=True,
            merge_messages=False,
            timestamp_mode="normal_no_YMD",
            read_mark=0.0,
            truncate=True,
            show_actions=True,
        )

        bot_name = global_config.bot.nickname
        if global_config.bot.alias_names:
            bot_nickname = f",也有人叫你{','.join(global_config.bot.alias_names)}"
        else:
            bot_nickname = ""

        prompt_personality = global_config.personality.personality_core
        indentify_block = f"你的名字是{bot_name}{bot_nickname}，你{prompt_personality}："

        async def _regress_text_mood():
            prompt = await global_prompt_manager.format_prompt(
                "regress_mood_prompt_vtb",
                chat_talking_prompt=chat_talking_prompt,
                indentify_block=indentify_block,
                mood_state=self.mood_state,
            )
            logger.debug(f"text regress prompt: {prompt}")
            response, (reasoning_content, model_name) = await self.mood_model.generate_response_async(prompt=prompt)
            logger.info(f"text regress response: {response}")
            logger.debug(f"text regress reasoning_content: {reasoning_content}")
            return response

        async def _regress_numerical_mood():
            prompt = await global_prompt_manager.format_prompt(
                "regress_mood_numerical_prompt",
                chat_talking_prompt=chat_talking_prompt,
                indentify_block=indentify_block,
                mood_state=self.mood_state,
                joy=self.mood_values["joy"],
                anger=self.mood_values["anger"],
                sorrow=self.mood_values["sorrow"],
                pleasure=self.mood_values["pleasure"],
                fear=self.mood_values["fear"],
            )
            logger.debug(f"numerical regress prompt: {prompt}")
            response, (reasoning_content, model_name) = await self.mood_model_numerical.generate_response_async(
                prompt=prompt
            )
            logger.info(f"numerical regress response: {response}")
            logger.debug(f"numerical regress reasoning_content: {reasoning_content}")
            return self._parse_numerical_mood(response)

        results = await asyncio.gather(_regress_text_mood(), _regress_numerical_mood())
        text_mood_response, numerical_mood_response = results

        if text_mood_response:
            self.mood_state = text_mood_response

        if numerical_mood_response:
            self.mood_values = numerical_mood_response
            if self.mood_values.get("joy", 0) > 5:
                asyncio.create_task(send_joy_action(self.chat_id))

        self.regression_count += 1


class MoodRegressionTask(AsyncTask):
    def __init__(self, mood_manager: "MoodManager"):
        super().__init__(task_name="MoodRegressionTask", run_interval=30)
        self.mood_manager = mood_manager

    async def run(self):
        logger.debug("Running mood regression task...")
        now = time.time()
        for mood in self.mood_manager.mood_list:
            if mood.last_change_time == 0:
                continue

            if now - mood.last_change_time > 180:
                if mood.regression_count >= 3:
                    continue

                logger.info(f"chat {mood.chat_id} 开始情绪回归, 这是第 {mood.regression_count + 1} 次")
                await mood.regress_mood()


class MoodManager:
    def __init__(self):
        self.mood_list: list[ChatMood] = []
        """当前情绪状态"""
        self.task_started: bool = False

    async def start(self):
        """启动情绪回归后台任务"""
        if self.task_started:
            return

        logger.info("启动情绪回归任务...")
        task = MoodRegressionTask(self)
        await async_task_manager.add_task(task)
        self.task_started = True
        logger.info("情绪回归任务已启动")

    def get_mood_by_chat_id(self, chat_id: str) -> ChatMood:
        for mood in self.mood_list:
            if mood.chat_id == chat_id:
                return mood

        new_mood = ChatMood(chat_id)
        self.mood_list.append(new_mood)
        return new_mood

    def reset_mood_by_chat_id(self, chat_id: str):
        for mood in self.mood_list:
            if mood.chat_id == chat_id:
                mood.mood_state = "感觉很平静"
                mood.regression_count = 0
                return
        self.mood_list.append(ChatMood(chat_id))


init_prompt()

mood_manager = MoodManager()
"""全局情绪管理器"""
