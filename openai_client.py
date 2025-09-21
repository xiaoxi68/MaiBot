import asyncio
import io
import json
import re
import base64
from collections.abc import Iterable
from typing import Callable, Any, Coroutine, Optional
from json_repair import repair_json

from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APIStatusError,
    NOT_GIVEN,
    AsyncStream,
)
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from openai.types.chat.chat_completion_chunk import ChoiceDelta

from src.config.api_ada_configs import ModelInfo, APIProvider
from src.common.logger import get_logger
from .base_client import APIResponse, UsageRecord, BaseClient, client_registry
from ..exceptions import (
    RespParseException,
    NetworkConnectionError,
    RespNotOkException,
    ReqAbortException,
    EmptyResponseException,
)
from ..payload_content.message import Message, RoleType, SUPPORTED_IMAGE_FORMATS
from ..payload_content.resp_format import RespFormat
from ..payload_content.tool_option import ToolOption, ToolParam, ToolCall

logger = get_logger("OpenAI客户端")


GEMINI_COMPATIBLE_IMAGE_FORMATS = ["png", "jpg", "jpeg", "webp", "heic", "heif"]


def _normalize_format_list(formats: Iterable[str]) -> list[str]:
    return sorted({fmt.lower() for fmt in formats if isinstance(fmt, str) and fmt})


def _is_gemini_like_model(model_info: ModelInfo) -> bool:
    identifier = model_info.model_identifier.lower()
    name = model_info.name.lower()

    if "gemini" in identifier or "gemini" in name:
        return True

    backend = model_info.extra_params.get("backend") if isinstance(model_info.extra_params, dict) else None
    if isinstance(backend, str) and backend.lower() == "gemini":
        return True

    underlying = model_info.extra_params.get("underlying_provider") if isinstance(model_info.extra_params, dict) else None
    if isinstance(underlying, str) and underlying.lower() == "gemini":
        return True

    return False


def _resolve_supported_image_formats(model_info: ModelInfo) -> list[str] | None:
    extra_formats = (
        model_info.extra_params.get("supported_image_formats")
        if isinstance(model_info.extra_params, dict)
        else None
    )
    if isinstance(extra_formats, (list, tuple, set)):
        normalized = _normalize_format_list(extra_formats)
        if normalized:
            return normalized

    if _is_gemini_like_model(model_info):
        return GEMINI_COMPATIBLE_IMAGE_FORMATS

    return None


def _find_unsupported_image_formats(message_list: list[Message], allowed_formats: Iterable[str]) -> set[str]:
    allowed = {fmt.lower() for fmt in allowed_formats}
    unsupported: set[str] = set()

    for message in message_list:
        if isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, tuple):
                    fmt = item[0].lower()
                    if fmt not in allowed:
                        unsupported.add(fmt)

    return unsupported


def _convert_messages(
    messages: list[Message],
    supported_image_formats: Iterable[str] | None = None,
) -> list[ChatCompletionMessageParam]:
    """
    转换消息格式 - 将消息转换为OpenAI API所需的格式
    :param messages: 消息列表
    :return: 转换后的消息列表
    """

    allowed_formats = {fmt.lower() for fmt in (supported_image_formats or SUPPORTED_IMAGE_FORMATS)}

    def _convert_message_item(message: Message) -> ChatCompletionMessageParam:
        """
        转换单个消息格式
        :param message: 消息对象
        :return: 转换后的消息字典
        """

        # 添加Content
        content: str | list[dict[str, Any]]
        if isinstance(message.content, str):
            content = message.content
        elif isinstance(message.content, list):
            content = []
            for item in message.content:
                if isinstance(item, tuple):
                    image_format = item[0].lower()
                    if image_format not in allowed_formats:
                        raise ValueError(
                            f"不受支持的图片格式: {image_format}. 允许的格式: {', '.join(sorted(allowed_formats))}"
                        )
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{image_format};base64,{item[1]}"},
                        }
                    )
                elif isinstance(item, str):
                    content.append({"type": "text", "text": item})
        else:
            raise RuntimeError("无法触及的代码：请使用MessageBuilder类构建消息对象")

        ret = {
            "role": message.role.value,
            "content": content,
        }

        # 添加工具调用ID
        if message.role == RoleType.Tool:
            if not message.tool_call_id:
                raise ValueError("无法触及的代码：请使用MessageBuilder类构建消息对象")
            ret["tool_call_id"] = message.tool_call_id

        return ret  # type: ignore

    return [_convert_message_item(message) for message in messages]


def _convert_tool_options(tool_options: list[ToolOption]) -> list[dict[str, Any]]:
    """
    转换工具选项格式 - 将工具选项转换为OpenAI API所需的格式
    :param tool_options: 工具选项列表
    :return: 转换后的工具选项列表
    """

    def _convert_tool_param(tool_option_param: ToolParam) -> dict[str, Any]:
        """
        转换单个工具参数格式
        :param tool_option_param: 工具参数对象
        :return: 转换后的工具参数字典
        """
        return_dict: dict[str, Any] = {
            "type": tool_option_param.param_type.value,
            "description": tool_option_param.description,
        }
        if tool_option_param.enum_values:
            return_dict["enum"] = tool_option_param.enum_values
        return return_dict

    def _convert_tool_option_item(tool_option: ToolOption) -> dict[str, Any]:
        """
        转换单个工具项格式
        :param tool_option: 工具选项对象
        :return: 转换后的工具选项字典
        """
        ret: dict[str, Any] = {
            "name": tool_option.name,
            "description": tool_option.description,
        }
        if tool_option.params:
            ret["parameters"] = {
                "type": "object",
                "properties": {param.name: _convert_tool_param(param) for param in tool_option.params},
                "required": [param.name for param in tool_option.params if param.required],
            }
        return ret

    return [
        {
            "type": "function",
            "function": _convert_tool_option_item(tool_option),
        }
        for tool_option in tool_options
    ]


def _process_delta(
    delta: ChoiceDelta,
    has_rc_attr_flag: bool,
    in_rc_flag: bool,
    rc_delta_buffer: io.StringIO,
    fc_delta_buffer: io.StringIO,
    tool_calls_buffer: list[tuple[str, str, io.StringIO]],
) -> bool:
    # 接收content
    if has_rc_attr_flag:
        # 有独立的推理内容块，则无需考虑content内容的判读
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:  # type: ignore
            # 如果有推理内容，则将其写入推理内容缓冲区
            assert isinstance(delta.reasoning_content, str)  # type: ignore
            rc_delta_buffer.write(delta.reasoning_content)  # type: ignore
        elif delta.content:
            # 如果有正式内容，则将其写入正式内容缓冲区
            fc_delta_buffer.write(delta.content)
    elif hasattr(delta, "content") and delta.content is not None:
        # 没有独立的推理内容块，但有正式内容
        if in_rc_flag:
            # 当前在推理内容块中
            if delta.content == "</think>":
                # 如果当前内容是</think>，则将其视为推理内容的结束标记，退出推理内容块
                in_rc_flag = False
            else:
                # 其他情况视为推理内容，加入推理内容缓冲区
                rc_delta_buffer.write(delta.content)
        elif delta.content == "<think>" and not fc_delta_buffer.getvalue():
            # 如果当前内容是<think>，且正式内容缓冲区为空，说明<think>为输出的首个token
            # 则将其视为推理内容的开始标记，进入推理内容块
            in_rc_flag = True
        else:
            # 其他情况视为正式内容，加入正式内容缓冲区
            fc_delta_buffer.write(delta.content)
    # 接收tool_calls
    if hasattr(delta, "tool_calls") and delta.tool_calls:
        tool_call_delta = delta.tool_calls[0]

        if tool_call_delta.index >= len(tool_calls_buffer):
            # 调用索引号大于等于缓冲区长度，说明是新的工具调用
            if tool_call_delta.id and tool_call_delta.function and tool_call_delta.function.name:
                tool_calls_buffer.append(
                    (
                        tool_call_delta.id,
                        tool_call_delta.function.name,
                        io.StringIO(),
                    )
                )
            else:
                logger.warning("工具调用索引号大于等于缓冲区长度，但缺少ID或函数信息。")

        if tool_call_delta.function and tool_call_delta.function.arguments:
            # 如果有工具调用参数，则添加到对应的工具调用的参数串缓冲区中
            tool_calls_buffer[tool_call_delta.index][2].write(tool_call_delta.function.arguments)

    return in_rc_flag


def _build_stream_api_resp(
    _fc_delta_buffer: io.StringIO,
    _rc_delta_buffer: io.StringIO,
    _tool_calls_buffer: list[tuple[str, str, io.StringIO]],
) -> APIResponse:
    resp = APIResponse()

    if _rc_delta_buffer.tell() > 0:
        # 如果推理内容缓冲区不为空，则将其写入APIResponse对象
        resp.reasoning_content = _rc_delta_buffer.getvalue()
    _rc_delta_buffer.close()
    if _fc_delta_buffer.tell() > 0:
        # 如果正式内容缓冲区不为空，则将其写入APIResponse对象
        resp.content = _fc_delta_buffer.getvalue()
    _fc_delta_buffer.close()
    if _tool_calls_buffer:
        # 如果工具调用缓冲区不为空，则将其解析为ToolCall对象列表
        resp.tool_calls = []
        for call_id, function_name, arguments_buffer in _tool_calls_buffer:
            if arguments_buffer.tell() > 0:
                # 如果参数串缓冲区不为空，则解析为JSON对象
                raw_arg_data = arguments_buffer.getvalue()
                arguments_buffer.close()
                try:
                    arguments = json.loads(repair_json(raw_arg_data))
                    if not isinstance(arguments, dict):
                        raise RespParseException(
                            None,
                            f"响应解析失败，工具调用参数无法解析为字典类型。工具调用参数原始响应：\n{raw_arg_data}",
                        )
                except json.JSONDecodeError as e:
                    raise RespParseException(
                        None,
                        f"响应解析失败，无法解析工具调用参数。工具调用参数原始响应：{raw_arg_data}",
                    ) from e
            else:
                arguments_buffer.close()
                arguments = None

            resp.tool_calls.append(ToolCall(call_id, function_name, arguments))

    if not resp.content and not resp.tool_calls:
        raise EmptyResponseException()

    return resp


async def _default_stream_response_handler(
    resp_stream: AsyncStream[ChatCompletionChunk],
    interrupt_flag: asyncio.Event | None,
) -> tuple[APIResponse, Optional[tuple[int, int, int]]]:
    """
    流式响应处理函数 - 处理OpenAI API的流式响应
    :param resp_stream: 流式响应对象
    :return: APIResponse对象
    """

    _has_rc_attr_flag = False  # 标记是否有独立的推理内容块
    _in_rc_flag = False  # 标记是否在推理内容块中
    _rc_delta_buffer = io.StringIO()  # 推理内容缓冲区，用于存储接收到的推理内容
    _fc_delta_buffer = io.StringIO()  # 正式内容缓冲区，用于存储接收到的正式内容
    _tool_calls_buffer: list[tuple[str, str, io.StringIO]] = []  # 工具调用缓冲区，用于存储接收到的工具调用
    _usage_record = None  # 使用情况记录

    def _insure_buffer_closed():
        # 确保缓冲区被关闭
        if _rc_delta_buffer and not _rc_delta_buffer.closed:
            _rc_delta_buffer.close()
        if _fc_delta_buffer and not _fc_delta_buffer.closed:
            _fc_delta_buffer.close()
        for _, _, buffer in _tool_calls_buffer:
            if buffer and not buffer.closed:
                buffer.close()

    async for event in resp_stream:
        if interrupt_flag and interrupt_flag.is_set():
            # 如果中断量被设置，则抛出ReqAbortException
            _insure_buffer_closed()
            raise ReqAbortException("请求被外部信号中断")
        # 空 choices / usage-only 帧的防御
        if not hasattr(event, "choices") or not event.choices:
            if hasattr(event, "usage") and event.usage:
                _usage_record = (
                    event.usage.prompt_tokens or 0,
                    event.usage.completion_tokens or 0,
                    event.usage.total_tokens or 0,
                )
            continue  # 跳过本帧，避免访问 choices[0]
        delta = event.choices[0].delta  # 获取当前块的delta内容

        if hasattr(delta, "reasoning_content") and delta.reasoning_content:  # type: ignore
            # 标记：有独立的推理内容块
            _has_rc_attr_flag = True

        _in_rc_flag = _process_delta(
            delta,
            _has_rc_attr_flag,
            _in_rc_flag,
            _rc_delta_buffer,
            _fc_delta_buffer,
            _tool_calls_buffer,
        )

        if event.usage:
            # 如果有使用情况，则将其存储在APIResponse对象中
            _usage_record = (
                event.usage.prompt_tokens or 0,
                event.usage.completion_tokens or 0,
                event.usage.total_tokens or 0,
            )

    try:
        return _build_stream_api_resp(
            _fc_delta_buffer,
            _rc_delta_buffer,
            _tool_calls_buffer,
        ), _usage_record
    except Exception:
        # 确保缓冲区被关闭
        _insure_buffer_closed()
        raise


pattern = re.compile(
    r"<think>(?P<think>.*?)</think>(?P<content>.*)|<think>(?P<think_unclosed>.*)|(?P<content_only>.+)",
    re.DOTALL,
)
"""用于解析推理内容的正则表达式"""


def _default_normal_response_parser(
    resp: ChatCompletion,
) -> tuple[APIResponse, Optional[tuple[int, int, int]]]:
    """
    解析对话补全响应 - 将OpenAI API响应解析为APIResponse对象
    :param resp: 响应对象
    :return: APIResponse对象
    """
    api_response = APIResponse()

    if not hasattr(resp, "choices") or len(resp.choices) == 0:
        raise EmptyResponseException("响应解析失败，缺失choices字段或choices列表为空")
    message_part = resp.choices[0].message

    if hasattr(message_part, "reasoning_content") and message_part.reasoning_content:  # type: ignore
        # 有有效的推理字段
        api_response.content = message_part.content
        api_response.reasoning_content = message_part.reasoning_content  # type: ignore
    elif message_part.content:
        # 提取推理和内容
        match = pattern.match(message_part.content)
        if not match:
            raise RespParseException(resp, "响应解析失败，无法捕获推理内容和输出内容")
        if match.group("think") is not None:
            result = match.group("think").strip(), match.group("content").strip()
        elif match.group("think_unclosed") is not None:
            result = match.group("think_unclosed").strip(), None
        else:
            result = None, match.group("content_only").strip()
        api_response.reasoning_content, api_response.content = result

    # 提取工具调用
    if message_part.tool_calls:
        api_response.tool_calls = []
        for call in message_part.tool_calls:
            try:
                arguments = json.loads(repair_json(call.function.arguments))
                if not isinstance(arguments, dict):
                    raise RespParseException(resp, "响应解析失败，工具调用参数无法解析为字典类型")
                api_response.tool_calls.append(ToolCall(call.id, call.function.name, arguments))
            except json.JSONDecodeError as e:
                raise RespParseException(resp, "响应解析失败，无法解析工具调用参数") from e

    # 提取Usage信息
    if resp.usage:
        _usage_record = (
            resp.usage.prompt_tokens or 0,
            resp.usage.completion_tokens or 0,
            resp.usage.total_tokens or 0,
        )
    else:
        _usage_record = None

    # 将原始响应存储在原始数据中
    api_response.raw_data = resp

    if not api_response.content and not api_response.tool_calls:
        raise EmptyResponseException()

    return api_response, _usage_record


@client_registry.register_client_class("openai")
class OpenaiClient(BaseClient):
    def __init__(self, api_provider: APIProvider):
        super().__init__(api_provider)
        self.client: AsyncOpenAI = AsyncOpenAI(
            base_url=api_provider.base_url,
            api_key=api_provider.api_key,
            max_retries=0,
            timeout=api_provider.timeout,
        )

    async def get_response(
        self,
        model_info: ModelInfo,
        message_list: list[Message],
        tool_options: list[ToolOption] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        response_format: RespFormat | None = None,
        stream_response_handler: Optional[
            Callable[
                [AsyncStream[ChatCompletionChunk], asyncio.Event | None],
                Coroutine[Any, Any, tuple[APIResponse, Optional[tuple[int, int, int]]]],
            ]
        ] = None,
        async_response_parser: Optional[
            Callable[[ChatCompletion], tuple[APIResponse, Optional[tuple[int, int, int]]]]
        ] = None,
        interrupt_flag: asyncio.Event | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        获取对话响应
        Args:
            model_info: 模型信息
            message_list: 对话体
            tool_options: 工具选项（可选，默认为None）
            max_tokens: 最大token数（可选，默认为1024）
            temperature: 温度（可选，默认为0.7）
            response_format: 响应格式（可选，默认为 NotGiven ）
            stream_response_handler: 流式响应处理函数（可选，默认为default_stream_response_handler）
            async_response_parser: 响应解析函数（可选，默认为default_response_parser）
            interrupt_flag: 中断信号量（可选，默认为None）
        Returns:
            (响应文本, 推理文本, 工具调用, 其他数据)
        """
        if stream_response_handler is None:
            stream_response_handler = _default_stream_response_handler

        if async_response_parser is None:
            async_response_parser = _default_normal_response_parser

        supported_formats_override = _resolve_supported_image_formats(model_info)
        allowed_formats = supported_formats_override or self.get_support_image_formats()

        if supported_formats_override:
            unsupported_formats = _find_unsupported_image_formats(message_list, allowed_formats)
            if unsupported_formats:
                allowed_display = ", ".join(allowed_formats)
                unsupported_display = ", ".join(sorted(unsupported_formats))
                raise RespNotOkException(
                    400,
                    f"当前模型不支持以下图片格式: {unsupported_display}，请转换为 {allowed_display} 格式后重试。",
                )

        # 将messages构造为OpenAI API所需的格式
        try:
            messages: Iterable[ChatCompletionMessageParam] = _convert_messages(message_list, allowed_formats)
        except ValueError as e:
            raise RespNotOkException(400, str(e)) from e
        # 将tool_options转换为OpenAI API所需的格式
        tools: Iterable[ChatCompletionToolParam] = _convert_tool_options(tool_options) if tool_options else NOT_GIVEN  # type: ignore

        try:
            if model_info.force_stream_mode:
                req_task = asyncio.create_task(
                    self.client.chat.completions.create(
                        model=model_info.model_identifier,
                        messages=messages,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        response_format=NOT_GIVEN,
                        extra_body=extra_params,
                    )
                )
                while not req_task.done():
                    if interrupt_flag and interrupt_flag.is_set():
                        # 如果中断量存在且被设置，则取消任务并抛出异常
                        req_task.cancel()
                        raise ReqAbortException("请求被外部信号中断")
                    await asyncio.sleep(0.1)  # 等待0.1秒后再次检查任务&中断信号量状态

                resp, usage_record = await stream_response_handler(req_task.result(), interrupt_flag)
            else:
                # 发送请求并获取响应
                # start_time = time.time()
                req_task = asyncio.create_task(
                    self.client.chat.completions.create(
                        model=model_info.model_identifier,
                        messages=messages,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        response_format=NOT_GIVEN,
                        extra_body=extra_params,
                    )
                )
                while not req_task.done():
                    if interrupt_flag and interrupt_flag.is_set():
                        # 如果中断量存在且被设置，则取消任务并抛出异常
                        req_task.cancel()
                        raise ReqAbortException("请求被外部信号中断")
                    await asyncio.sleep(0.1)  # 等待0.5秒后再次检查任务&中断信号量状态

                # logger.info(f"OpenAI请求时间: {model_info.model_identifier}  {time.time() - start_time} \n{messages}")

                resp, usage_record = async_response_parser(req_task.result())
        except APIConnectionError as e:
            # 重封装APIConnectionError为NetworkConnectionError
            raise NetworkConnectionError() from e
        except APIStatusError as e:
            # 重封装APIError为RespNotOkException
            raise RespNotOkException(e.status_code, e.message) from e

        if usage_record:
            resp.usage = UsageRecord(
                model_name=model_info.name,
                provider_name=model_info.api_provider,
                prompt_tokens=usage_record[0],
                completion_tokens=usage_record[1],
                total_tokens=usage_record[2],
            )

        return resp

    async def get_embedding(
        self,
        model_info: ModelInfo,
        embedding_input: str,
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        获取文本嵌入
        :param model_info: 模型信息
        :param embedding_input: 嵌入输入文本
        :return: 嵌入响应
        """
        try:
            raw_response = await self.client.embeddings.create(
                model=model_info.model_identifier,
                input=embedding_input,
                extra_body=extra_params,
            )
        except APIConnectionError as e:
            # 添加详细的错误信息以便调试
            logger.error(f"OpenAI API连接错误（嵌入模型）: {str(e)}")
            logger.error(f"错误类型: {type(e)}")
            if hasattr(e, "__cause__") and e.__cause__:
                logger.error(f"底层错误: {str(e.__cause__)}")
            raise NetworkConnectionError() from e
        except APIStatusError as e:
            # 重封装APIError为RespNotOkException
            raise RespNotOkException(e.status_code) from e

        response = APIResponse()

        # 解析嵌入响应
        if len(raw_response.data) > 0:
            response.embedding = raw_response.data[0].embedding
        else:
            raise RespParseException(
                raw_response,
                "响应解析失败，缺失嵌入数据。",
            )

        # 解析使用情况
        if hasattr(raw_response, "usage"):
            response.usage = UsageRecord(
                model_name=model_info.name,
                provider_name=model_info.api_provider,
                prompt_tokens=raw_response.usage.prompt_tokens or 0,
                completion_tokens=getattr(raw_response.usage, "completion_tokens", 0),
                total_tokens=raw_response.usage.total_tokens or 0,
            )

        return response

    async def get_audio_transcriptions(
        self,
        model_info: ModelInfo,
        audio_base64: str,
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        获取音频转录
        :param model_info: 模型信息
        :param audio_base64: base64编码的音频数据
        :extra_params: 附加的请求参数
        :return: 音频转录响应
        """
        try:
            raw_response = await self.client.audio.transcriptions.create(
                model=model_info.model_identifier,
                file=("audio.wav", io.BytesIO(base64.b64decode(audio_base64))),
                extra_body=extra_params,
            )
        except APIConnectionError as e:
            raise NetworkConnectionError() from e
        except APIStatusError as e:
            # 重封装APIError为RespNotOkException
            raise RespNotOkException(e.status_code) from e
        response = APIResponse()
        # 解析转录响应
        if hasattr(raw_response, "text"):
            response.content = raw_response.text
        else:
            raise RespParseException(
                raw_response,
                "响应解析失败，缺失转录文本。",
            )
        return response

    def get_support_image_formats(self) -> list[str]:
        """
        获取支持的图片格式
        :return: 支持的图片格式列表
        """
        return ["jpg", "jpeg", "png", "webp", "gif"]
