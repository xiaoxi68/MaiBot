import asyncio
import json
import time
import random

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
   
   # 执行眨眼动作
   await facial_expression.perform_blink()

3. 自动表情系统：
   - 当情绪值更新时，系统会自动根据mood_values选择合适的面部表情
   - 只有当新表情与当前表情不同时才会发送，避免重复发送
   - 支持joy >= 8时显示very_happy，joy >= 6时显示happy等梯度表情

4. amadus表情更新系统：
   - 每1秒检查一次表情是否有变化，如有变化则发送到amadus
   - 每次mood更新后立即发送表情更新
   - 发送消息类型为"amadus_expression_update"，格式为{"action": "表情名", "data": 1.0}

5. 眨眼系统：
   - 每4-6秒随机执行一次眨眼动作
   - 眨眼包含两个阶段：先闭眼（eye_close=1.0），保持0.1-0.15秒，然后睁眼（eye_close=0.0）
   - 眨眼使用override_values参数临时覆盖eye_close值，不修改原始表情状态
   - 眨眼时会发送完整的表情状态，包含当前表情的所有动作
   - 当eye部位已经是eye_happy_weak时，跳过眨眼动作

6. 表情选择逻辑：
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
        
        # 预定义面部表情动作（根据用户定义的表情动作）
        self.expressions = {
            # 眼睛表情
            "eye_happy_weak": {"action": "eye_happy_weak", "data": 1.0},
            "eye_close": {"action": "eye_close", "data": 1.0},
            "eye_shift_left": {"action": "eye_shift_left", "data": 1.0},
            "eye_shift_right": {"action": "eye_shift_right", "data": 1.0},
            # "eye_smile": {"action": "eye_smile", "data": 1.0},  # 未定义，占位
            # "eye_cry": {"action": "eye_cry", "data": 1.0},  # 未定义，占位
            # "eye_normal": {"action": "eye_normal", "data": 1.0},  # 未定义，占位
            
            # 眉毛表情
            "eyebrow_happy_weak": {"action": "eyebrow_happy_weak", "data": 1.0},
            "eyebrow_happy_strong": {"action": "eyebrow_happy_strong", "data": 1.0},
            "eyebrow_angry_weak": {"action": "eyebrow_angry_weak", "data": 1.0},
            "eyebrow_angry_strong": {"action": "eyebrow_angry_strong", "data": 1.0},
            "eyebrow_sad_weak": {"action": "eyebrow_sad_weak", "data": 1.0},
            "eyebrow_sad_strong": {"action": "eyebrow_sad_strong", "data": 1.0},
            # "eyebrow_smile": {"action": "eyebrow_smile", "data": 1.0},  # 未定义，占位
            # "eyebrow_angry": {"action": "eyebrow_angry", "data": 1.0},  # 未定义，占位
            # "eyebrow_sad": {"action": "eyebrow_sad", "data": 1.0},  # 未定义，占位
            # "eyebrow_normal": {"action": "eyebrow_normal", "data": 1.0},  # 未定义，占位
            
            # 嘴巴表情（注意：用户定义的是mouth，可能是mouth的拼写错误）
            "mouth_default": {"action": "mouth_default", "data": 1.0},
            "mouth_happy_strong": {"action": "mouth_happy_strong", "data": 1.0},  # 保持用户原始拼写
            "mouth_angry_weak": {"action": "mouth_angry_weak", "data": 1.0},
            # "mouth_sad": {"action": "mouth_sad", "data": 1.0},  # 未定义，占位
            # "mouth_angry": {"action": "mouth_angry", "data": 1.0},  # 未定义，占位
            # "mouth_laugh": {"action": "mouth_laugh", "data": 1.0},  # 未定义，占位
            # "mouth_pout": {"action": "mouth_pout", "data": 1.0},  # 未定义，占位
            # "mouth_normal": {"action": "mouth_normal", "data": 1.0},  # 未定义，占位
            
            # 脸部表情
            # "face_blush": {"action": "face_blush", "data": 1.0},  # 未定义，占位
            # "face_normal": {"action": "face_normal", "data": 1.0},  # 未定义，占位
        }
        
        # 表情组合模板（根据新的表情动作调整）
        self.expression_combinations = {
            "happy": {
                "eye": "eye_happy_weak",
                "eyebrow": "eyebrow_happy_weak", 
                "mouth": "mouth_default",
            },
            "very_happy": {
                "eye": "eye_happy_weak",
                "eyebrow": "eyebrow_happy_strong",
                "mouth": "mouth_happy_strong",
            },
            "sad": {
                "eyebrow": "eyebrow_sad_strong",
                "mouth": "mouth_default",
            },
            "angry": {
                "eyebrow": "eyebrow_angry_strong",
                "mouth": "mouth_angry_weak",
            },
            "fear": {
                "eyebrow": "eyebrow_sad_weak",
                "mouth": "mouth_default",
            },
            "shy": {
                "eyebrow": "eyebrow_happy_weak",
                "mouth": "mouth_default",
            },
            "neutral": {
                "eyebrow": "eyebrow_happy_weak",
                "mouth": "mouth_default",
            }
        }
        
        # 未定义的表情部位（保留备用）：
        # 眼睛：eye_smile, eye_cry, eye_close, eye_normal
        # 眉毛：eyebrow_smile, eyebrow_angry, eyebrow_sad, eyebrow_normal  
        # 嘴巴：mouth_sad, mouth_angry, mouth_laugh, mouth_pout, mouth_normal
        # 脸部：face_blush, face_normal
        
        # 初始化当前表情状态
        self.last_expression = "neutral"
    
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
        _dominant_value = emotions[dominant_emotion]
        
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
    
    async def _send_expression_actions(self, expression_name: str, log_prefix: str = "发送面部表情", override_values: dict = None):
        """统一的表情动作发送函数 - 发送完整的表情状态
        
        Args:
            expression_name: 表情名称
            log_prefix: 日志前缀
            override_values: 需要覆盖的动作值，格式为 {"action_name": value}
        """
        if expression_name not in self.expression_combinations:
            logger.warning(f"[{self.chat_id}] 未知表情: {expression_name}")
            return
        
        combination = self.expression_combinations[expression_name]
        
        # 按部位分组所有已定义的表情动作
        expressions_by_part = {
            "eye": {},
            "eyebrow": {},
            "mouth": {}
        }
        
        # 将所有已定义的表情按部位分组
        for expression_key, expression_data in self.expressions.items():
            if expression_key.startswith("eye_"):
                expressions_by_part["eye"][expression_key] = expression_data
            elif expression_key.startswith("eyebrow_"):
                expressions_by_part["eyebrow"][expression_key] = expression_data
            elif expression_key.startswith("mouth_"):
                expressions_by_part["mouth"][expression_key] = expression_data
        
        # 构建完整的表情状态
        complete_expression_state = {}
        
        # 为每个部位构建完整的表情动作状态
        for part in expressions_by_part.keys():
            if expressions_by_part[part]:  # 如果该部位有已定义的表情
                part_actions = {}
                active_expression = combination.get(part)  # 当前激活的表情
                
                # 添加该部位所有已定义的表情动作
                for expression_key, expression_data in expressions_by_part[part].items():
                    # 复制表情数据并设置激活状态
                    action_data = expression_data.copy()
                    
                    # 检查是否有覆盖值
                    if override_values and expression_key in override_values:
                        action_data["data"] = override_values[expression_key]
                    else:
                        action_data["data"] = 1.0 if expression_key == active_expression else 0.0
                    
                    part_actions[expression_key] = action_data
                
                complete_expression_state[part] = part_actions
                logger.debug(f"[{self.chat_id}] 部位 {part}: 激活 {active_expression}, 总共 {len(part_actions)} 个动作")
        
        # 发送完整的表情状态
        if complete_expression_state:
            package_data = {
                "expression_name": expression_name,
                "actions": complete_expression_state
            }
            
            await send_api.custom_to_stream(
                message_type="face_emotion",
                content=package_data,
                stream_id=self.chat_id,
                storage_message=False,
                show_log=False,
            )
            
            # 统计信息
            total_actions = sum(len(part_actions) for part_actions in complete_expression_state.values())
            active_actions = [f"{part}:{combination.get(part, 'none')}" for part in complete_expression_state.keys()]
            logger.info(f"[{self.chat_id}] {log_prefix}: {expression_name} - 发送{total_actions}个动作，激活: {', '.join(active_actions)}")
        else:
            logger.warning(f"[{self.chat_id}] 表情 {expression_name} 没有有效的动作可发送")
    
    async def send_expression(self, expression_name: str):
        """发送表情组合"""
        await self._send_expression_actions(expression_name, "发送面部表情")
        
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
    
    async def perform_blink(self):
        """执行眨眼动作"""
        # 检查当前表情组合中eye部位是否为eye_happy_weak
        current_combination = self.expression_combinations.get(self.last_expression, {})
        current_eye_expression = current_combination.get("eye")
        
        if current_eye_expression == "eye_happy_weak":
            logger.debug(f"[{self.chat_id}] 当前eye表情为{current_eye_expression}，跳过眨眼动作")
            return
        
        logger.debug(f"[{self.chat_id}] 执行眨眼动作")
        
        # 第一阶段：闭眼
        await self._send_expression_actions(
            self.last_expression, 
            "眨眼-闭眼", 
            override_values={"eye_close": 1.0}
        )
        
        # 等待0.1-0.15秒
        blink_duration = random.uniform(0.7, 0.12)
        await asyncio.sleep(blink_duration)
        
        # 第二阶段：睁眼
        await self._send_expression_actions(
            self.last_expression, 
            "眨眼-睁眼", 
            override_values={"eye_close": 0.0}
        )
        
        
    async def perform_shift(self):
        """执行眨眼动作"""
        # 检查当前表情组合中eye部位是否为eye_happy_weak
        current_combination = self.expression_combinations.get(self.last_expression, {})
        current_eye_expression = current_combination.get("eye")
        
        direction = random.choice(["left", "right"])
        strength = random.randint(6, 9) / 10
        time_duration = random.randint(5, 15) / 10
        
        if current_eye_expression == "eye_happy_weak" or current_eye_expression == "eye_close":
            logger.debug(f"[{self.chat_id}] 当前eye表情为{current_eye_expression}，跳过漂移动作")
            return
        
        logger.debug(f"[{self.chat_id}] 执行漂移动作，方向：{direction}，强度：{strength}，时间：{time_duration}")
        
        if direction == "left":
            override_values = {"eye_shift_left": strength}
            back_values = {"eye_shift_left": 0.0}
        else:
            override_values = {"eye_shift_right": strength}
            back_values = {"eye_shift_right": 0.0}
        
        # 第一阶段：闭眼
        await self._send_expression_actions(
            self.last_expression, 
            "漂移", 
            override_values=override_values
        )
        
        # 等待0.1-0.15秒
        await asyncio.sleep(time_duration)
        
        # 第二阶段：睁眼
        await self._send_expression_actions(
            self.last_expression, 
            "回归", 
            override_values=back_values
        )



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
            _old_mood_values = self.mood_values.copy()
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
            _old_mood_values = self.mood_values.copy()
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
            # 使用统一的表情发送函数
            await self.facial_expression._send_expression_actions(
                self.last_expression, 
                "发送表情更新到amadus"
            )
            self.expression_needs_update = False  # 重置标记
    
    async def perform_blink(self):
        """执行眨眼动作"""
        await self.facial_expression.perform_blink()
        
    async def perform_shift(self):
        """执行漂移动作"""
        await self.facial_expression.perform_shift()


class MoodRegressionTask(AsyncTask):
    def __init__(self, mood_manager: "MoodManager"):
        super().__init__(task_name="MoodRegressionTask", run_interval=30)
        self.mood_manager = mood_manager
        self.run_count = 0

    async def run(self):
        self.run_count += 1
        logger.info(f"[回归任务] 第{self.run_count}次检查，当前管理{len(self.mood_manager.mood_list)}个聊天的情绪状态")
        
        now = time.time()
        regression_executed = 0
        
        for mood in self.mood_manager.mood_list:
            chat_info = f"chat {mood.chat_id}"
            
            if mood.last_change_time == 0:
                logger.debug(f"[回归任务] {chat_info} 尚未有情绪变化，跳过回归")
                continue

            time_since_last_change = now - mood.last_change_time
            
            if time_since_last_change > 120:  # 2分钟
                if mood.regression_count >= 3:
                    logger.debug(f"[回归任务] {chat_info} 已达到最大回归次数(3次)，停止回归")
                    continue

                logger.info(f"[回归任务] {chat_info} 开始情绪回归 (距上次变化{int(time_since_last_change)}秒，第{mood.regression_count + 1}次回归)")
                await mood.regress_mood()
                regression_executed += 1
            else:
                remaining_time = 120 - time_since_last_change
                logger.debug(f"[回归任务] {chat_info} 距离回归还需等待{int(remaining_time)}秒")
        
        if regression_executed > 0:
            logger.info(f"[回归任务] 本次执行了{regression_executed}个聊天的情绪回归")
        else:
            logger.debug(f"[回归任务] 本次没有符合回归条件的聊天")


class ExpressionUpdateTask(AsyncTask):
    def __init__(self, mood_manager: "MoodManager"):
        super().__init__(task_name="ExpressionUpdateTask", run_interval=0.3)
        self.mood_manager = mood_manager
        self.run_count = 0
        self.last_log_time = 0

    async def run(self):
        self.run_count += 1
        now = time.time()
        
        # 每60秒输出一次状态信息（避免日志太频繁）
        if now - self.last_log_time > 60:
            logger.info(f"[表情任务] 已运行{self.run_count}次，当前管理{len(self.mood_manager.mood_list)}个聊天的表情状态")
            self.last_log_time = now
        
        updates_sent = 0
        for mood in self.mood_manager.mood_list:
            if mood.expression_needs_update:
                logger.debug(f"[表情任务] chat {mood.chat_id} 检测到表情变化，发送更新")
                await mood.send_expression_update_if_needed()
                updates_sent += 1
        
        if updates_sent > 0:
            logger.info(f"[表情任务] 发送了{updates_sent}个表情更新")


class BlinkTask(AsyncTask):
    def __init__(self, mood_manager: "MoodManager"):
        # 初始随机间隔4-6秒
        super().__init__(task_name="BlinkTask", run_interval=4)
        self.mood_manager = mood_manager
        self.run_count = 0
        self.last_log_time = 0

    async def run(self):
        self.run_count += 1
        now = time.time()
        
        # 每60秒输出一次状态信息（避免日志太频繁）
        if now - self.last_log_time > 20:
            logger.debug(f"[眨眼任务] 已运行{self.run_count}次，当前管理{len(self.mood_manager.mood_list)}个聊天的眨眼状态")
            self.last_log_time = now
        
        interval_add = random.randint(0, 2) 
        await asyncio.sleep(interval_add)
        
        blinks_executed = 0
        for mood in self.mood_manager.mood_list:
            try:
                await mood.perform_blink()
                blinks_executed += 1
            except Exception as e:
                logger.error(f"[眨眼任务] 处理chat {mood.chat_id}时出错: {e}")
        
        if blinks_executed > 0:
            logger.debug(f"[眨眼任务] 本次执行了{blinks_executed}个聊天的眨眼动作")
            
class ShiftTask(AsyncTask):
    def __init__(self, mood_manager: "MoodManager"):
        # 初始随机间隔4-6秒
        super().__init__(task_name="ShiftTask", run_interval=8)
        self.mood_manager = mood_manager
        self.run_count = 0
        self.last_log_time = 0

    async def run(self):
        self.run_count += 1
        now = time.time()
        
        # 每60秒输出一次状态信息（避免日志太频繁）
        if now - self.last_log_time > 20:
            logger.debug(f"[漂移任务] 已运行{self.run_count}次，当前管理{len(self.mood_manager.mood_list)}个聊天的漂移状态")
            self.last_log_time = now
        
        interval_add = random.randint(0, 3)
        await asyncio.sleep(interval_add)
        
        blinks_executed = 0
        for mood in self.mood_manager.mood_list:
            try:
                await mood.perform_shift()
                blinks_executed += 1
            except Exception as e:
                logger.error(f"[漂移任务] 处理chat {mood.chat_id}时出错: {e}")
        
        if blinks_executed > 0:
            logger.debug(f"[漂移任务] 本次执行了{blinks_executed}个聊天的漂移动作")


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
        
        # 启动眨眼任务
        blink_task = BlinkTask(self)
        await async_task_manager.add_task(blink_task)
        
        # 启动漂移任务
        shift_task = ShiftTask(self)
        await async_task_manager.add_task(shift_task)
        
        self.task_started = True
        logger.info("情绪管理任务已启动（包含情绪回归、表情更新和眨眼动作）")

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
