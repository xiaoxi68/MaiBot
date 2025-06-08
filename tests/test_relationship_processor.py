import os
import sys
import asyncio
import random
import time
import traceback
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.common.message_repository import find_messages
from src.common.database.database_model import ActionRecords, ChatStreams
from src.config.config import global_config
from src.person_info.person_info import person_info_manager
from src.chat.utils.utils import translate_timestamp_to_human_readable
from src.chat.heart_flow.observation.observation import Observation
from src.llm_models.utils_model import LLMRequest
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.person_info.relationship_manager import relationship_manager
from src.common.logger_manager import get_logger
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.relation_info import RelationInfo

logger = get_logger("processor")

async def get_person_id_list(messages: List[Dict[str, Any]]) -> List[str]:
    """
    从消息列表中提取不重复的 person_id 列表 (忽略机器人自身)。

    Args:
        messages: 消息字典列表。

    Returns:
        一个包含唯一 person_id 的列表。
    """
    person_ids_set = set()  # 使用集合来自动去重

    for msg in messages:
        platform = msg.get("user_platform")
        user_id = msg.get("user_id")

        # 检查必要信息是否存在 且 不是机器人自己
        if not all([platform, user_id]) or user_id == global_config.bot.qq_account:
            continue

        person_id = person_info_manager.get_person_id(platform, user_id)

        # 只有当获取到有效 person_id 时才添加
        if person_id:
            person_ids_set.add(person_id)

    return list(person_ids_set)  # 将集合转换为列表返回

class ChattingObservation(Observation):
    def __init__(self, chat_id):
        super().__init__(chat_id)
        self.chat_id = chat_id
        self.platform = "qq"
        
        # 从数据库获取聊天类型和目标信息
        chat_info = ChatStreams.select().where(ChatStreams.stream_id == chat_id).first()
        self.is_group_chat = True
        self.chat_target_info = {
            "person_name": chat_info.group_name if chat_info else None,
            "user_nickname": chat_info.group_name if chat_info else None
        }

        # 初始化其他属性
        self.talking_message = []
        self.talking_message_str = ""
        self.talking_message_str_truncate = ""
        self.name = global_config.bot.nickname
        self.nick_name = global_config.bot.alias_names
        self.max_now_obs_len = global_config.focus_chat.observation_context_size
        self.overlap_len = global_config.focus_chat.compressed_length
        self.mid_memories = []
        self.max_mid_memory_len = global_config.focus_chat.compress_length_limit
        self.mid_memory_info = ""
        self.person_list = []
        self.oldest_messages = []
        self.oldest_messages_str = ""
        self.compressor_prompt = ""
        self.last_observe_time = 0

    def get_observe_info(self, ids=None):
        """获取观察信息"""
        return self.talking_message_str

def init_prompt():
    relationship_prompt = """
<聊天记录>
{chat_observe_info}
</聊天记录>

<人物信息>
{relation_prompt}
</人物信息>

请区分聊天记录的内容和你之前对人的了解，聊天记录是现在发生的事情，人物信息是之前对某个人的持久的了解。

{name_block}
现在请你总结提取某人的信息，提取成一串文本
1. 根据聊天记录的需求，如果需要你和某个人的信息，请输出你和这个人之间精简的信息
2. 如果没有特别需要提及的信息，就不用输出这个人的信息
3. 如果有人问你对他的看法或者关系，请输出你和这个人之间的信息

请从这些信息中提取出你对某人的了解信息，信息提取成一串文本：

请严格按照以下输出格式，不要输出多余内容，person_name可以有多个：
{{
    "person_name": "信息",
    "person_name2": "信息",
    "person_name3": "信息",
}}

"""
    Prompt(relationship_prompt, "relationship_prompt")

class RelationshipProcessor:
    log_prefix = "关系"

    def __init__(self, subheartflow_id: str):
        self.subheartflow_id = subheartflow_id

        self.llm_model = LLMRequest(
            model=global_config.model.relation,
            request_type="relation",
        )

        # 直接从数据库获取名称
        chat_info = ChatStreams.select().where(ChatStreams.stream_id == subheartflow_id).first()
        name = chat_info.group_name if chat_info else "未知"
        self.log_prefix = f"[{name}] "

    async def process_info(
        self, observations: Optional[List[Observation]] = None, running_memorys: Optional[List[Dict]] = None, *infos
    ) -> List[InfoBase]:
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
        self, observations: Optional[List[Observation]] = None,
    ):
        """
        在回复前进行思考，生成内心想法并收集工具调用结果

        参数:
            observations: 观察信息

        返回:
            如果return_prompt为False:
                tuple: (current_mind, past_mind) 当前想法和过去的想法列表
            如果return_prompt为True:
                tuple: (current_mind, past_mind, prompt) 当前想法、过去的想法列表和使用的prompt
        """

        if observations is None:
            observations = []
        for observation in observations:
            if isinstance(observation, ChattingObservation):
                # 获取聊天元信息
                is_group_chat = observation.is_group_chat
                chat_target_info = observation.chat_target_info
                chat_target_name = "对方"  # 私聊默认名称
                if not is_group_chat and chat_target_info:
                    # 优先使用person_name，其次user_nickname，最后回退到默认值
                    chat_target_name = (
                        chat_target_info.get("person_name") or chat_target_info.get("user_nickname") or chat_target_name
                    )
                # 获取聊天内容
                chat_observe_info = observation.get_observe_info()
                person_list = observation.person_list

        nickname_str = ""
        for nicknames in global_config.bot.alias_names:
            nickname_str += f"{nicknames},"
        name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"

        if is_group_chat:
            relation_prompt_init = "你对群聊里的人的印象是：\n"
        else:
            relation_prompt_init = "你对对方的印象是：\n"
        
        relation_prompt = ""
        for person in person_list:
            relation_prompt += f"{await relationship_manager.build_relationship_info(person, is_id=True)}\n"
            
        if relation_prompt:
            relation_prompt = relation_prompt_init + relation_prompt
        else:
            relation_prompt = relation_prompt_init + "没有特别在意的人\n"

        prompt = (await global_prompt_manager.get_prompt_async("relationship_prompt")).format(
            name_block=name_block,
            relation_prompt=relation_prompt,
            time_now=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            chat_observe_info=chat_observe_info,
        )
        # The above code is a Python script that is attempting to print the variable `prompt`.
        # However, the code is not complete as the content of the `prompt` variable is missing.
        # print(prompt)

        content = ""
        try:
            content, _ = await self.llm_model.generate_response_async(prompt=prompt)
            if not content:
                logger.warning(f"{self.log_prefix} LLM返回空结果，关系识别失败。")
        except Exception as e:
            # 处理总体异常
            logger.error(f"{self.log_prefix} 执行LLM请求或处理响应时出错: {e}")
            logger.error(traceback.format_exc())
            content = "关系识别过程中出现错误"

        if content == "None":
            content = ""
        # 记录初步思考结果
        logger.info(f"{self.log_prefix} 关系识别prompt: \n{prompt}\n")
        logger.info(f"{self.log_prefix} 关系识别: {content}")

        return content

init_prompt()

# ==== 只复制最小依赖的relationship_manager ====
class SimpleRelationshipManager:
    async def build_relationship_info(self, person, is_id: bool = False) -> str:
        if is_id:
            person_id = person
        else:
            person_id = person_info_manager.get_person_id(person[0], person[1])

        person_name = await person_info_manager.get_value(person_id, "person_name")
        if not person_name or person_name == "none":
            return ""
        impression = await person_info_manager.get_value(person_id, "impression")
        interaction = await person_info_manager.get_value(person_id, "interaction")
        points = await person_info_manager.get_value(person_id, "points") or []
        
        if isinstance(points, str):
            try:
                import ast
                points = ast.literal_eval(points)
            except (SyntaxError, ValueError):
                points = []
        
        import random
        random_points = random.sample(points, min(3, len(points))) if points else []
        
        nickname_str = await person_info_manager.get_value(person_id, "nickname")
        platform = await person_info_manager.get_value(person_id, "platform")
        relation_prompt = f"'{person_name}' ，ta在{platform}上的昵称是{nickname_str}。"
        
        if impression:
            relation_prompt += f"你对ta的印象是：{impression}。"
        if interaction:
            relation_prompt += f"你与ta的关系是：{interaction}。"
        if random_points:
            for point in random_points:
                point_str = f"时间：{point[2]}。内容：{point[0]}"
            relation_prompt += f"你记得{person_name}最近的点是：{point_str}。"
        return relation_prompt

# 用于替换原有的relationship_manager
relationship_manager = SimpleRelationshipManager()

def get_raw_msg_by_timestamp_random(
    timestamp_start: float, timestamp_end: float, limit: int = 0, limit_mode: str = "latest"
) -> List[Dict[str, Any]]:
    """先在范围时间戳内随机选择一条消息，取得消息的chat_id，然后根据chat_id获取该聊天在指定时间戳范围内的消息"""
    # 获取所有消息，只取chat_id字段
    filter_query = {"time": {"$gt": timestamp_start, "$lt": timestamp_end}}
    all_msgs = find_messages(message_filter=filter_query)
    if not all_msgs:
        return []
    # 随机选一条
    msg = random.choice(all_msgs)
    chat_id = msg["chat_id"]
    timestamp_start = msg["time"]
    # 用 chat_id 获取该聊天在指定时间戳范围内的消息
    filter_query = {"chat_id": chat_id, "time": {"$gt": timestamp_start, "$lt": timestamp_end}}
    sort_order = [("time", 1)] if limit == 0 else None
    return find_messages(message_filter=filter_query, sort=sort_order, limit=limit, limit_mode="earliest")

def _build_readable_messages_internal(
    messages: List[Dict[str, Any]],
    replace_bot_name: bool = True,
    merge_messages: bool = False,
    timestamp_mode: str = "relative",
    truncate: bool = False,
) -> Tuple[str, List[Tuple[float, str, str]]]:
    """内部辅助函数，构建可读消息字符串和原始消息详情列表"""
    if not messages:
        return "", []

    message_details_raw: List[Tuple[float, str, str]] = []

    # 1 & 2: 获取发送者信息并提取消息组件
    for msg in messages:
        # 检查是否是动作记录
        if msg.get("is_action_record", False):
            is_action = True
            timestamp = msg.get("time")
            content = msg.get("display_message", "")
            message_details_raw.append((timestamp, global_config.bot.nickname, content, is_action))
            continue

        # 检查并修复缺少的user_info字段
        if "user_info" not in msg:
            msg["user_info"] = {
                "platform": msg.get("user_platform", ""),
                "user_id": msg.get("user_id", ""),
                "user_nickname": msg.get("user_nickname", ""),
                "user_cardname": msg.get("user_cardname", ""),
            }

        user_info = msg.get("user_info", {})
        platform = user_info.get("platform")
        user_id = user_info.get("user_id")
        user_nickname = user_info.get("user_nickname")
        user_cardname = user_info.get("user_cardname")
        timestamp = msg.get("time")
        
        if msg.get("display_message"):
            content = msg.get("display_message")
        else:
            content = msg.get("processed_plain_text", "")

        if "ᶠ" in content:
            content = content.replace("ᶠ", "")
        if "ⁿ" in content:
            content = content.replace("ⁿ", "")

        if not all([platform, user_id, timestamp is not None]):
            continue

        person_id = person_info_manager.get_person_id(platform, user_id)
        if replace_bot_name and user_id == global_config.bot.qq_account:
            person_name = f"{global_config.bot.nickname}(你)"
        else:
            person_name = person_info_manager.get_value_sync(person_id, "person_name")

        if not person_name:
            if user_cardname:
                person_name = f"昵称：{user_cardname}"
            elif user_nickname:
                person_name = f"{user_nickname}"
            else:
                person_name = "某人"

        if content != "":
            message_details_raw.append((timestamp, person_name, content, False))

    if not message_details_raw:
        return "", []

    message_details_raw.sort(key=lambda x: x[0])

    # 为每条消息添加一个标记，指示它是否是动作记录
    message_details_with_flags = []
    for timestamp, name, content, is_action in message_details_raw:
        message_details_with_flags.append((timestamp, name, content, is_action))

    # 应用截断逻辑
    message_details: List[Tuple[float, str, str, bool]] = []
    n_messages = len(message_details_with_flags)
    if truncate and n_messages > 0:
        for i, (timestamp, name, content, is_action) in enumerate(message_details_with_flags):
            if is_action:
                message_details.append((timestamp, name, content, is_action))
                continue

            percentile = i / n_messages
            original_len = len(content)
            limit = -1

            if percentile < 0.2:
                limit = 50
                replace_content = "......（记不清了）"
            elif percentile < 0.5:
                limit = 100
                replace_content = "......（有点记不清了）"
            elif percentile < 0.7:
                limit = 200
                replace_content = "......（内容太长了）"
            elif percentile < 1.0:
                limit = 300
                replace_content = "......（太长了）"

            truncated_content = content
            if 0 < limit < original_len:
                truncated_content = f"{content[:limit]}{replace_content}"

            message_details.append((timestamp, name, truncated_content, is_action))
    else:
        message_details = message_details_with_flags

    # 合并连续消息
    merged_messages = []
    if merge_messages and message_details:
        current_merge = {
            "name": message_details[0][1],
            "start_time": message_details[0][0],
            "end_time": message_details[0][0],
            "content": [message_details[0][2]],
            "is_action": message_details[0][3]
        }

        for i in range(1, len(message_details)):
            timestamp, name, content, is_action = message_details[i]
            
            if is_action or current_merge["is_action"]:
                merged_messages.append(current_merge)
                current_merge = {
                    "name": name,
                    "start_time": timestamp,
                    "end_time": timestamp,
                    "content": [content],
                    "is_action": is_action
                }
                continue

            if name == current_merge["name"] and (timestamp - current_merge["end_time"] <= 60):
                current_merge["content"].append(content)
                current_merge["end_time"] = timestamp
            else:
                merged_messages.append(current_merge)
                current_merge = {
                    "name": name, 
                    "start_time": timestamp, 
                    "end_time": timestamp, 
                    "content": [content],
                    "is_action": is_action
                }
        merged_messages.append(current_merge)
    elif message_details:
        for timestamp, name, content, is_action in message_details:
            merged_messages.append(
                {
                    "name": name,
                    "start_time": timestamp,
                    "end_time": timestamp,
                    "content": [content],
                    "is_action": is_action
                }
            )

    # 格式化为字符串
    output_lines = []
    for merged in merged_messages:
        readable_time = translate_timestamp_to_human_readable(merged["start_time"], mode=timestamp_mode)

        if merged["is_action"]:
            output_lines.append(f"{readable_time}, {merged['content'][0]}")
        else:
            header = f"{readable_time}, {merged['name']} :"
            output_lines.append(header)
            for line in merged["content"]:
                stripped_line = line.strip()
                if stripped_line:
                    if stripped_line.endswith("。"):
                        stripped_line = stripped_line[:-1]
                    if not stripped_line.endswith("（内容太长）"):
                        output_lines.append(f"{stripped_line}")
                    else:
                        output_lines.append(stripped_line)
        output_lines.append("\n")

    formatted_string = "".join(output_lines).strip()
    return formatted_string, [(t, n, c) for t, n, c, is_action in message_details if not is_action]

def build_readable_messages(
    messages: List[Dict[str, Any]],
    replace_bot_name: bool = True,
    merge_messages: bool = False,
    timestamp_mode: str = "relative",
    read_mark: float = 0.0,
    truncate: bool = False,
    show_actions: bool = False,
) -> str:
    """将消息列表转换为可读的文本格式"""
    copy_messages = [msg.copy() for msg in messages]
    
    if show_actions and copy_messages:
        min_time = min(msg.get("time", 0) for msg in copy_messages)
        max_time = max(msg.get("time", 0) for msg in copy_messages)
        chat_id = copy_messages[0].get("chat_id") if copy_messages else None
        
        actions = ActionRecords.select().where(
            (ActionRecords.time >= min_time) & 
            (ActionRecords.time <= max_time) &
            (ActionRecords.chat_id == chat_id)
        ).order_by(ActionRecords.time)
        
        for action in actions:
            if action.action_build_into_prompt:
                action_msg = {
                    "time": action.time,
                    "user_id": global_config.bot.qq_account,
                    "user_nickname": global_config.bot.nickname,
                    "user_cardname": "",
                    "processed_plain_text": f"{action.action_prompt_display}",
                    "display_message": f"{action.action_prompt_display}",
                    "chat_info_platform": action.chat_info_platform,
                    "is_action_record": True,
                    "action_name": action.action_name,
                }
                copy_messages.append(action_msg)
        
        copy_messages.sort(key=lambda x: x.get("time", 0))

    if read_mark <= 0:
        formatted_string, _ = _build_readable_messages_internal(
            copy_messages, replace_bot_name, merge_messages, timestamp_mode, truncate
        )
        return formatted_string
    else:
        messages_before_mark = [msg for msg in copy_messages if msg.get("time", 0) <= read_mark]
        messages_after_mark = [msg for msg in copy_messages if msg.get("time", 0) > read_mark]

        formatted_before, _ = _build_readable_messages_internal(
            messages_before_mark, replace_bot_name, merge_messages, timestamp_mode, truncate
        )
        formatted_after, _ = _build_readable_messages_internal(
            messages_after_mark,
            replace_bot_name,
            merge_messages,
            timestamp_mode,
        )

        read_mark_line = "\n--- 以上消息是你已经看过---\n--- 请关注以下未读的新消息---\n"

        if formatted_before and formatted_after:
            return f"{formatted_before}{read_mark_line}{formatted_after}"
        elif formatted_before:
            return f"{formatted_before}{read_mark_line}"
        elif formatted_after:
            return f"{read_mark_line}{formatted_after}"
        else:
            return read_mark_line.strip()

async def test_relationship_processor():
    """测试关系处理器的功能"""
    
    # 测试10次
    for i in range(10):
        print(f"\n=== 测试 {i+1} ===")
        
        # 获取随机消息
        current_time = time.time()
        start_time = current_time - 864000  # 10天前
        messages = get_raw_msg_by_timestamp_random(start_time, current_time, limit=25)
        
        if not messages:
            print("没有找到消息，跳过此次测试")
            continue
            
        chat_id = messages[0]["chat_id"]
        
        # 构建可读消息
        chat_observe_info = build_readable_messages(
            messages,
            replace_bot_name=True,
            timestamp_mode="normal_no_YMD",
            truncate=True,
            show_actions=True,
        )
        # print(chat_observe_info)
        # 创建观察对象
        processor = RelationshipProcessor(chat_id)
        observation = ChattingObservation(chat_id)
        observation.talking_message_str = chat_observe_info
        observation.talking_message = messages  # 设置消息列表
        observation.person_list = await get_person_id_list(messages)  # 使用get_person_id_list获取person_list
        
        # 处理关系
        result = await processor.process_info([observation])
        
        if result:
            print("\n关系识别结果:")
            print(result[0].get_processed_info())
        else:
            print("关系识别失败")
            
        # 等待一下，避免请求过快
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(test_relationship_processor()) 