from .observation import ChattingObservation
from src.plugins.models.utils_model import LLMRequest
from src.config.config import global_config
import time
import traceback
from src.common.logger_manager import get_logger
from src.individuality.individuality import Individuality
import random
from ..plugins.utils.prompt_builder import Prompt, global_prompt_manager
from src.do_tool.tool_use import ToolUser
from src.plugins.utils.json_utils import safe_json_dumps, process_llm_tool_calls
from src.heart_flow.chat_state_info import ChatStateInfo
from src.plugins.chat.chat_stream import chat_manager
from src.plugins.heartFC_chat.heartFC_Cycleinfo import CycleInfo
import difflib
from src.plugins.person_info.relationship_manager import relationship_manager
from src.plugins.memory_system.Hippocampus import HippocampusManager
import jieba


logger = get_logger("sub_heartflow")


def init_prompt():
    # --- Group Chat Prompt ---
    group_prompt = """
{extra_info}
{relation_prompt}
你的名字是{bot_name},{prompt_personality},你现在{mood_info}
{cycle_info_block}
现在是{time_now}，你正在上网，和qq群里的网友们聊天，以下是正在进行的聊天内容：
{chat_observe_info}

以下是你之前对这个群聊的陈述：
{last_mind}

现在请你继续输出思考内容，输出要求：
1. 根据聊天内容生成你的想法，{hf_do_next}
2. 参考之前的思考，基于之前的内容对这个群聊继续陈述，可以删除不重要的内容，添加新的内容
3. 思考群内进行的话题，话题由谁发起，进展状况如何，你如何参与？思考你在群聊天中的角色，你是一个什么样的人，你在这个群聊中扮演什么角色？
4. 注意群聊的时间线索，思考聊天的时间线。
5. 请结合你做出的行为，对前面的陈述进行补充
6. 语言简洁自然，不要分点，不要浮夸，不要修辞，仅输出思考内容就好"""
    Prompt(group_prompt, "sub_heartflow_prompt_before")

    # --- Private Chat Prompt ---
    private_prompt = """
{extra_info}
{relation_prompt}
你的名字是{bot_name},{prompt_personality},你现在{mood_info}
{cycle_info_block}
现在是{time_now}，你正在上网，和 {chat_target_name} 私聊，以下是你们的聊天内容：
{chat_observe_info}

以下是你之前在这个群聊中的思考：
{last_mind}

请仔细阅读聊天内容，想想你和 {chat_target_name} 的关系，回顾你们刚刚的交流,你刚刚发言和对方的反应，思考聊天的主题。
请思考你要不要回复以及如何回复对方。
思考并输出你的内心想法
输出要求：
1. 根据聊天内容生成你的想法，{hf_do_next}
2. 不要分点、不要使用表情符号
3. 避免多余符号(冒号、引号、括号等)
4. 语言简洁自然，不要浮夸
5. 如果你刚发言，对方没有回复你，请谨慎回复"""
    Prompt(private_prompt, "sub_heartflow_prompt_private_before")


def calculate_similarity(text_a: str, text_b: str) -> float:
    """
    计算两个文本字符串的相似度。
    """
    if not text_a or not text_b:
        return 0.0
    matcher = difflib.SequenceMatcher(None, text_a, text_b)
    return matcher.ratio()


def calculate_replacement_probability(similarity: float) -> float:
    """
    根据相似度计算替换的概率。
    规则：
    - 相似度 <= 0.4: 概率 = 0
    - 相似度 >= 0.9: 概率 = 1
    - 相似度 == 0.6: 概率 = 0.7
    - 0.4 < 相似度 <= 0.6: 线性插值 (0.4, 0) 到 (0.6, 0.7)
    - 0.6 < 相似度 < 0.9: 线性插值 (0.6, 0.7) 到 (0.9, 1.0)
    """
    if similarity <= 0.4:
        return 0.0
    elif similarity >= 0.9:
        return 1.0
    elif 0.4 < similarity <= 0.6:
        # p = 3.5 * s - 1.4
        probability = 3.5 * similarity - 1.4
        return max(0.0, probability)
    else:  # 0.6 < similarity < 0.9
        # p = s + 0.1
        probability = similarity + 0.1
        return min(1.0, max(0.0, probability))


class SubMind:
    def __init__(self, subheartflow_id: str, chat_state: ChatStateInfo, observations: ChattingObservation):
        self.last_active_time = None
        self.subheartflow_id = subheartflow_id

        self.llm_model = LLMRequest(
            model=global_config.llm_sub_heartflow,
            temperature=global_config.llm_sub_heartflow["temp"],
            max_tokens=800,
            request_type="sub_heart_flow",
        )

        self.chat_state = chat_state
        self.observations = observations

        self.current_mind = ""
        self.past_mind = []
        self.structured_info = []
        self.structured_info_str = ""
        
        name = chat_manager.get_stream_name(self.subheartflow_id)
        self.log_prefix = f"[{name}] "
        self._update_structured_info_str()

    def _update_structured_info_str(self):
        """根据 structured_info 更新 structured_info_str"""
        if not self.structured_info:
            self.structured_info_str = ""
            return

        lines = ["【信息】"]
        for item in self.structured_info:
            # 简化展示，突出内容和类型，包含TTL供调试
            type_str = item.get("type", "未知类型")
            content_str = item.get("content", "")

            if type_str == "info":
                lines.append(f"刚刚: {content_str}")
            elif type_str == "memory":
                lines.append(f"{content_str}")
            elif type_str == "comparison_result":
                lines.append(f"数字大小比较结果: {content_str}")
            elif type_str == "time_info":
                lines.append(f"{content_str}")
            elif type_str == "lpmm_knowledge":
                lines.append(f"你知道：{content_str}")
            else:
                lines.append(f"{type_str}的信息: {content_str}")

        self.structured_info_str = "\n".join(lines)
        logger.debug(f"{self.log_prefix} 更新 structured_info_str: \n{self.structured_info_str}")

    async def do_thinking_before_reply(self, history_cycle: list[CycleInfo] = None, parallel_mode: bool = True, no_tools: bool = True, return_prompt: bool = False, cycle_info: CycleInfo = None):
        """
        在回复前进行思考，生成内心想法并收集工具调用结果
        
        参数:
            history_cycle: 历史循环信息
            parallel_mode: 是否在并行模式下执行，默认为True
            no_tools: 是否禁用工具调用，默认为True
            return_prompt: 是否返回prompt，默认为False
            cycle_info: 循环信息对象，可用于记录详细执行信息

        返回:
            如果return_prompt为False:
                tuple: (current_mind, past_mind) 当前想法和过去的想法列表
            如果return_prompt为True:
                tuple: (current_mind, past_mind, prompt) 当前想法、过去的想法列表和使用的prompt
        """
        # 更新活跃时间
        self.last_active_time = time.time()

        # ---------- 0. 更新和清理 structured_info ----------
        if self.structured_info:
            updated_info = []
            for item in self.structured_info:
                item["ttl"] -= 1
                if item["ttl"] > 0:
                    updated_info.append(item)
                else:
                    logger.debug(f"{self.log_prefix} 移除过期的 structured_info 项: {item['id']}")
            self.structured_info = updated_info
            self._update_structured_info_str()
        logger.debug(
            f"{self.log_prefix} 当前完整的 structured_info: {safe_json_dumps(self.structured_info, ensure_ascii=False)}"
        )

        # ---------- 1. 准备基础数据 ----------
        # 获取现有想法和情绪状态
        previous_mind = self.current_mind if self.current_mind else ""
        mood_info = self.chat_state.mood

        # 获取观察对象
        observation: ChattingObservation = self.observations[0] if self.observations else None
        if not observation or not hasattr(observation, "is_group_chat"):  # Ensure it's ChattingObservation or similar
            logger.error(f"{self.log_prefix} 无法获取有效的观察对象或缺少聊天类型信息")
            self.update_current_mind("(观察出错了...)")
            return self.current_mind, self.past_mind

        is_group_chat = observation.is_group_chat

        chat_target_info = observation.chat_target_info
        chat_target_name = "对方"  # Default for private
        if not is_group_chat and chat_target_info:
            chat_target_name = (
                chat_target_info.get("person_name") or chat_target_info.get("user_nickname") or chat_target_name
            )

        # 获取观察内容
        chat_observe_info = observation.get_observe_info()
        person_list = observation.person_list

        # ---------- 2. 获取记忆 ----------
        try:
            # 从聊天内容中提取关键词
            chat_words = set(jieba.cut(chat_observe_info))
            # 过滤掉停用词和单字词
            keywords = [word for word in chat_words if len(word) > 1]
            # 去重并限制数量
            keywords = list(set(keywords))[:5]

            logger.debug(f"{self.log_prefix} 提取的关键词: {keywords}")
            # 检查已有记忆，过滤掉已存在的主题
            existing_topics = set()
            for item in self.structured_info:
                if item["type"] == "memory":
                    existing_topics.add(item["id"])

            # 过滤掉已存在的主题
            filtered_keywords = [k for k in keywords if k not in existing_topics]

            if not filtered_keywords:
                logger.debug(f"{self.log_prefix} 所有关键词对应的记忆都已存在，跳过记忆提取")
            else:
                # 调用记忆系统获取相关记忆
                related_memory = await HippocampusManager.get_instance().get_memory_from_topic(
                    valid_keywords=filtered_keywords, max_memory_num=3, max_memory_length=2, max_depth=3
                )

                logger.debug(f"{self.log_prefix} 获取到的记忆: {related_memory}")

                if related_memory:
                    for topic, memory in related_memory:
                        new_item = {"type": "memory", "id": topic, "content": memory, "ttl": 3}
                        self.structured_info.append(new_item)
                        logger.debug(f"{self.log_prefix} 添加新记忆: {topic} - {memory}")
                else:
                    logger.debug(f"{self.log_prefix} 没有找到相关记忆")

        except Exception as e:
            logger.error(f"{self.log_prefix} 获取记忆时出错: {e}")
            logger.error(traceback.format_exc())

        # ---------- 3. 准备个性化数据 ----------
        # 获取个性化信息
        individuality = Individuality.get_instance()

        relation_prompt = ""
        for person in person_list:
            relation_prompt += await relationship_manager.build_relationship_info(person, is_id=True)

        # 构建个性部分
        prompt_personality = individuality.get_prompt(x_person=2, level=2)

        # 获取当前时间
        time_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        # ---------- 4. 构建思考指导部分 ----------
        # 创建本地随机数生成器，基于分钟数作为种子
        local_random = random.Random()
        current_minute = int(time.strftime("%M"))
        local_random.seed(current_minute)

        # 思考指导选项和权重
        hf_options = [
            ("可以参考之前的想法，在原来想法的基础上继续思考", 0.2),
            ("可以参考之前的想法，在原来的想法上尝试新的话题", 0.4),
            ("不要太深入", 0.2),
            ("进行深入思考", 0.2),
        ]

        # 准备循环信息块 (分析最近的活动循环)
        recent_active_cycles = []
        for cycle in reversed(history_cycle):
            # 只关心实际执行了动作的循环
            if cycle.action_taken:
                recent_active_cycles.append(cycle)
                # 最多找最近的3个活动循环
                if len(recent_active_cycles) == 3:
                    break

        cycle_info_block = ""
        consecutive_text_replies = 0
        responses_for_prompt = []

        # 检查这最近的活动循环中有多少是连续的文本回复 (从最近的开始看)
        for cycle in recent_active_cycles:
            if cycle.action_type == "text_reply":
                consecutive_text_replies += 1
                # 获取回复内容，如果不存在则返回'[空回复]'
                response_text = cycle.response_info.get("response_text", [])
                # 使用简单的 join 来格式化回复内容列表
                formatted_response = "[空回复]" if not response_text else " ".join(response_text)
                responses_for_prompt.append(formatted_response)
            else:
                # 一旦遇到非文本回复，连续性中断
                break

        # 根据连续文本回复的数量构建提示信息
        # 注意: responses_for_prompt 列表是从最近到最远排序的
        if consecutive_text_replies >= 3:  # 如果最近的三个活动都是文本回复
            cycle_info_block = f'你已经连续回复了三条消息（最近: "{responses_for_prompt[0]}"，第二近: "{responses_for_prompt[1]}"，第三近: "{responses_for_prompt[2]}"）。你回复的有点多了，请注意'
        elif consecutive_text_replies == 2:  # 如果最近的两个活动是文本回复
            cycle_info_block = f'你已经连续回复了两条消息（最近: "{responses_for_prompt[0]}"，第二近: "{responses_for_prompt[1]}"），请注意'
        elif consecutive_text_replies == 1:  # 如果最近的一个活动是文本回复
            cycle_info_block = f'你刚刚已经回复一条消息（内容: "{responses_for_prompt[0]}"）'

        # 包装提示块，增加可读性，即使没有连续回复也给个标记
        if cycle_info_block:
            cycle_info_block = f"\n【近期回复历史】\n{cycle_info_block}\n"
        else:
            # 如果最近的活动循环不是文本回复，或者没有活动循环
            cycle_info_block = "\n【近期回复历史】\n(最近没有连续文本回复)\n"

        # 加权随机选择思考指导
        hf_do_next = local_random.choices(
            [option[0] for option in hf_options], weights=[option[1] for option in hf_options], k=1
        )[0]

        # ---------- 5. 构建最终提示词 ----------
        # --- 根据聊天类型选择模板 ---
        logger.debug(f"is_group_chat: {is_group_chat}")
        
        template_name = "sub_heartflow_prompt_before" if is_group_chat else "sub_heartflow_prompt_private_before"
        logger.debug(f"{self.log_prefix} 使用{'群聊' if is_group_chat else '私聊'}思考模板")
                
        prompt = (await global_prompt_manager.get_prompt_async(template_name)).format(
            extra_info=self.structured_info_str,
            prompt_personality=prompt_personality,
            relation_prompt=relation_prompt,
            bot_name=individuality.name,
            time_now=time_now,
            chat_observe_info=chat_observe_info,
            mood_info=mood_info,
            hf_do_next=hf_do_next,
            last_mind = previous_mind,
            cycle_info_block=cycle_info_block,
            chat_target_name=chat_target_name,
        )

        # 在构建完提示词后，生成最终的prompt字符串
        final_prompt = prompt
        
        # ---------- 6. 调用LLM ----------
        # 如果指定了cycle_info，记录structured_info和prompt
        if cycle_info:
            cycle_info.set_submind_info(
                prompt=final_prompt,
                structured_info=self.structured_info_str
            )

        content = ""  # 初始化内容变量

        try:
            # 调用LLM生成响应
            response = await self.llm_model.generate_response_async(
                prompt=final_prompt
            )
            
            # 直接使用LLM返回的文本响应作为 content
            content = response if response else ""

        except Exception as e:
            # 处理总体异常
            logger.error(f"{self.log_prefix} 执行LLM请求或处理响应时出错: {e}")
            logger.error(traceback.format_exc())
            content = "思考过程中出现错误"

        # 记录初步思考结果
        logger.debug(f"{self.log_prefix} 初步心流思考结果: {content}\nprompt: {final_prompt}\n")

        # 处理空响应情况
        if not content:
            content = "(不知道该想些什么...)"
            logger.warning(f"{self.log_prefix} LLM返回空结果，思考失败。")

        # ---------- 7. 应用概率性去重和修饰 ----------
        new_content = content  # 保存 LLM 直接输出的结果
        try:
            similarity = calculate_similarity(previous_mind, new_content)
            replacement_prob = calculate_replacement_probability(similarity)
            logger.debug(f"{self.log_prefix} 新旧想法相似度: {similarity:.2f}, 替换概率: {replacement_prob:.2f}")

            # 定义词语列表 (移到判断之前)
            yu_qi_ci_liebiao = ["嗯", "哦", "啊", "唉", "哈", "唔"]
            zhuan_zhe_liebiao = ["但是", "不过", "然而", "可是", "只是"]
            cheng_jie_liebiao = ["然后", "接着", "此外", "而且", "另外"]
            zhuan_jie_ci_liebiao = zhuan_zhe_liebiao + cheng_jie_liebiao

            if random.random() < replacement_prob:
                # 相似度非常高时，尝试去重或特殊处理
                if similarity == 1.0:
                    logger.debug(f"{self.log_prefix} 想法完全重复 (相似度 1.0)，执行特殊处理...")
                    # 随机截取大约一半内容
                    if len(new_content) > 1:  # 避免内容过短无法截取
                        split_point = max(
                            1, len(new_content) // 2 + random.randint(-len(new_content) // 4, len(new_content) // 4)
                        )
                        truncated_content = new_content[:split_point]
                    else:
                        truncated_content = new_content  # 如果只有一个字符或者为空，就不截取了

                    # 添加语气词和转折/承接词
                    yu_qi_ci = random.choice(yu_qi_ci_liebiao)
                    zhuan_jie_ci = random.choice(zhuan_jie_ci_liebiao)
                    content = f"{yu_qi_ci}{zhuan_jie_ci}，{truncated_content}"
                    logger.debug(f"{self.log_prefix} 想法重复，特殊处理后: {content}")

                else:
                    # 相似度较高但非100%，执行标准去重逻辑
                    logger.debug(f"{self.log_prefix} 执行概率性去重 (概率: {replacement_prob:.2f})...")
                    logger.debug(f"{self.log_prefix} previous_mind类型: {type(previous_mind)}, new_content类型: {type(new_content)}")
                    
                    matcher = difflib.SequenceMatcher(None, previous_mind, new_content)
                    logger.debug(f"{self.log_prefix} matcher类型: {type(matcher)}")
                    
                    deduplicated_parts = []
                    last_match_end_in_b = 0
                    
                    # 获取并记录所有匹配块
                    matching_blocks = matcher.get_matching_blocks()
                    logger.debug(f"{self.log_prefix} 匹配块数量: {len(matching_blocks)}")
                    logger.debug(f"{self.log_prefix} 匹配块示例(前3个): {matching_blocks[:3] if len(matching_blocks) > 3 else matching_blocks}")
                    
                    # get_matching_blocks()返回形如[(i, j, n), ...]的列表，其中i是a中的索引，j是b中的索引，n是匹配的长度
                    for idx, match in enumerate(matching_blocks):
                        if not isinstance(match, tuple):
                            logger.error(f"{self.log_prefix} 匹配块 {idx} 不是元组类型，而是 {type(match)}: {match}")
                            continue
                            
                        try:
                            _i, j, n = match  # 解包元组为三个变量
                            logger.debug(f"{self.log_prefix} 匹配块 {idx}: i={_i}, j={j}, n={n}")
                            
                            if last_match_end_in_b < j:
                                # 确保添加的是字符串，而不是元组
                                try:
                                    non_matching_part = new_content[last_match_end_in_b:j]
                                    logger.debug(f"{self.log_prefix} 添加非匹配部分: '{non_matching_part}', 类型: {type(non_matching_part)}")
                                    if not isinstance(non_matching_part, str):
                                        logger.warning(f"{self.log_prefix} 非匹配部分不是字符串类型: {type(non_matching_part)}")
                                        non_matching_part = str(non_matching_part)
                                    deduplicated_parts.append(non_matching_part)
                                except Exception as e:
                                    logger.error(f"{self.log_prefix} 处理非匹配部分时出错: {e}")
                                    logger.error(traceback.format_exc())
                            last_match_end_in_b = j + n
                        except Exception as e:
                            logger.error(f"{self.log_prefix} 处理匹配块时出错: {e}")
                            logger.error(traceback.format_exc())
                    
                    logger.debug(f"{self.log_prefix} 去重前部分列表: {deduplicated_parts}")
                    logger.debug(f"{self.log_prefix} 列表元素类型: {[type(part) for part in deduplicated_parts]}")
                    
                    # 确保所有元素都是字符串
                    deduplicated_parts = [str(part) for part in deduplicated_parts]
                    
                    # 防止列表为空
                    if not deduplicated_parts:
                        logger.warning(f"{self.log_prefix} 去重后列表为空，添加空字符串")
                        deduplicated_parts = [""]
                        
                    logger.debug(f"{self.log_prefix} 处理后的部分列表: {deduplicated_parts}")
                    
                    try:
                        deduplicated_content = "".join(deduplicated_parts).strip()
                        logger.debug(f"{self.log_prefix} 拼接后的去重内容: '{deduplicated_content}'")
                    except Exception as e:
                        logger.error(f"{self.log_prefix} 拼接去重内容时出错: {e}")
                        logger.error(traceback.format_exc())
                        deduplicated_content = ""
                    
                    if deduplicated_content:
                        # 根据概率决定是否添加词语
                        prefix_str = ""
                        if random.random() < 0.3:  # 30% 概率添加语气词
                            prefix_str += random.choice(yu_qi_ci_liebiao)
                        if random.random() < 0.7:  # 70% 概率添加转折/承接词
                            prefix_str += random.choice(zhuan_jie_ci_liebiao)

                        # 组合最终结果
                        if prefix_str:
                            content = f"{prefix_str}，{deduplicated_content}"  # 更新 content
                            logger.debug(f"{self.log_prefix} 去重并添加引导词后: {content}")
                        else:
                            content = deduplicated_content  # 更新 content
                            logger.debug(f"{self.log_prefix} 去重后 (未添加引导词): {content}")
                    else:
                        logger.warning(f"{self.log_prefix} 去重后内容为空，保留原始LLM输出: {new_content}")
                        content = new_content  # 保留原始 content
            else:
                logger.debug(f"{self.log_prefix} 未执行概率性去重 (概率: {replacement_prob:.2f})")
                # content 保持 new_content 不变

        except Exception as e:
            logger.error(f"{self.log_prefix} 应用概率性去重或特殊处理时出错: {e}")
            logger.error(traceback.format_exc())
            # 出错时保留原始 content
            content = new_content

        # ---------- 8. 更新思考状态并返回结果 ----------
        logger.info(f"{self.log_prefix} 最终心流思考结果: {content}")
        # 更新当前思考内容
        self.update_current_mind(content)

        # 在原始代码的return语句前，记录结果并根据return_prompt决定返回值
        if cycle_info:
            cycle_info.set_submind_info(
                result=content
            )
            
        if return_prompt:
            return content, self.past_mind, final_prompt
        else:
            return content, self.past_mind

    def update_current_mind(self, response):
        if self.current_mind:  # 只有当 current_mind 非空时才添加到 past_mind
            self.past_mind.append(self.current_mind)
            # 可以考虑限制 past_mind 的大小，例如:
            # max_past_mind_size = 10
            # if len(self.past_mind) > max_past_mind_size:
            #     self.past_mind.pop(0) # 移除最旧的

        self.current_mind = response


init_prompt()
