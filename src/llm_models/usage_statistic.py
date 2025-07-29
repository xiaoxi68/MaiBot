from datetime import datetime
from enum import Enum
from typing import Tuple

from src.common.logger import get_logger
from src.config.api_ada_configs import ModelInfo
from src.common.database.database_model import LLMUsage

logger = get_logger("模型使用统计")


class ReqType(Enum):
    """
    请求类型
    """

    CHAT = "chat"  # 对话请求
    EMBEDDING = "embedding"  # 嵌入请求


class UsageCallStatus(Enum):
    """
    任务调用状态
    """

    PROCESSING = "processing"  # 处理中
    SUCCESS = "success"  # 成功
    FAILURE = "failure"  # 失败
    CANCELED = "canceled"  # 取消


class ModelUsageStatistic:
    """
    模型使用统计类 - 使用SQLite+Peewee
    """

    def __init__(self):
        """
        初始化统计类
        由于使用Peewee ORM，不需要传入数据库实例
        """
        # 确保表已经创建
        try:
            from src.common.database.database import db

            db.create_tables([LLMUsage], safe=True)
        except Exception as e:
            logger.error(f"创建LLMUsage表失败: {e}")

    @staticmethod
    def _calculate_cost(prompt_tokens: int, completion_tokens: int, model_info: ModelInfo) -> float:
        """计算API调用成本
        使用模型的pri_in和pri_out价格计算输入和输出的成本

        Args:
            prompt_tokens: 输入token数量
            completion_tokens: 输出token数量
            model_info: 模型信息

        Returns:
            float: 总成本（元）
        """
        # 使用模型的pri_in和pri_out计算成本
        input_cost = (prompt_tokens / 1000000) * model_info.price_in
        output_cost = (completion_tokens / 1000000) * model_info.price_out
        return round(input_cost + output_cost, 6)

    def create_usage(
        self,
        model_name: str,
        task_name: str = "N/A",
        request_type: ReqType = ReqType.CHAT,
        user_id: str = "system",
        endpoint: str = "/chat/completions",
    ) -> int | None:
        """
        创建模型使用情况记录

        Args:
            model_name: 模型名
            task_name: 任务名称
            request_type: 请求类型，默认为Chat
            user_id: 用户ID，默认为system
            endpoint: API端点

        Returns:
            int | None: 返回记录ID，失败返回None
        """
        try:
            usage_record = LLMUsage.create(
                model_name=model_name,
                user_id=user_id,
                request_type=request_type.value,
                endpoint=endpoint,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost=0.0,
                status=UsageCallStatus.PROCESSING.value,
                timestamp=datetime.now(),
            )

            # logger.trace(
            #     f"创建了一条模型使用情况记录 - 模型: {model_name}, "
            #     f"子任务: {task_name}, 类型: {request_type.value}, "
            #     f"用户: {user_id}, 记录ID: {usage_record.id}"
            # )

            return usage_record.id
        except Exception as e:
            logger.error(f"创建模型使用情况记录失败: {str(e)}")
            return None

    def update_usage(
        self,
        record_id: int | None,
        model_info: ModelInfo,
        usage_data: Tuple[int, int, int] | None = None,
        stat: UsageCallStatus = UsageCallStatus.SUCCESS,
        ext_msg: str | None = None,
    ):
        """
        更新模型使用情况

        Args:
            record_id: 记录ID
            model_info: 模型信息
            usage_data: 使用情况数据(输入token数量, 输出token数量, 总token数量)
            stat: 任务调用状态
            ext_msg: 额外信息
        """
        if not record_id:
            logger.error("更新模型使用情况失败: record_id不能为空")
            return

        if usage_data and len(usage_data) != 3:
            logger.error("更新模型使用情况失败: usage_data的长度不正确，应该为3个元素")
            return

        # 提取使用情况数据
        prompt_tokens = usage_data[0] if usage_data else 0
        completion_tokens = usage_data[1] if usage_data else 0
        total_tokens = usage_data[2] if usage_data else 0

        try:
            # 使用Peewee更新记录
            update_query = LLMUsage.update(
                status=stat.value,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost=self._calculate_cost(prompt_tokens, completion_tokens, model_info) if usage_data else 0.0,
            ).where(LLMUsage.id == record_id)  # type: ignore

            updated_count = update_query.execute()

            if updated_count == 0:
                logger.warning(f"记录ID {record_id} 不存在，无法更新")
                return

            logger.debug(
                f"Token使用情况 - 模型: {model_info.name}, "
                f"记录ID: {record_id}, "
                f"任务状态: {stat.value}, 额外信息: {ext_msg or 'N/A'}, "
                f"提示词: {prompt_tokens}, 完成: {completion_tokens}, "
                f"总计: {total_tokens}"
            )
        except Exception as e:
            logger.error(f"记录token使用情况失败: {str(e)}")
