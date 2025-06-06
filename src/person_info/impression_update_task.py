from src.manager.async_task_manager import AsyncTask
from src.common.logger_manager import get_logger
from src.person_info.relationship_manager import relationship_manager
from src.chat.utils.chat_message_builder import get_raw_msg_by_timestamp
from src.config.config import global_config
from src.person_info.person_info import person_info_manager
from src.chat.message_receive.chat_stream import chat_manager
import time
import random
from collections import defaultdict

logger = get_logger("relation")


class ImpressionUpdateTask(AsyncTask):
    def __init__(self):
        super().__init__(
            task_name="impression_update",
            wait_before_start=5,
            run_interval=global_config.relationship.build_relationship_interval,
        )

    async def run(self):
        try:
            # 获取最近的消息
            current_time = int(time.time())
            start_time = current_time - 360000  # 1小时前
            
            # 获取所有消息
            messages = get_raw_msg_by_timestamp(timestamp_start=start_time, timestamp_end=current_time, limit=200)
            
            if not messages:
                logger.info("没有找到需要处理的消息")
                return

            logger.info(f"获取到 {len(messages)} 条消息")

            # 按chat_id分组消息
            chat_messages = defaultdict(list)
            for msg in messages:
                chat_messages[msg["chat_id"]].append(msg)

            logger.info(f"消息按聊天分组: {len(chat_messages)} 个聊天组")

            # 处理每个聊天组
            for chat_id, msgs in chat_messages.items():
                # 获取chat_stream
                chat_stream = chat_manager.get_stream(chat_id)
                if not chat_stream:
                    logger.warning(f"未找到聊天组 {chat_id} 的chat_stream，跳过处理")
                    continue

                # 找到bot的消息
                bot_messages = [msg for msg in msgs if msg["user_nickname"] == global_config.bot.nickname]
                
                if not bot_messages:
                    logger.info(f"聊天组 {chat_id} 没有bot消息，跳过处理")
                    continue

                # 按时间排序所有消息
                sorted_messages = sorted(msgs, key=lambda x: x["time"])
                
                # 找到第一条和最后一条bot消息
                first_bot_msg = bot_messages[0]
                last_bot_msg = bot_messages[-1]
                
                # 获取第一条bot消息前15条消息
                first_bot_index = sorted_messages.index(first_bot_msg)
                start_index = max(0, first_bot_index - 15)
                
                # 获取最后一条bot消息后15条消息
                last_bot_index = sorted_messages.index(last_bot_msg)
                end_index = min(len(sorted_messages), last_bot_index + 16)
                
                # 获取相关消息
                relevant_messages = sorted_messages[start_index:end_index]

                # 统计用户发言权重
                user_weights = defaultdict(lambda: {"weight": 0, "messages": []})

                # 计算权重
                for bot_msg in bot_messages:
                    bot_time = bot_msg["time"]
                    context_messages = [msg for msg in relevant_messages if abs(msg["time"] - bot_time) <= 600]  # 前后10分钟
                    logger.debug(f"Bot消息 {bot_time} 的上下文消息数: {len(context_messages)}")

                    for msg in context_messages:
                        if msg["user_nickname"] == global_config.bot.nickname:
                            continue

                        person_id = person_info_manager.get_person_id(msg["chat_info_platform"], msg["user_id"])
                        if not person_id:
                            logger.warning(f"未找到用户 {msg['user_nickname']} 的person_id")
                            continue

                        # 在bot消息附近的发言权重加倍
                        if abs(msg["time"] - bot_time) <= 120:  # 前后2分钟
                            user_weights[person_id]["weight"] += 2
                            logger.debug(f"用户 {msg['user_nickname']} 在bot消息附近发言，权重+2")
                        else:
                            user_weights[person_id]["weight"] += 1
                            logger.debug(f"用户 {msg['user_nickname']} 发言，权重+1")

                        user_weights[person_id]["messages"].append(msg)

                # 按权重排序
                sorted_users = sorted(user_weights.items(), key=lambda x: x[1]["weight"], reverse=True)

                logger.debug(
                    f"用户权重排序: {[(msg[1]['messages'][0]['user_nickname'], msg[1]['weight']) for msg in sorted_users]}"
                )

                # 选择最多5个用户
                selected_users = []
                if len(sorted_users) > 5:
                    # 使用权重作为概率进行随机选择，确保不重复
                    weights = [user[1]["weight"] for user in sorted_users]
                    total_weight = sum(weights)
                    # 计算每个用户的概率
                    probabilities = [w/total_weight for w in weights]
                    # 使用累积概率进行选择
                    selected_indices = []
                    remaining_indices = list(range(len(sorted_users)))
                    for _ in range(5):
                        if not remaining_indices:
                            break
                        # 计算剩余索引的累积概率
                        remaining_probs = [probabilities[i] for i in remaining_indices]
                        # 归一化概率
                        remaining_probs = [p/sum(remaining_probs) for p in remaining_probs]
                        # 选择索引
                        chosen_idx = random.choices(remaining_indices, weights=remaining_probs, k=1)[0]
                        selected_indices.append(chosen_idx)
                        remaining_indices.remove(chosen_idx)
                    
                    selected_users = [sorted_users[i] for i in selected_indices]
                    logger.info(
                        f"开始进一步了解这些用户: {[msg[1]['messages'][0]['user_nickname'] for msg in selected_users]}"
                    )
                else:
                    selected_users = sorted_users
                    logger.info(
                        f"开始进一步了解用户: {[msg[1]['messages'][0]['user_nickname'] for msg in selected_users]}"
                    )

                # 更新选中用户的印象
                for person_id, data in selected_users:
                    user_nickname = data["messages"][0]["user_nickname"]
                    platform = data["messages"][0]["chat_info_platform"]
                    user_id = data["messages"][0]["user_id"]
                    cardname = data["messages"][0]["user_cardname"]
                    
                    is_known = await relationship_manager.is_known_some_one(platform, user_id)

                    if not is_known:
                        logger.info(f"首次认识用户: {user_nickname}")
                        await relationship_manager.first_knowing_some_one(platform, user_id, user_nickname, cardname)
                    
                    
                    logger.info(f"开始更新用户 {user_nickname} 的印象")
                    await relationship_manager.update_person_impression(
                        person_id=person_id,
                        timestamp=last_bot_msg["time"],
                        bot_engaged_messages=relevant_messages
                    )

            logger.debug("印象更新任务执行完成")

        except Exception as e:
            logger.exception(f"更新印象任务失败: {str(e)}")


# 创建任务实例
impression_update_task = ImpressionUpdateTask()
