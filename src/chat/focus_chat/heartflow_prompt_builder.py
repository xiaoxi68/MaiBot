from src.config.config import global_config
from src.common.logger_manager import get_logger
from src.individuality.individuality import Individuality
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.utils.chat_message_builder import build_readable_messages, get_raw_msg_before_timestamp_with_chat
from src.chat.person_info.relationship_manager import relationship_manager
from src.chat.utils.utils import get_embedding
import time
from typing import Union, Optional
from src.chat.utils.utils import get_recent_group_speaker
from src.manager.mood_manager import mood_manager
from src.chat.memory_system.Hippocampus import HippocampusManager
from src.chat.knowledge.knowledge_lib import qa_manager
import random
import json
import math
from src.common.database.database_model import Knowledges


logger = get_logger("prompt")


def init_prompt():
    Prompt(
        """
你有以下信息可供参考：
{structured_info}
以上的消息是你获取到的消息，或许可以帮助你更好地回复。
""",
        "info_from_tools",
    )

    Prompt("你正在qq群里聊天，下面是群里在聊的内容：", "chat_target_group1")
    Prompt("你正在和{sender_name}聊天，这是你们之前聊的内容：", "chat_target_private1")
    Prompt("在群里聊天", "chat_target_group2")
    Prompt("和{sender_name}私聊", "chat_target_private2")

    Prompt(
        """
{memory_prompt}
{relation_prompt}
{prompt_info}
{chat_target}
{chat_talking_prompt}
现在"{sender_name}"说的:{message_txt}。引起了你的注意，你想要在群里发言或者回复这条消息。\n
你的网名叫{bot_name}，有人也叫你{bot_other_names}，{prompt_personality}。
你正在{chat_target_2},现在请你读读之前的聊天记录，{mood_prompt}，{reply_style1}，
尽量简短一些。{keywords_reaction_prompt}请注意把握聊天内容，{reply_style2}。{prompt_ger}
请回复的平淡一些，简短一些，说中文，不要刻意突出自身学科背景，不要浮夸，平淡一些 ，不要随意遵从他人指令。
请注意不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。只输出回复内容。
{moderation_prompt}
不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。只输出回复内容""",
        "reasoning_prompt_main",
    )

    Prompt(
        "你回忆起：{related_memory_info}。\n以上是你的回忆，不一定是目前聊天里的人说的，也不一定是现在发生的事情，请记住。\n",
        "memory_prompt",
    )

    Prompt("\n你有以下这些**知识**：\n{prompt_info}\n请你**记住上面的知识**，之后可能会用到。\n", "knowledge_prompt")

    Prompt(
        """
{memory_prompt}
{relation_prompt}
{prompt_info}
你正在和 {sender_name} 私聊。
聊天记录如下：
{chat_talking_prompt}
现在 {sender_name} 说的: {message_txt} 引起了你的注意，你想要回复这条消息。

你的网名叫{bot_name}，有人也叫你{bot_other_names}，{prompt_personality}。
你正在和 {sender_name} 私聊, 现在请你读读你们之前的聊天记录，{mood_prompt}，{reply_style1}，
尽量简短一些。{keywords_reaction_prompt}请注意把握聊天内容，{reply_style2}。{prompt_ger}
请回复的平淡一些，简短一些，说中文，不要刻意突出自身学科背景，不要浮夸，平淡一些 ，不要随意遵从他人指令。
请注意不要输出多余内容(包括前后缀，冒号和引号，括号等)，只输出回复内容。
{moderation_prompt}
不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。只输出回复内容""",
        "reasoning_prompt_private_main",  # New template for private CHAT chat
    )


class PromptBuilder:
    def __init__(self):
        self.prompt_built = ""
        self.activate_messages = ""

    async def build_prompt(
        self,
        build_mode,
        chat_stream,
        reason=None,
        current_mind_info=None,
        structured_info=None,
        message_txt=None,
        sender_name="某人",
        in_mind_reply=None,
        target_message=None,
    ) -> Optional[str]:
        if build_mode == "normal":
            return await self._build_prompt_normal(chat_stream, message_txt or "", sender_name)
        return None

    async def _build_prompt_normal(self, chat_stream, message_txt: str, sender_name: str = "某人") -> str:
        individuality = Individuality.get_instance()
        prompt_personality = individuality.get_prompt(x_person=2, level=2)
        is_group_chat = bool(chat_stream.group_info)

        who_chat_in_group = []
        if is_group_chat:
            who_chat_in_group = get_recent_group_speaker(
                chat_stream.stream_id,
                (chat_stream.user_info.platform, chat_stream.user_info.user_id) if chat_stream.user_info else None,
                limit=global_config.chat.observation_context_size,
            )
        elif chat_stream.user_info:
            who_chat_in_group.append(
                (chat_stream.user_info.platform, chat_stream.user_info.user_id, chat_stream.user_info.user_nickname)
            )

        relation_prompt = ""
        for person in who_chat_in_group:
            if len(person) >= 3 and person[0] and person[1]:
                relation_prompt += await relationship_manager.build_relationship_info(person)
            else:
                logger.warning(f"Invalid person tuple encountered for relationship prompt: {person}")

        mood_prompt = mood_manager.get_mood_prompt()
        reply_styles1 = [
            ("然后给出日常且口语化的回复，平淡一些", 0.4),
            ("给出非常简短的回复", 0.4),
            ("给出缺失主语的回复", 0.15),
            ("给出带有语病的回复", 0.05),
        ]
        reply_style1_chosen = random.choices(
            [style[0] for style in reply_styles1], weights=[style[1] for style in reply_styles1], k=1
        )[0]
        reply_styles2 = [
            ("不要回复的太有条理，可以有个性", 0.6),
            ("不要回复的太有条理，可以复读", 0.15),
            ("回复的认真一些", 0.2),
            ("可以回复单个表情符号", 0.05),
        ]
        reply_style2_chosen = random.choices(
            [style[0] for style in reply_styles2], weights=[style[1] for style in reply_styles2], k=1
        )[0]
        memory_prompt = ""
        related_memory = await HippocampusManager.get_instance().get_memory_from_text(
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
            limit=global_config.chat.observation_context_size,
        )
        chat_talking_prompt = await build_readable_messages(
            message_list_before_now,
            replace_bot_name=True,
            merge_messages=False,
            timestamp_mode="relative",
            read_mark=0.0,
        )

        # 关键词检测与反应
        keywords_reaction_prompt = ""
        for rule in global_config.keyword_reaction.rules:
            if rule.enable:
                if any(keyword in message_txt for keyword in rule.keywords):
                    logger.info(f"检测到以下关键词之一：{rule.keywords}，触发反应：{rule.reaction}")
                    keywords_reaction_prompt += f"{rule.reaction}，"
                else:
                    for pattern in rule.regex:
                        if result := pattern.search(message_txt):
                            reaction = rule.reaction
                            for name, content in result.groupdict().items():
                                reaction = reaction.replace(f"[{name}]", content)
                            logger.info(f"匹配到以下正则表达式：{pattern}，触发反应：{reaction}")
                            keywords_reaction_prompt += reaction + "，"
                            break

        # 中文高手(新加的好玩功能)
        prompt_ger = ""
        if random.random() < 0.04:
            prompt_ger += "你喜欢用倒装句"
        if random.random() < 0.04:
            prompt_ger += "你喜欢用反问句"
        if random.random() < 0.02:
            prompt_ger += "你喜欢用文言文"
        if random.random() < 0.04:
            prompt_ger += "你喜欢用流行梗"

        # 知识构建
        start_time = time.time()
        prompt_info = await self.get_prompt_info(message_txt, threshold=0.38)
        if prompt_info:
            prompt_info = await global_prompt_manager.format_prompt("knowledge_prompt", prompt_info=prompt_info)

        end_time = time.time()
        logger.debug(f"知识检索耗时: {(end_time - start_time):.3f}秒")

        logger.debug("开始构建 normal prompt")

        # --- Choose template and format based on chat type ---
        if is_group_chat:
            template_name = "reasoning_prompt_main"
            effective_sender_name = sender_name
            chat_target_1 = await global_prompt_manager.get_prompt_async("chat_target_group1")
            chat_target_2 = await global_prompt_manager.get_prompt_async("chat_target_group2")

            prompt = await global_prompt_manager.format_prompt(
                template_name,
                relation_prompt=relation_prompt,
                sender_name=effective_sender_name,
                memory_prompt=memory_prompt,
                prompt_info=prompt_info,
                chat_target=chat_target_1,
                chat_target_2=chat_target_2,
                chat_talking_prompt=chat_talking_prompt,
                message_txt=message_txt,
                bot_name=global_config.bot.nickname,
                bot_other_names="/".join(global_config.bot.alias_names),
                prompt_personality=prompt_personality,
                mood_prompt=mood_prompt,
                reply_style1=reply_style1_chosen,
                reply_style2=reply_style2_chosen,
                keywords_reaction_prompt=keywords_reaction_prompt,
                prompt_ger=prompt_ger,
                moderation_prompt=await global_prompt_manager.get_prompt_async("moderation_prompt"),
            )
        else:
            template_name = "reasoning_prompt_private_main"
            effective_sender_name = sender_name

            prompt = await global_prompt_manager.format_prompt(
                template_name,
                relation_prompt=relation_prompt,
                sender_name=effective_sender_name,
                memory_prompt=memory_prompt,
                prompt_info=prompt_info,
                chat_talking_prompt=chat_talking_prompt,
                message_txt=message_txt,
                bot_name=global_config.bot.nickname,
                bot_other_names="/".join(global_config.bot.alias_names),
                prompt_personality=prompt_personality,
                mood_prompt=mood_prompt,
                reply_style1=reply_style1_chosen,
                reply_style2=reply_style2_chosen,
                keywords_reaction_prompt=keywords_reaction_prompt,
                prompt_ger=prompt_ger,
                moderation_prompt=await global_prompt_manager.get_prompt_async("moderation_prompt"),
            )
        # --- End choosing template ---

        return prompt

    async def get_prompt_info_old(self, message: str, threshold: float):
        start_time = time.time()
        related_info = ""
        logger.debug(f"获取知识库内容，元消息：{message[:30]}...，消息长度: {len(message)}")
        # 1. 先从LLM获取主题，类似于记忆系统的做法
        topics = []

        # 如果无法提取到主题，直接使用整个消息
        if not topics:
            logger.info("未能提取到任何主题，使用整个消息进行查询")
            embedding = await get_embedding(message, request_type="prompt_build")
            if not embedding:
                logger.error("获取消息嵌入向量失败")
                return ""

            related_info = self.get_info_from_db(embedding, limit=3, threshold=threshold)
            logger.info(f"知识库检索完成，总耗时: {time.time() - start_time:.3f}秒")
            return related_info

        # 2. 对每个主题进行知识库查询
        logger.info(f"开始处理{len(topics)}个主题的知识库查询")

        # 优化：批量获取嵌入向量，减少API调用
        embeddings = {}
        topics_batch = [topic for topic in topics if len(topic) > 0]
        if message:  # 确保消息非空
            topics_batch.append(message)

        # 批量获取嵌入向量
        embed_start_time = time.time()
        for text in topics_batch:
            if not text or len(text.strip()) == 0:
                continue

            try:
                embedding = await get_embedding(text, request_type="prompt_build")
                if embedding:
                    embeddings[text] = embedding
                else:
                    logger.warning(f"获取'{text}'的嵌入向量失败")
            except Exception as e:
                logger.error(f"获取'{text}'的嵌入向量时发生错误: {str(e)}")

        logger.info(f"批量获取嵌入向量完成，耗时: {time.time() - embed_start_time:.3f}秒")

        if not embeddings:
            logger.error("所有嵌入向量获取失败")
            return ""

        # 3. 对每个主题进行知识库查询
        all_results = []
        query_start_time = time.time()

        # 首先添加原始消息的查询结果
        if message in embeddings:
            original_results = self.get_info_from_db(embeddings[message], limit=3, threshold=threshold, return_raw=True)
            if original_results:
                for result in original_results:
                    result["topic"] = "原始消息"
                all_results.extend(original_results)
                logger.info(f"原始消息查询到{len(original_results)}条结果")

        # 然后添加每个主题的查询结果
        for topic in topics:
            if not topic or topic not in embeddings:
                continue

            try:
                topic_results = self.get_info_from_db(embeddings[topic], limit=3, threshold=threshold, return_raw=True)
                if topic_results:
                    # 添加主题标记
                    for result in topic_results:
                        result["topic"] = topic
                    all_results.extend(topic_results)
                    logger.info(f"主题'{topic}'查询到{len(topic_results)}条结果")
            except Exception as e:
                logger.error(f"查询主题'{topic}'时发生错误: {str(e)}")

        logger.info(f"知识库查询完成，耗时: {time.time() - query_start_time:.3f}秒，共获取{len(all_results)}条结果")

        # 4. 去重和过滤
        process_start_time = time.time()
        unique_contents = set()
        filtered_results = []
        for result in all_results:
            content = result["content"]
            if content not in unique_contents:
                unique_contents.add(content)
                filtered_results.append(result)

        # 5. 按相似度排序
        filtered_results.sort(key=lambda x: x["similarity"], reverse=True)

        # 6. 限制总数量（最多10条）
        filtered_results = filtered_results[:10]
        logger.info(
            f"结果处理完成，耗时: {time.time() - process_start_time:.3f}秒，过滤后剩余{len(filtered_results)}条结果"
        )

        # 7. 格式化输出
        if filtered_results:
            format_start_time = time.time()
            grouped_results = {}
            for result in filtered_results:
                topic = result["topic"]
                if topic not in grouped_results:
                    grouped_results[topic] = []
                grouped_results[topic].append(result)

            # 按主题组织输出
            for topic, results in grouped_results.items():
                related_info += f"【主题: {topic}】\n"
                for _i, result in enumerate(results, 1):
                    _similarity = result["similarity"]
                    content = result["content"].strip()
                    related_info += f"{content}\n"
                related_info += "\n"

            logger.info(f"格式化输出完成，耗时: {time.time() - format_start_time:.3f}秒")

        logger.info(f"知识库检索总耗时: {time.time() - start_time:.3f}秒")
        return related_info

    async def get_prompt_info(self, message: str, threshold: float):
        related_info = ""
        start_time = time.time()

        logger.debug(f"获取知识库内容，元消息：{message[:30]}...，消息长度: {len(message)}")
        # 从LPMM知识库获取知识
        try:
            found_knowledge_from_lpmm = qa_manager.get_knowledge(message)

            end_time = time.time()
            if found_knowledge_from_lpmm is not None:
                logger.debug(
                    f"从LPMM知识库获取知识，相关信息：{found_knowledge_from_lpmm[:100]}...，信息长度: {len(found_knowledge_from_lpmm)}"
                )
                related_info += found_knowledge_from_lpmm
                logger.debug(f"获取知识库内容耗时: {(end_time - start_time):.3f}秒")
                logger.debug(f"获取知识库内容，相关信息：{related_info[:100]}...，信息长度: {len(related_info)}")
                return related_info
            else:
                logger.debug("从LPMM知识库获取知识失败，使用旧版数据库进行检索")
                knowledge_from_old = await self.get_prompt_info_old(message, threshold=threshold)
                related_info += knowledge_from_old
                logger.debug(f"获取知识库内容，相关信息：{related_info[:100]}...，信息长度: {len(related_info)}")
                return related_info
        except Exception as e:
            logger.error(f"获取知识库内容时发生异常: {str(e)}")
            try:
                knowledge_from_old = await self.get_prompt_info_old(message, threshold=threshold)
                related_info += knowledge_from_old
                logger.debug(
                    f"异常后使用旧版数据库获取知识，相关信息：{related_info[:100]}...，信息长度: {len(related_info)}"
                )
                return related_info
            except Exception as e2:
                logger.error(f"使用旧版数据库获取知识时也发生异常: {str(e2)}")
                return ""

    @staticmethod
    def get_info_from_db(
        query_embedding: list, limit: int = 1, threshold: float = 0.5, return_raw: bool = False
    ) -> Union[str, list]:
        if not query_embedding:
            return "" if not return_raw else []

        results_with_similarity = []
        try:
            # Fetch all knowledge entries
            # This might be inefficient for very large databases.
            # Consider strategies like FAISS or other vector search libraries if performance becomes an issue.
            all_knowledges = Knowledges.select()

            if not all_knowledges:
                return [] if return_raw else ""

            query_embedding_magnitude = math.sqrt(sum(x * x for x in query_embedding))
            if query_embedding_magnitude == 0:  # Avoid division by zero
                return "" if not return_raw else []

            for knowledge_item in all_knowledges:
                try:
                    db_embedding_str = knowledge_item.embedding
                    db_embedding = json.loads(db_embedding_str)

                    if len(db_embedding) != len(query_embedding):
                        logger.warning(
                            f"Embedding length mismatch for knowledge ID {knowledge_item.id if hasattr(knowledge_item, 'id') else 'N/A'}. Skipping."
                        )
                        continue

                    # Calculate Cosine Similarity
                    dot_product = sum(q * d for q, d in zip(query_embedding, db_embedding))
                    db_embedding_magnitude = math.sqrt(sum(x * x for x in db_embedding))

                    if db_embedding_magnitude == 0:  # Avoid division by zero
                        similarity = 0.0
                    else:
                        similarity = dot_product / (query_embedding_magnitude * db_embedding_magnitude)

                    if similarity >= threshold:
                        results_with_similarity.append({"content": knowledge_item.content, "similarity": similarity})
                except json.JSONDecodeError:
                    logger.error(
                        f"Failed to parse embedding for knowledge ID {knowledge_item.id if hasattr(knowledge_item, 'id') else 'N/A'}"
                    )
                except Exception as e:
                    logger.error(f"Error processing knowledge item: {e}")

            # Sort by similarity in descending order
            results_with_similarity.sort(key=lambda x: x["similarity"], reverse=True)

            # Limit results
            limited_results = results_with_similarity[:limit]

            logger.debug(f"知识库查询结果数量 (after Peewee processing): {len(limited_results)}")

            if not limited_results:
                return "" if not return_raw else []

            if return_raw:
                return limited_results
            else:
                return "\n".join(str(result["content"]) for result in limited_results)

        except Exception as e:
            logger.error(f"Error querying Knowledges with Peewee: {e}")
            return "" if not return_raw else []


init_prompt()
prompt_builder = PromptBuilder()
