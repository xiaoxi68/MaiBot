from datetime import datetime, timedelta
from common.logger_manager import get_logger
from manager.async_task_manager import AsyncTask
from model_manager.chat_user import ChatUserManager
from model_manager.message import MessageManager


logger = get_logger("person_msg_interval")

# 此处为个体消息间隔推断任务的实现
# 要取得消息间隔，请在业务逻辑中直接调用ChatUserManager获取ChatUserDTO


class PersonMsgIntervalInferTask(AsyncTask):
    """个体消息间隔推断任务

    该任务用于推断个体在聊天流中的消息发送间隔。
    """

    def __init__(self):
        super().__init__(
            name="Person Msg Interval Infer Task",
            wait_before_start=600,  # 首次执行前等待十分钟
            run_interval=43200,  # 每天执行两次
        )

    async def run(self):
        """执行推断任务"""
        logger.info("正在执行个体消息间隔推断任务...")

        all_chat_user = ChatUserManager.get_all_users()

        for chat_user in all_chat_user:
            user_id = chat_user.id
            messages = MessageManager.get_user_messages(
                user_id=chat_user.id, start_time=datetime.now() - timedelta(days=1)
            )

            # 计算消息间隔
            intervals = []
            for i in range(1, len(messages)):
                interval = (messages[i].message_time - messages[i - 1].message_time).total_seconds
                # 过滤掉小于0.2秒和大于8秒的间隔
                if 0.2 < interval < 8:
                    intervals.append(interval)

            # 如果有效间隔小于40个，则跳过推断
            if not intervals or len(intervals) < 40:
                logger.debug(f"用户 {user_id} 没有足够多的有效消息记录，跳过推断。")
                continue

            # 排序，去掉头尾
            intervals.sort()
            intervals = intervals[5:-5]  # 去掉前5个和后5个极端值

            mean_interval = sum(intervals) / len(intervals)

            chat_user.msg_interval = mean_interval
            chat_user = ChatUserManager.update_chat_user(chat_user)
            logger.info(f"用户 {user_id} 的消息间隔已更新为 {mean_interval:.2f} 秒。")

        logger.info("个体消息间隔推断任务执行完成。")
