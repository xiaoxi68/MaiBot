
from src.config.config import global_config
from src.common.logger import get_logger
from src.individuality.individuality import get_individuality
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.utils.chat_message_builder import build_readable_messages, get_raw_msg_before_timestamp_with_chat
from src.chat.message_receive.message import MessageRecv
import time
from src.chat.utils.utils import get_recent_group_speaker
from src.chat.memory_system.Hippocampus import hippocampus_manager
import random

from src.person_info.relationship_manager import get_relationship_manager

logger = get_logger("prompt")


def init_prompt():
    Prompt("你正在qq群里聊天，下面是群里在聊的内容：", "chat_target_group1")
    Prompt("你正在和{sender_name}聊天，这是你们之前聊的内容：", "chat_target_private1")
    Prompt("在群里聊天", "chat_target_group2")
    Prompt("和{sender_name}私聊", "chat_target_private2")

    Prompt("\n你有以下这些**知识**：\n{prompt_info}\n请你**记住上面的知识**，之后可能会用到。\n", "knowledge_prompt")


    Prompt(
        """
你的名字叫{bot_name}，昵称是：{bot_other_names}，{prompt_personality}。
你现在的主要任务是和 {sender_name} 聊天。同时，也有其他用户会参与你们的聊天，但是你主要还是关注你和{sender_name}的聊天内容。

{background_dialogue_prompt}
--------------------------------
{now_time}
这是你和{sender_name}的对话，你们正在交流中：
{core_dialogue_prompt}

{message_txt}
回复可以简短一些。可以参考贴吧，知乎和微博的回复风格，回复不要浮夸，不要用夸张修辞，平淡一些。
不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。只输出回复内容，现在{sender_name}正在等待你的回复。
你的回复风格不要浮夸，有逻辑和条理，请你继续回复{sender_name}。""",
        "s4u_prompt",  # New template for private CHAT chat
    )


class PromptBuilder:
    def __init__(self):
        self.prompt_built = ""
        self.activate_messages = ""

    async def build_prompt_normal(
        self,
        message,
        chat_stream,
        message_txt: str,
        sender_name: str = "某人",
    ) -> str:
        prompt_personality = get_individuality().get_prompt(x_person=2, level=2)
        is_group_chat = bool(chat_stream.group_info)

        who_chat_in_group = []
        if is_group_chat:
            who_chat_in_group = get_recent_group_speaker(
                chat_stream.stream_id,
                (chat_stream.user_info.platform, chat_stream.user_info.user_id) if chat_stream.user_info else None,
                limit=global_config.normal_chat.max_context_size,
            )
        elif chat_stream.user_info:
            who_chat_in_group.append(
                (chat_stream.user_info.platform, chat_stream.user_info.user_id, chat_stream.user_info.user_nickname)
            )

        relation_prompt = ""
        if global_config.relationship.enable_relationship:
            for person in who_chat_in_group:
                relationship_manager = get_relationship_manager()
                relation_prompt += await relationship_manager.build_relationship_info(person)


        memory_prompt = ""
        related_memory = await hippocampus_manager.get_memory_from_text(
            text=message_txt, max_memory_num=2, max_memory_length=2, max_depth=3, fast_retrieval=False
        )

        related_memory_info = ""
        if related_memory:
            for memory in related_memory:
                related_memory_info += memory[1]
            memory_prompt = await global_prompt_manager.format_prompt(
                "memory_prompt", related_memory_info=related_memory_info
            )

        message_list_before_now = get_raw_msg_before_timestamp_with_chat(
            chat_id=chat_stream.stream_id,
            timestamp=time.time(),
            limit=100,
        )
        

        # 分别筛选核心对话和背景对话
        core_dialogue_list = []
        background_dialogue_list = []
        bot_id = str(global_config.bot.qq_account)
        target_user_id = str(message.chat_stream.user_info.user_id)

        for msg_dict in message_list_before_now:
            try:
                # 直接通过字典访问
                msg_user_id = str(msg_dict.get('user_id'))
                
                if msg_user_id == bot_id or msg_user_id == target_user_id:
                    core_dialogue_list.append(msg_dict)
                else:
                    background_dialogue_list.append(msg_dict)
            except Exception as e:
                logger.error(f"无法处理历史消息记录: {msg_dict}, 错误: {e}")
                
        if background_dialogue_list:
            latest_25_msgs = background_dialogue_list[-25:]
            background_dialogue_prompt = build_readable_messages(
                latest_25_msgs,
                merge_messages=True,
                timestamp_mode = "normal_no_YMD",
                show_pic = False,
            )
            background_dialogue_prompt = f"这是其他用户的发言：\n{background_dialogue_prompt}"
        else:
            background_dialogue_prompt = ""
                
        # 分别获取最新50条和最新25条（从message_list_before_now截取）
        core_dialogue_list = core_dialogue_list[-50:]
        
        first_msg = core_dialogue_list[0]
        start_speaking_user_id = first_msg.get('user_id')
        if start_speaking_user_id == bot_id:
            last_speaking_user_id = bot_id
            msg_seg_str = "你的发言：\n"
        else:
            start_speaking_user_id = target_user_id
            last_speaking_user_id = start_speaking_user_id
            msg_seg_str = "对方的发言：\n"
        
        msg_seg_str += f"{first_msg.get('processed_plain_text')}\n"

        all_msg_seg_list = []
        for msg in core_dialogue_list[1:]:
            speaker = msg.get('user_id')
            if speaker == last_speaking_user_id:
                #还是同一个人讲话
                msg_seg_str += f"{msg.get('processed_plain_text')}\n"
            else:
                #换人了
                msg_seg_str = f"{msg_seg_str}\n"
                all_msg_seg_list.append(msg_seg_str)
                
                if speaker == bot_id:
                    msg_seg_str = "你的发言：\n"
                else:
                    msg_seg_str = "对方的发言：\n"
                
                msg_seg_str += f"{msg.get('processed_plain_text')}\n"
                last_speaking_user_id = speaker
            
        all_msg_seg_list.append(msg_seg_str)


        core_msg_str = ""
        for msg in all_msg_seg_list:
            # print(f"msg: {msg}")
            core_msg_str += msg

        now_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        now_time = f"现在的时间是：{now_time}"

        template_name = "s4u_prompt"
        effective_sender_name = sender_name

        prompt = await global_prompt_manager.format_prompt(
            template_name,
            relation_prompt=relation_prompt,
            sender_name=effective_sender_name,
            memory_prompt=memory_prompt,
            core_dialogue_prompt=core_msg_str,
            background_dialogue_prompt=background_dialogue_prompt,
            message_txt=message_txt,
            bot_name=global_config.bot.nickname,
            bot_other_names="/".join(global_config.bot.alias_names),
            prompt_personality=prompt_personality,
            now_time=now_time,
        )

        return prompt


def weighted_sample_no_replacement(items, weights, k) -> list:
    """
    加权且不放回地随机抽取k个元素。

    参数：
        items: 待抽取的元素列表
        weights: 每个元素对应的权重（与items等长，且为正数）
        k: 需要抽取的元素个数
    返回：
        selected: 按权重加权且不重复抽取的k个元素组成的列表

        如果 items 中的元素不足 k 个，就只会返回所有可用的元素

    实现思路：
        每次从当前池中按权重加权随机选出一个元素，选中后将其从池中移除，重复k次。
        这样保证了：
        1. count越大被选中概率越高
        2. 不会重复选中同一个元素
    """
    selected = []
    pool = list(zip(items, weights))
    for _ in range(min(k, len(pool))):
        total = sum(w for _, w in pool)
        r = random.uniform(0, total)
        upto = 0
        for idx, (item, weight) in enumerate(pool):
            upto += weight
            if upto >= r:
                selected.append(item)
                pool.pop(idx)
                break
    return selected


init_prompt()
prompt_builder = PromptBuilder()
