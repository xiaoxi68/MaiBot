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

"""
面部表情系统使用说明：

1. 预定义的面部表情：
   - happy: 高兴表情（眼睛微笑 + 眉毛微笑 + 嘴巴大笑）
   - very_happy: 非常高兴（高兴表情 + 脸红）
   - sad: 悲伤表情（眼睛哭泣 + 眉毛忧伤 + 嘴巴悲伤）
   - angry: 生气表情（眉毛生气 + 嘴巴生气）
   - fear: 恐惧表情（眼睛闭上）
   - shy: 害羞表情（嘴巴嘟起 + 脸红）
   - neutral: 中性表情（无表情）

2. 使用方法：
   # 获取面部表情管理器
   facial_expression = mood_manager.get_facial_expression_by_chat_id(chat_id)
   
   # 发送指定表情
   await facial_expression.send_expression("happy")
   
   # 根据情绪值自动选择表情
   await facial_expression.send_expression_by_mood(mood_values)
   
   # 重置为中性表情
   await facial_expression.reset_expression()

3. 自动表情系统：
   - 当情绪值更新时，系统会自动根据mood_values选择合适的面部表情
   - 只有当新表情与当前表情不同时才会发送，避免重复发送
   - 支持joy >= 8时显示very_happy，joy >= 6时显示happy等梯度表情

4. amadus表情更新系统：
   - 每1秒检查一次表情是否有变化，如有变化则发送到amadus
   - 每次mood更新后立即发送表情更新
   - 发送消息类型为"amadus_expression_update"，格式为{"action": "表情名", "data": 1.0}

5. 表情选择逻辑：
   - 系统会找出最强的情绪（joy, anger, sorrow, fear）
   - 根据情绪强度选择相应的表情组合
   - 默认情况下返回neutral表情
"""

logger = get_logger("mood")


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
惧(Fear): {fear}

现在，发送了消息，引起了你的注意，你对其进行了阅读和思考。请基于对话内容，评估你新的情绪状态。
请以JSON格式输出你新的情绪状态，包含"喜怒哀惧"四个维度，每个维度的取值范围为1-10。
键值请使用英文: "joy", "anger", "sorrow", "fear".
例如: {{"joy": 5, "anger": 1, "sorrow": 1, "fear": 1}}
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
惧(Fear): {fear}

距离你上次关注直播间消息已经过去了一段时间，你冷静了下来。请基于此，评估你现在的情绪状态。
请以JSON格式输出你新的情绪状态，包含"喜怒哀惧"四个维度，每个维度的取值范围为1-10。
键值请使用英文: "joy", "anger", "sorrow", "fear".
例如: {{"joy": 5, "anger": 1, "sorrow": 1, "fear": 1}}
不要输出任何其他内容，只输出JSON。
""",
        "regress_mood_numerical_prompt",
    )


class FacialExpression:
    def __init__(self, chat_id: str):
        self.chat_id: str = chat_id
        
        # 预定义面部表情动作
        self.expressions = {
            # 眼睛表情
            "eye_smile": {"action": "eye_smile", "data": 1.0},
            "eye_cry": {"action": "eye_cry", "data": 1.0},
            "eye_close": {"action": "eye_close", "data": 1.0},
            "eye_normal": {"action": "eye_normal", "data": 1.0},
            
            # 眉毛表情
            "eyebrow_smile": {"action": "eyebrow_smile", "data": 1.0},
            "eyebrow_angry": {"action": "eyebrow_angry", "data": 1.0},
            "eyebrow_sad": {"action": "eyebrow_sad", "data": 1.0},
            "eyebrow_normal": {"action": "eyebrow_normal", "data": 1.0},
            
            # 嘴巴表情
            "mouth_sad": {"action": "mouth_sad", "data": 1.0},
            "mouth_angry": {"action": "mouth_angry", "data": 1.0},
            "mouth_laugh": {"action": "mouth_laugh", "data": 1.0},
            "mouth_pout": {"action": "mouth_pout", "data": 1.0},
            "mouth_normal": {"action": "mouth_normal", "data": 1.0},
            
            # 脸部表情
            "face_blush": {"action": "face_blush", "data": 1.0},
            "face_normal": {"action": "face_normal", "data": 1.0},
        }
        
        # 表情组合模板
        self.expression_combinations = {
            "happy": {
                "eye": "eye_smile",
                "eyebrow": "eyebrow_smile", 
                "mouth": "mouth_laugh",
                "face": "face_normal"
            },
            "very_happy": {
                "eye": "eye_smile",
                "eyebrow": "eyebrow_smile",
                "mouth": "mouth_laugh",
                "face": "face_blush"
            },
            "sad": {
                "eye": "eye_cry",
                "eyebrow": "eyebrow_sad",
                "mouth": "mouth_sad",
                "face": "face_normal"
            },
            "angry": {
                "eye": "eye_normal",
                "eyebrow": "eyebrow_angry",
                "mouth": "mouth_angry",
                "face": "face_normal"
            },
            "fear": {
                "eye": "eye_close",
                "eyebrow": "eyebrow_normal",
                "mouth": "mouth_normal",
                "face": "face_normal"
            },
            "shy": {
                "eye": "eye_normal",
                "eyebrow": "eyebrow_normal",
                "mouth": "mouth_pout",
                "face": "face_blush"
            },
            "neutral": {
                "eye": "eye_normal",
                "eyebrow": "eyebrow_normal",
                "mouth": "mouth_normal",
                "face": "face_normal"
            }
        }
    
    def select_expression_by_mood(self, mood_values: dict[str, int]) -> str:
        """根据情绪值选择合适的表情组合"""
        joy = mood_values.get("joy", 5)
        anger = mood_values.get("anger", 1)
        sorrow = mood_values.get("sorrow", 1)
        fear = mood_values.get("fear", 1)
        
        # 找出最强的情绪
        emotions = {
            "joy": joy,
            "anger": anger,
            "sorrow": sorrow,
            "fear": fear
        }
        
        # 获取最强情绪
        dominant_emotion = max(emotions, key=emotions.get)
        dominant_value = emotions[dominant_emotion]
        
        # 根据情绪强度和类型选择表情
        if dominant_emotion == "joy":
            if joy >= 8:
                return "very_happy"
            elif joy >= 6:
                return "happy"
            elif joy >= 4:
                return "shy"
            else:
                return "neutral"
        elif dominant_emotion == "anger" and anger >= 6:
            return "angry"
        elif dominant_emotion == "sorrow" and sorrow >= 6:
            return "sad"
        elif dominant_emotion == "fear" and fear >= 6:
            return "fear"
        else:
            return "neutral"
    
    async def send_expression(self, expression_name: str):
        """发送表情组合"""
        if expression_name not in self.expression_combinations:
            logger.warning(f"[{self.chat_id}] 未知表情: {expression_name}")
            return
        
        combination = self.expression_combinations[expression_name]
        
        # 依次发送各部位表情
        for part, expression_key in combination.items():
            if expression_key in self.expressions:
                expression_data = self.expressions[expression_key]
                await send_api.custom_to_stream(
                    message_type="facial_expression",
                    content=expression_data,
                    stream_id=self.chat_id
                )
                logger.info(f"[{self.chat_id}] 发送面部表情 {part}: {expression_data}")
                await asyncio.sleep(0.1)  # 短暂延迟避免同时发送过多消息
        
        # 通知ChatMood需要更新amadus
        # 这里需要从mood_manager获取ChatMood实例并标记
        chat_mood = mood_manager.get_mood_by_chat_id(self.chat_id)
        if chat_mood.last_expression != expression_name:
            chat_mood.last_expression = expression_name
            chat_mood.expression_needs_update = True
    
    async def send_expression_by_mood(self, mood_values: dict[str, int]):
        """根据情绪值发送相应的面部表情"""
        expression_name = self.select_expression_by_mood(mood_values)
        logger.info(f"[{self.chat_id}] 根据情绪值选择表情: {expression_name}, 情绪值: {mood_values}")
        await self.send_expression(expression_name)
    
    async def reset_expression(self):
        """重置为中性表情"""
        await self.send_expression("neutral")


class ChatMood:
    def __init__(self, chat_id: str):
        self.chat_id: str = chat_id
        self.mood_state: str = "感觉很平静"
        self.mood_values: dict[str, int] = {"joy": 5, "anger": 1, "sorrow": 1, "fear": 1}

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
        
        # 添加面部表情系统
        self.facial_expression = FacialExpression(chat_id)
        self.last_expression = "neutral"  # 记录上一次的表情
        self.expression_needs_update = False  # 标记表情是否需要更新
        
        # 设置初始中性表情
        asyncio.create_task(self.facial_expression.reset_expression())
        self.expression_needs_update = True  # 初始化时也标记需要更新

    def _parse_numerical_mood(self, response: str) -> dict[str, int] | None:
        try:
            # The LLM might output markdown with json inside
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            data = json.loads(response)

            # Validate
            required_keys = {"joy", "anger", "sorrow", "fear"}
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
            old_mood_values = self.mood_values.copy()
            self.mood_values = numerical_mood_response
            
            # 发送面部表情
            new_expression = self.facial_expression.select_expression_by_mood(self.mood_values)
            if new_expression != self.last_expression:
                # 立即发送表情
                asyncio.create_task(self.facial_expression.send_expression(new_expression))
                self.last_expression = new_expression
                self.expression_needs_update = True  # 标记表情已更新

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
            old_mood_values = self.mood_values.copy()
            self.mood_values = numerical_mood_response
            
            # 发送面部表情
            new_expression = self.facial_expression.select_expression_by_mood(self.mood_values)
            if new_expression != self.last_expression:
                # 立即发送表情
                asyncio.create_task(self.facial_expression.send_expression(new_expression))
                self.last_expression = new_expression
                self.expression_needs_update = True  # 标记表情已更新

        self.regression_count += 1

    async def send_expression_update_if_needed(self):
        """如果表情有变化，发送更新到amadus"""
        if self.expression_needs_update:
            # 发送当前表情状态到amadus，使用简洁的action/data格式
            expression_data = {
                "action": self.last_expression,
                "data": 1.0
            }
            
            await send_api.custom_to_stream(
                message_type="amadus_expression_update",
                content=expression_data,
                stream_id=self.chat_id
            )
            
            logger.info(f"[{self.chat_id}] 发送表情更新到amadus: {expression_data}")
            self.expression_needs_update = False  # 重置标记


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


class ExpressionUpdateTask(AsyncTask):
    def __init__(self, mood_manager: "MoodManager"):
        super().__init__(task_name="ExpressionUpdateTask", run_interval=1)
        self.mood_manager = mood_manager

    async def run(self):
        logger.debug("Running expression update task...")
        for mood in self.mood_manager.mood_list:
            await mood.send_expression_update_if_needed()


class MoodManager:
    def __init__(self):
        self.mood_list: list[ChatMood] = []
        """当前情绪状态"""
        self.task_started: bool = False

    async def start(self):
        """启动情绪回归后台任务"""
        if self.task_started:
            return

        logger.info("启动情绪管理任务...")
        
        # 启动情绪回归任务
        regression_task = MoodRegressionTask(self)
        await async_task_manager.add_task(regression_task)
        
        # 启动表情更新任务
        expression_task = ExpressionUpdateTask(self)
        await async_task_manager.add_task(expression_task)
        
        self.task_started = True
        logger.info("情绪管理任务已启动（包含情绪回归和表情更新）")

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
                mood.mood_values = {"joy": 5, "anger": 1, "sorrow": 1, "fear": 1}
                mood.regression_count = 0
                # 重置面部表情为中性
                asyncio.create_task(mood.facial_expression.reset_expression())
                mood.last_expression = "neutral"
                mood.expression_needs_update = True  # 标记表情需要更新
                return
        
        # 如果没有找到现有的mood，创建新的
        new_mood = ChatMood(chat_id)
        self.mood_list.append(new_mood)
        asyncio.create_task(new_mood.facial_expression.reset_expression())
        new_mood.expression_needs_update = True  # 标记表情需要更新

    def get_facial_expression_by_chat_id(self, chat_id: str) -> FacialExpression:
        """获取聊天对应的面部表情管理器"""
        for mood in self.mood_list:
            if mood.chat_id == chat_id:
                return mood.facial_expression
        
        # 如果没有找到，创建新的
        new_mood = ChatMood(chat_id)
        self.mood_list.append(new_mood)
        return new_mood.facial_expression


init_prompt()

mood_manager = MoodManager()
"""全局情绪管理器"""
