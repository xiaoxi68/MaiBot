import asyncio
import traceback
from typing import Optional, Coroutine, Callable, Any, List

from src.common.logger_manager import get_logger

# Need manager types for dependency injection
from src.heart_flow.mai_state_manager import MaiStateManager, MaiStateInfo
from src.heart_flow.subheartflow_manager import SubHeartflowManager
from src.heart_flow.interest_logger import InterestLogger


logger = get_logger("background_tasks")


# 兴趣评估间隔
INTEREST_EVAL_INTERVAL_SECONDS = 5
# 专注水群检查间隔
FOCUS_CHAT_CHECK_INTERVAL_SECONDS = 60
# 日志记录间隔
LOG_INTERVAL_SECONDS = 3


async def _run_periodic_loop(
    task_name: str, interval: int, task_func: Callable[..., Coroutine[Any, Any, None]], **kwargs
):
    """周期性任务主循环"""
    while True:
        start_time = asyncio.get_event_loop().time()
        # logger.debug(f"开始执行后台任务: {task_name}")

        try:
            await task_func(**kwargs)  # 执行实际任务
        except asyncio.CancelledError:
            logger.info(f"任务 {task_name} 已取消")
            break
        except Exception as e:
            logger.error(f"任务 {task_name} 执行出错: {e}")
            logger.error(traceback.format_exc())

        # 计算并执行间隔等待
        elapsed = asyncio.get_event_loop().time() - start_time
        sleep_time = max(0, interval - elapsed)
        # if sleep_time < 0.1:  # 任务超时处理, DEBUG 时可能干扰断点
        #     logger.warning(f"任务 {task_name} 超时执行 ({elapsed:.2f}s > {interval}s)")
        await asyncio.sleep(sleep_time)

    logger.debug(f"任务循环结束: {task_name}")  # 调整日志信息


class BackgroundTaskManager:
    """管理 Heartflow 的后台周期性任务。"""

    def __init__(
        self,
        mai_state_info: MaiStateInfo,  # Needs current state info
        mai_state_manager: MaiStateManager,
        subheartflow_manager: SubHeartflowManager,
        interest_logger: InterestLogger,
    ):
        self.mai_state_info = mai_state_info
        self.mai_state_manager = mai_state_manager
        self.subheartflow_manager = subheartflow_manager
        self.interest_logger = interest_logger

        # Task references
        self._logging_task: Optional[asyncio.Task] = None
        self._focus_chat_check_task: Optional[asyncio.Task] = None
        self._into_focus_task: Optional[asyncio.Task] = None
        self._tasks: List[Optional[asyncio.Task]] = []  # Keep track of all tasks

    async def start_tasks(self):
        """启动所有后台任务

        功能说明:
        - 启动核心后台任务: 日志记录、兴趣评估和专注水群监测
        - 每个任务启动前检查是否已在运行
        - 将任务引用保存到任务列表
        """

        # 任务配置列表: (任务函数, 任务名称, 日志级别, 额外日志信息, 任务对象引用属性名)
        task_configs = [
            (
                lambda: self._run_focus_chat_check_cycle(FOCUS_CHAT_CHECK_INTERVAL_SECONDS),
                "debug",
                f"专注水群检查任务已启动 间隔:{FOCUS_CHAT_CHECK_INTERVAL_SECONDS}s",
                "_focus_chat_check_task",
            ),
            (
                self._run_logging_cycle,
                "info",
                f"日志任务已启动 间隔:{LOG_INTERVAL_SECONDS}s",
                "_logging_task",
            ),
            # 兴趣评估任务配置
            (
                self._run_into_focus_cycle,
                "debug",  # 设为debug，避免过多日志
                f"专注评估任务已启动 间隔:{INTEREST_EVAL_INTERVAL_SECONDS}s",
                "_into_focus_task",
            ),
        ]

        # 统一启动所有任务
        for task_func, log_level, log_msg, task_attr_name in task_configs:
            # 检查任务变量是否存在且未完成
            current_task_var = getattr(self, task_attr_name)
            if current_task_var is None or current_task_var.done():
                new_task = asyncio.create_task(task_func())
                setattr(self, task_attr_name, new_task)  # 更新任务变量
                if new_task not in self._tasks:  # 避免重复添加
                    self._tasks.append(new_task)

                # 根据配置记录不同级别的日志
                getattr(logger, log_level)(log_msg)
            else:
                logger.warning(f"{task_attr_name}任务已在运行")

    async def stop_tasks(self):
        """停止所有后台任务。

        该方法会:
        1. 遍历所有后台任务并取消未完成的任务
        2. 等待所有取消操作完成
        3. 清空任务列表
        """
        logger.info("正在停止所有后台任务...")
        cancelled_count = 0

        # 第一步：取消所有运行中的任务
        for task in self._tasks:
            if task and not task.done():
                task.cancel()  # 发送取消请求
                cancelled_count += 1

        # 第二步：处理取消结果
        if cancelled_count > 0:
            logger.debug(f"正在等待{cancelled_count}个任务完成取消...")
            # 使用gather等待所有取消操作完成，忽略异常
            await asyncio.gather(*[t for t in self._tasks if t and t.cancelled()], return_exceptions=True)
            logger.info(f"成功取消{cancelled_count}个后台任务")
        else:
            logger.info("没有需要取消的后台任务")

        # 第三步：清空任务列表
        self._tasks = []  # 重置任务列表

    async def _focus_chat_check_work(self):
        """检查FOCUSED状态的子心流是否需要转回CHAT状态"""
        logger.debug("[专注水群检查] 开始检查专注水群状态的子心流...")
        await self.subheartflow_manager.sbhf_focus_into_chat()

    async def _perform_logging_work(self):
        """执行一轮状态日志记录。"""
        await self.interest_logger.log_all_states()

    async def _perform_into_focus_work(self):
        """执行一轮子心流兴趣评估与提升检查。"""
        # 直接调用 subheartflow_manager 的方法进行CHAT到FOCUSED的转换
        await self.subheartflow_manager.sbhf_chat_into_focus()

    # --- Specific Task Runners --- #
    async def _run_focus_chat_check_cycle(self, interval: int):
        await _run_periodic_loop(
            task_name="Focus Chat Check", interval=interval, task_func=self._focus_chat_check_work
        )

    async def _run_logging_cycle(self):
        await _run_periodic_loop(
            task_name="State Logging", interval=LOG_INTERVAL_SECONDS, task_func=self._perform_logging_work
        )

    async def _run_into_focus_cycle(self):
        await _run_periodic_loop(
            task_name="Into Focus",
            interval=INTEREST_EVAL_INTERVAL_SECONDS,
            task_func=self._perform_into_focus_work,
        )
