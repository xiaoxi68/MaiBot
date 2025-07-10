import json
import time

from src.chat.message_receive.message import MessageRecv
from src.llm_models.utils_model import LLMRequest
from src.common.logger import get_logger
from src.chat.utils.chat_message_builder import build_readable_messages, get_raw_msg_by_timestamp_with_chat_inclusive
from src.config.config import global_config
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.manager.async_task_manager import AsyncTask, async_task_manager
from json_repair import repair_json

logger = get_logger("action")


def init_prompt():
    Prompt(
        """
{chat_talking_prompt}
以上是群里正在进行的聊天记录

{indentify_block}
你现在的动作状态是：
- 手部：{hand_action}
- 上半身：{upper_body_action}
- 头部：{head_action}

现在，因为你发送了消息，或者群里其他人发送了消息，引起了你的注意，你对其进行了阅读和思考，请你更新你的动作状态。
请只按照以下json格式输出，描述你新的动作状态，每个动作一到三个中文词，确保每个字段都存在：
{{
  "hand_action": "...",
  "upper_body_action": "...",
  "head_action": "..."
}}
""",
        "change_action_prompt",
    )
    Prompt(
        """
{chat_talking_prompt}
以上是群里最近的聊天记录

{indentify_block}
你之前的动作状态是：
- 手部：{hand_action}
- 上半身：{upper_body_action}
- 头部：{head_action}

距离你上次关注群里消息已经过去了一段时间，你冷静了下来，你的动作会趋于平缓或静止，请你输出你现在新的动作状态，用中文。
请只按照以下json格式输出，描述你新的动作状态，每个动作一到三个词，确保每个字段都存在：
{{
  "hand_action": "...",
  "upper_body_action": "...",
  "head_action": "..."
}}
""",
        "regress_action_prompt",
    )


class ChatAction:
    def __init__(self, chat_id: str):
        self.chat_id: str = chat_id
        self.hand_action: str = "双手放在桌面"
        self.upper_body_action: str = "坐着"
        self.head_action: str = "注视摄像机"

        self.regression_count: int = 0

        self.action_model = LLMRequest(
            model=global_config.model.emotion,
            temperature=0.7,
            request_type="action",
        )

        self.last_change_time = 0

    async def update_action_by_message(self, message: MessageRecv):
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

        prompt = await global_prompt_manager.format_prompt(
            "change_action_prompt",
            chat_talking_prompt=chat_talking_prompt,
            indentify_block=indentify_block,
            hand_action=self.hand_action,
            upper_body_action=self.upper_body_action,
            head_action=self.head_action,
        )

        logger.info(f"prompt: {prompt}")
        response, (reasoning_content, model_name) = await self.action_model.generate_response_async(prompt=prompt)
        logger.info(f"response: {response}")
        logger.info(f"reasoning_content: {reasoning_content}")

        action_data = json.loads(repair_json(response))

        if action_data:
            self.hand_action = action_data.get("hand_action", self.hand_action)
            self.upper_body_action = action_data.get("upper_body_action", self.upper_body_action)
            self.head_action = action_data.get("head_action", self.head_action)

        self.last_change_time = message_time

    async def regress_action(self):
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

        prompt = await global_prompt_manager.format_prompt(
            "regress_action_prompt",
            chat_talking_prompt=chat_talking_prompt,
            indentify_block=indentify_block,
            hand_action=self.hand_action,
            upper_body_action=self.upper_body_action,
            head_action=self.head_action,
        )

        logger.info(f"prompt: {prompt}")
        response, (reasoning_content, model_name) = await self.action_model.generate_response_async(prompt=prompt)
        logger.info(f"response: {response}")
        logger.info(f"reasoning_content: {reasoning_content}")

        action_data = json.loads(repair_json(response))
        if action_data:
            self.hand_action = action_data.get("hand_action", self.hand_action)
            self.upper_body_action = action_data.get("upper_body_action", self.upper_body_action)
            self.head_action = action_data.get("head_action", self.head_action)

        self.regression_count += 1


class ActionRegressionTask(AsyncTask):
    def __init__(self, action_manager: "ActionManager"):
        super().__init__(task_name="ActionRegressionTask", run_interval=30)
        self.action_manager = action_manager

    async def run(self):
        logger.debug("Running action regression task...")
        now = time.time()
        for action_state in self.action_manager.action_state_list:
            if action_state.last_change_time == 0:
                continue

            if now - action_state.last_change_time > 180:
                if action_state.regression_count >= 3:
                    continue

                logger.info(f"chat {action_state.chat_id} 开始动作回归, 这是第 {action_state.regression_count + 1} 次")
                await action_state.regress_action()


class ActionManager:
    def __init__(self):
        self.action_state_list: list[ChatAction] = []
        """当前动作状态"""
        self.task_started: bool = False

    async def start(self):
        """启动动作回归后台任务"""
        if self.task_started:
            return

        logger.info("启动动作回归任务...")
        task = ActionRegressionTask(self)
        await async_task_manager.add_task(task)
        self.task_started = True
        logger.info("动作回归任务已启动")

    def get_action_state_by_chat_id(self, chat_id: str) -> ChatAction:
        for action_state in self.action_state_list:
            if action_state.chat_id == chat_id:
                return action_state

        new_action_state = ChatAction(chat_id)
        self.action_state_list.append(new_action_state)
        return new_action_state

    def reset_action_state_by_chat_id(self, chat_id: str):
        for action_state in self.action_state_list:
            if action_state.chat_id == chat_id:
                action_state.hand_action = "双手放在桌面"
                action_state.upper_body_action = "坐着"
                action_state.head_action = "注视摄像机"
                action_state.regression_count = 0
                return
        self.action_state_list.append(ChatAction(chat_id))


init_prompt()

action_manager = ActionManager()
"""全局动作管理器"""
