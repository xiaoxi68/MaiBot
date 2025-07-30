import re
import copy
import asyncio
from datetime import datetime
from typing import Tuple, Union, List, Dict, Optional, Callable, Any
from src.common.logger import get_logger
import base64
from PIL import Image
from enum import Enum
import io
from src.common.database.database import db  # 确保 db 被导入用于 create_tables
from src.common.database.database_model import LLMUsage  # 导入 LLMUsage 模型
from src.config.config import global_config, model_config
from src.config.api_ada_configs import APIProvider, ModelInfo
from rich.traceback import install

from .payload_content.message import MessageBuilder, Message
from .payload_content.resp_format import RespFormat
from .payload_content.tool_option import ToolOption, ToolCall
from .model_client.base_client import BaseClient, APIResponse, UsageRecord, client_registry
from .utils import compress_messages

from .exceptions import (
    NetworkConnectionError,
    ReqAbortException,
    RespNotOkException,
    RespParseException,
    PayLoadTooLargeError,
    RequestAbortException,
    PermissionDeniedException,
)

install(extra_lines=3)

logger = get_logger("model_utils")

# 常见Error Code Mapping
error_code_mapping = {
    400: "参数不正确",
    401: "API key 错误，认证失败，请检查 config/model_config.toml 中的配置是否正确",
    402: "账号余额不足",
    403: "需要实名,或余额不足",
    404: "Not Found",
    429: "请求过于频繁，请稍后再试",
    500: "服务器内部故障",
    503: "服务器负载过高",
}


class RequestType(Enum):
    """请求类型枚举"""

    RESPONSE = "response"
    EMBEDDING = "embedding"


class LLMRequest:
    """LLM请求类"""

    # 定义需要转换的模型列表，作为类变量避免重复
    MODELS_NEEDING_TRANSFORMATION = [
        "o1",
        "o1-2024-12-17",
        "o1-mini",
        "o1-mini-2024-09-12",
        "o1-preview",
        "o1-preview-2024-09-12",
        "o1-pro",
        "o1-pro-2025-03-19",
        "o3",
        "o3-2025-04-16",
        "o3-mini",
        "o3-mini-2025-01-31",
        "o4-mini",
        "o4-mini-2025-04-16",
    ]

    def __init__(self, task_name: str, request_type: str = "") -> None:
        self.task_name = task_name
        self.model_for_task = model_config.model_task_config.get_task(task_name)
        self.request_type = request_type
        self.model_usage: Dict[str, Tuple[int, int]] = {model: (0, 0) for model in self.model_for_task.model_list}
        """模型使用量记录，用于进行负载均衡，对应为(total_tokens, penalty)，惩罚值是为了能在某个模型请求不给力的时候进行调整"""

        self.pri_in = 0
        self.pri_out = 0
        
        self._init_database()

    @staticmethod
    def _init_database():
        """初始化数据库集合"""
        try:
            # 使用 Peewee 创建表，safe=True 表示如果表已存在则不会抛出错误
            db.create_tables([LLMUsage], safe=True)
            # logger.debug("LLMUsage 表已初始化/确保存在。")
        except Exception as e:
            logger.error(f"创建 LLMUsage 表失败: {str(e)}")

    async def generate_response_for_image(
        self,
        prompt: str,
        image_base64: str,
        image_format: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, str, Optional[List[Dict[str, Any]]]]:
        """
        为图像生成响应
        Args:
            prompt (str): 提示词
            image_base64 (str): 图像的Base64编码字符串
            image_format (str): 图像格式（如 'png', 'jpeg' 等）
        Returns:

        """
        # 请求体构建
        message_builder = MessageBuilder()
        message_builder.add_text_content(prompt)
        message_builder.add_image_content(image_base64=image_base64, image_format=image_format)
        messages = [message_builder.build()]

        # 模型选择
        model_info, api_provider, client = self._select_model()

        # 请求并处理返回值
        response = await self._execute_request(
            api_provider=api_provider,
            client=client,
            request_type=RequestType.RESPONSE,
            model_info=model_info,
            message_list=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.content or ""
        reasoning_content = response.reasoning_content or ""
        tool_calls = response.tool_calls
        # 从内容中提取<think>标签的推理内容（向后兼容）
        if not reasoning_content and content:
            content, extracted_reasoning = self._extract_reasoning(content)
            reasoning_content = extracted_reasoning
        if usage := response.usage:
            self.pri_in = model_info.price_in
            self.pri_out = model_info.price_out
            self._record_usage(
                model_name=model_info.name,
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens or 0,
                user_id="system",
                request_type=self.request_type,
                endpoint="/chat/completions",
            )
        return content, reasoning_content, self._convert_tool_calls(tool_calls) if tool_calls else None

    async def generate_response_for_voice(self):
        pass

    async def generate_response_async(
        self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None
    ) -> Tuple[str, str, Optional[List[Dict[str, Any]]]]:
        """
        异步生成响应
        Args:
            prompt (str): 提示词
            temperature (float, optional): 温度参数
            max_tokens (int, optional): 最大token数
        Returns:
            Tuple[str, str, Optional[List[Dict[str, Any]]]]: 响应内容、推理内容和工具调用列表
        """
        # 请求体构建
        message_builder = MessageBuilder()
        message_builder.add_text_content(prompt)
        messages = [message_builder.build()]

        # 模型选择
        model_info, api_provider, client = self._select_model()

        # 请求并处理返回值
        response = await self._execute_request(
            api_provider=api_provider,
            client=client,
            request_type=RequestType.RESPONSE,
            model_info=model_info,
            message_list=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.content
        reasoning_content = response.reasoning_content or ""
        tool_calls = response.tool_calls
        # 从内容中提取<think>标签的推理内容（向后兼容）
        if not reasoning_content and content:
            content, extracted_reasoning = self._extract_reasoning(content)
            reasoning_content = extracted_reasoning
        if usage := response.usage:
            self.pri_in = model_info.price_in
            self.pri_out = model_info.price_out
            self._record_usage(
                model_name=model_info.name,
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens or 0,
                user_id="system",
                request_type=self.request_type,
                endpoint="/chat/completions",
            )
        if not content:
            raise RuntimeError("获取LLM生成内容失败")

        return content, reasoning_content, self._convert_tool_calls(tool_calls) if tool_calls else None

    async def get_embedding(self, embedding_input: str) -> List[float]:
        """获取嵌入向量"""
        # 无需构建消息体，直接使用输入文本
        model_info, api_provider, client = self._select_model()

        # 请求并处理返回值
        response = await self._execute_request(
            api_provider=api_provider,
            client=client,
            request_type=RequestType.EMBEDDING,
            model_info=model_info,
            embedding_input=embedding_input,
        )

        embedding = response.embedding

        if response.usage:
            self.pri_in = model_info.price_in
            self.pri_out = model_info.price_out
            self._record_usage(
                model_name=model_info.name,
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens or 0,
                user_id="system",
                request_type=self.request_type,
                endpoint="/embeddings",
            )

        if not embedding:
            raise RuntimeError("获取embedding失败")

        return embedding

    def _select_model(self) -> Tuple[ModelInfo, APIProvider, BaseClient]:
        """
        根据总tokens和惩罚值选择的模型
        """
        least_used_model_name = min(
            self.model_usage, key=lambda k: self.model_usage[k][0] + self.model_usage[k][1] * 300
        )
        model_info = model_config.get_model_info(least_used_model_name)
        api_provider = model_config.get_provider(model_info.api_provider)
        client = client_registry.get_client_class(api_provider.client_type)(copy.deepcopy(api_provider))
        return model_info, api_provider, client

    def _convert_tool_calls(self, tool_calls: List[ToolCall]) -> List[Dict[str, Any]]:
        """将ToolCall对象转换为Dict列表"""
        pass

    async def _execute_request(
        self,
        api_provider: APIProvider,
        client: BaseClient,
        request_type: RequestType,
        model_info: ModelInfo,
        message_list: List[Message] | None = None,
        tool_options: list[ToolOption] | None = None,
        response_format: RespFormat | None = None,
        stream_response_handler: Optional[Callable] = None,
        async_response_parser: Optional[Callable] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        embedding_input: str = "",
    ) -> APIResponse:
        """
        实际执行请求的方法

        包含了重试和异常处理逻辑
        """
        retry_remain = api_provider.max_retry
        compressed_messages: Optional[List[Message]] = None
        while retry_remain > 0:
            try:
                if request_type == RequestType.RESPONSE:
                    assert message_list is not None, "message_list cannot be None for response requests"
                    return await client.get_response(
                        model_info=model_info,
                        message_list=(compressed_messages or message_list),
                        tool_options=tool_options,
                        max_tokens=self.model_for_task.max_tokens if max_tokens is None else max_tokens,
                        temperature=self.model_for_task.temperature if temperature is None else temperature,
                        response_format=response_format,
                        stream_response_handler=stream_response_handler,
                        async_response_parser=async_response_parser,
                    )
                elif request_type == RequestType.EMBEDDING:
                    assert embedding_input, "embedding_input cannot be empty for embedding requests"
                    return await client.get_embedding(model_info=model_info, embedding_input=embedding_input)
            except Exception as e:
                logger.debug(f"请求失败: {str(e)}")
                # 处理异常
                total_tokens, penalty = self.model_usage[model_info.name]
                self.model_usage[model_info.name] = (total_tokens, penalty + 1)
                wait_interval, compressed_messages = self._default_exception_handler(
                    e,
                    self.task_name,
                    model_name=model_info.name,
                    remain_try=retry_remain,
                    messages=(message_list, compressed_messages is not None),
                )

                if wait_interval == -1:
                    retry_remain = 0  # 不再重试
                elif wait_interval > 0:
                    logger.info(f"等待 {wait_interval} 秒后重试...")
                    await asyncio.sleep(wait_interval)
            finally:
                # 放在finally防止死循环
                retry_remain -= 1
        logger.error(
            f"任务 '{self.task_name}' 模型 '{model_info.name}' 请求失败，达到最大重试次数 {api_provider.max_retry} 次"
        )
        raise RuntimeError("请求失败，已达到最大重试次数")

    def _default_exception_handler(
        self,
        e: Exception,
        task_name: str,
        model_name: str,
        remain_try: int,
        retry_interval: int = 10,
        messages: Tuple[List[Message], bool] | None = None,
    ) -> Tuple[int, List[Message] | None]:
        """
        默认异常处理函数
        Args:
            e (Exception): 异常对象
            task_name (str): 任务名称
            model_name (str): 模型名称
            remain_try (int): 剩余尝试次数
            retry_interval (int): 重试间隔
            messages (tuple[list[Message], bool] | None): (消息列表, 是否已压缩过)
        Returns:
            (等待间隔（如果为0则不等待，为-1则不再请求该模型）, 新的消息列表（适用于压缩消息）)
        """

        if isinstance(e, NetworkConnectionError):  # 网络连接错误
            return self._check_retry(
                remain_try,
                retry_interval,
                can_retry_msg=f"任务-'{task_name}' 模型-'{model_name}': 连接异常，将于{retry_interval}秒后重试",
                cannot_retry_msg=f"任务-'{task_name}' 模型-'{model_name}': 连接异常，超过最大重试次数，请检查网络连接状态或URL是否正确",
            )
        elif isinstance(e, ReqAbortException):
            logger.warning(f"任务-'{task_name}' 模型-'{model_name}': 请求被中断，详细信息-{str(e.message)}")
            return -1, None  # 不再重试请求该模型
        elif isinstance(e, RespNotOkException):
            return self._handle_resp_not_ok(
                e,
                task_name,
                model_name,
                remain_try,
                retry_interval,
                messages,
            )
        elif isinstance(e, RespParseException):
            # 响应解析错误
            logger.error(f"任务-'{task_name}' 模型-'{model_name}': 响应解析错误，错误信息-{e.message}")
            logger.debug(f"附加内容: {str(e.ext_info)}")
            return -1, None  # 不再重试请求该模型
        else:
            logger.error(f"任务-'{task_name}' 模型-'{model_name}': 未知异常，错误信息-{str(e)}")
            return -1, None  # 不再重试请求该模型

    def _check_retry(
        self,
        remain_try: int,
        retry_interval: int,
        can_retry_msg: str,
        cannot_retry_msg: str,
        can_retry_callable: Callable | None = None,
        **kwargs,
    ) -> Tuple[int, List[Message] | None]:
        """辅助函数：检查是否可以重试
        Args:
            remain_try (int): 剩余尝试次数
            retry_interval (int): 重试间隔
            can_retry_msg (str): 可以重试时的提示信息
            cannot_retry_msg (str): 不可以重试时的提示信息
            can_retry_callable (Callable | None): 可以重试时调用的函数（如果有）
            **kwargs: 其他参数

        Returns:
            (Tuple[int, List[Message] | None]): (等待间隔（如果为0则不等待，为-1则不再请求该模型）, 新的消息列表（适用于压缩消息）)
        """
        if remain_try > 0:
            # 还有重试机会
            logger.warning(f"{can_retry_msg}")
            if can_retry_callable is not None:
                return retry_interval, can_retry_callable(**kwargs)
            else:
                return retry_interval, None
        else:
            # 达到最大重试次数
            logger.warning(f"{cannot_retry_msg}")
            return -1, None  # 不再重试请求该模型

    def _handle_resp_not_ok(
        self,
        e: RespNotOkException,
        task_name: str,
        model_name: str,
        remain_try: int,
        retry_interval: int = 10,
        messages: tuple[list[Message], bool] | None = None,
    ):
        """
        处理响应错误异常
        Args:
            e (RespNotOkException): 响应错误异常对象
            task_name (str): 任务名称
            model_name (str): 模型名称
            remain_try (int): 剩余尝试次数
            retry_interval (int): 重试间隔
            messages (tuple[list[Message], bool] | None): (消息列表, 是否已压缩过)
        Returns:
            (等待间隔（如果为0则不等待，为-1则不再请求该模型）, 新的消息列表（适用于压缩消息）)
        """
        # 响应错误
        if e.status_code in [400, 401, 402, 403, 404]:
            # 客户端错误
            logger.warning(
                f"任务-'{task_name}' 模型-'{model_name}': 请求失败，错误代码-{e.status_code}，错误信息-{e.message}"
            )
            return -1, None  # 不再重试请求该模型
        elif e.status_code == 413:
            if messages and not messages[1]:
                # 消息列表不为空且未压缩，尝试压缩消息
                return self._check_retry(
                    remain_try,
                    0,
                    can_retry_msg=f"任务-'{task_name}' 模型-'{model_name}': 请求体过大，尝试压缩消息后重试",
                    cannot_retry_msg=f"任务-'{task_name}' 模型-'{model_name}': 请求体过大，压缩消息后仍然过大，放弃请求",
                    can_retry_callable=compress_messages,
                    messages=messages[0],
                )
            # 没有消息可压缩
            logger.warning(f"任务-'{task_name}' 模型-'{model_name}': 请求体过大，无法压缩消息，放弃请求。")
            return -1, None
        elif e.status_code == 429:
            # 请求过于频繁
            return self._check_retry(
                remain_try,
                retry_interval,
                can_retry_msg=f"任务-'{task_name}' 模型-'{model_name}': 请求过于频繁，将于{retry_interval}秒后重试",
                cannot_retry_msg=f"任务-'{task_name}' 模型-'{model_name}': 请求过于频繁，超过最大重试次数，放弃请求",
            )
        elif e.status_code >= 500:
            # 服务器错误
            return self._check_retry(
                remain_try,
                retry_interval,
                can_retry_msg=f"任务-'{task_name}' 模型-'{model_name}': 服务器错误，将于{retry_interval}秒后重试",
                cannot_retry_msg=f"任务-'{task_name}' 模型-'{model_name}': 服务器错误，超过最大重试次数，请稍后再试",
            )
        else:
            # 未知错误
            logger.warning(
                f"任务-'{task_name}' 模型-'{model_name}': 未知错误，错误代码-{e.status_code}，错误信息-{e.message}"
            )
            return -1, None

    @staticmethod
    def _extract_reasoning(content: str) -> Tuple[str, str]:
        """CoT思维链提取，向后兼容"""
        match = re.search(r"(?:<think>)?(.*?)</think>", content, re.DOTALL)
        content = re.sub(r"(?:<think>)?.*?</think>", "", content, flags=re.DOTALL, count=1).strip()
        reasoning = match[1].strip() if match else ""
        return content, reasoning

    def _record_usage(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        user_id: str = "system",
        request_type: str | None = None,
        endpoint: str = "/chat/completions",
    ):
        """记录模型使用情况到数据库
        Args:
            prompt_tokens: 输入token数
            completion_tokens: 输出token数
            total_tokens: 总token数
            user_id: 用户ID，默认为system
            request_type: 请求类型
            endpoint: API端点
        """
        # 如果 request_type 为 None，则使用实例变量中的值
        if request_type is None:
            request_type = self.request_type

        try:
            # 使用 Peewee 模型创建记录
            LLMUsage.create(
                model_name=model_name,
                user_id=user_id,
                request_type=request_type,
                endpoint=endpoint,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost=self._calculate_cost(prompt_tokens, completion_tokens),
                status="success",
                timestamp=datetime.now(),  # Peewee 会处理 DateTimeField
            )
            logger.debug(
                f"Token使用情况 - 模型: {model_name}, "
                f"用户: {user_id}, 类型: {request_type}, "
                f"提示词: {prompt_tokens}, 完成: {completion_tokens}, "
                f"总计: {total_tokens}"
            )
        except Exception as e:
            logger.error(f"记录token使用情况失败: {str(e)}")

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """计算API调用成本
        使用模型的pri_in和pri_out价格计算输入和输出的成本

        Args:
            prompt_tokens: 输入token数量
            completion_tokens: 输出token数量

        Returns:
            float: 总成本（元）
        """
        # 使用模型的pri_in和pri_out计算成本
        input_cost = (prompt_tokens / 1000000) * self.pri_in
        output_cost = (completion_tokens / 1000000) * self.pri_out
        return round(input_cost + output_cost, 6)
