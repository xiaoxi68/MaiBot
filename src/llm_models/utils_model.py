import re
from datetime import datetime
from typing import Tuple, Union
from src.common.logger import get_logger
import base64
from PIL import Image
import io
from src.common.database.database import db  # 确保 db 被导入用于 create_tables
from src.common.database.database_model import LLMUsage  # 导入 LLMUsage 模型
from src.config.config import global_config
from rich.traceback import install

install(extra_lines=3)

logger = get_logger("model_utils")

# 新架构导入 - 使用延迟导入以支持fallback模式
try:
    from .model_manager import ModelManager
    from .model_client import ModelRequestHandler
    from .payload_content.message import MessageBuilder
    
    # 不在模块级别初始化ModelManager，延迟到实际使用时
    ModelManager_class = ModelManager
    model_manager = None  # 延迟初始化
    
    # 添加请求处理器缓存，避免重复创建
    _request_handler_cache = {}  # 格式: {(model_name, task_name): ModelRequestHandler}
    
    NEW_ARCHITECTURE_AVAILABLE = True
    logger.info("新架构模块导入成功")
except Exception as e:
    logger.warning(f"新架构不可用，将使用fallback模式: {str(e)}")
    ModelManager_class = None
    model_manager = None
    ModelRequestHandler = None
    MessageBuilder = None
    _request_handler_cache = {}
    NEW_ARCHITECTURE_AVAILABLE = False


class PayLoadTooLargeError(Exception):
    """自定义异常类，用于处理请求体过大错误"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return "请求体过大，请尝试压缩图片或减少输入内容。"


class RequestAbortException(Exception):
    """自定义异常类，用于处理请求中断异常"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message


class PermissionDeniedException(Exception):
    """自定义异常类，用于处理访问拒绝的异常"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message


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




class LLMRequest:
    """
    重构后的LLM请求类，基于新的model_manager和model_client架构
    保持向后兼容的API接口
    """
    
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

    def __init__(self, model: dict, **kwargs):
        """
        初始化LLM请求实例
        Args:
            model: 模型配置字典，兼容旧格式和新格式
            **kwargs: 额外参数
        """
        logger.debug(f"🔍 [模型初始化] 开始初始化模型: {model.get('model_name', model.get('name', 'Unknown'))}")
        logger.debug(f"🔍 [模型初始化] 模型配置: {model}")
        logger.debug(f"🔍 [模型初始化] 额外参数: {kwargs}")
        
        # 兼容新旧模型配置格式
        # 新格式使用 model_name，旧格式使用 name
        self.model_name: str = model.get("model_name", model.get("name", ""))
        # 在新架构中，provider信息从model_config.toml自动获取，不需要在这里设置
        self.provider = model.get("provider", "")  # 保留兼容性，但在新架构中不使用
        
        # 从全局配置中获取任务配置
        self.request_type = kwargs.pop("request_type", "default")
        
        # 确定使用哪个任务配置
        task_name = self._determine_task_name(model)
        
        # 初始化 request_handler
        self.request_handler = None
        
        # 尝试初始化新架构
        if NEW_ARCHITECTURE_AVAILABLE and ModelManager_class is not None:
            try:
                # 延迟初始化ModelManager
                global model_manager, _request_handler_cache
                if model_manager is None:
                    from src.config.config import model_config
                    model_manager = ModelManager_class(model_config)
                    logger.debug("🔍 [模型初始化] ModelManager延迟初始化成功")
                
                # 构建缓存键
                cache_key = (self.model_name, task_name)
                
                # 检查是否已有缓存的请求处理器
                if cache_key in _request_handler_cache:
                    self.request_handler = _request_handler_cache[cache_key]
                    logger.debug(f"🚀 [性能优化] 从LLMRequest缓存获取请求处理器: {cache_key}")
                else:
                    # 使用新架构获取模型请求处理器
                    self.request_handler = model_manager[task_name]
                    _request_handler_cache[cache_key] = self.request_handler
                    logger.debug(f"🔧 [性能优化] 创建并缓存LLMRequest请求处理器: {cache_key}")
                
                logger.debug(f"🔍 [模型初始化] 成功获取模型请求处理器，任务: {task_name}")
                self.use_new_architecture = True
            except Exception as e:
                logger.warning(f"无法使用新架构，任务 {task_name} 初始化失败: {e}")
                logger.warning("回退到兼容模式，某些功能可能受限")
                self.request_handler = None
                self.use_new_architecture = False
        else:
            logger.warning("新架构不可用，使用兼容模式")
            logger.warning("回退到兼容模式，某些功能可能受限")
            self.request_handler = None
            self.use_new_architecture = False
        
        # 保存原始参数用于向后兼容
        self.params = kwargs
        
        # 兼容性属性，从模型配置中提取
        # 新格式和旧格式都支持
        self.enable_thinking = model.get("enable_thinking", False)
        self.temp = model.get("temperature", model.get("temp", 0.7))  # 新格式用temperature，旧格式用temp
        self.thinking_budget = model.get("thinking_budget", 4096)
        self.stream = model.get("stream", False)
        self.pri_in = model.get("pri_in", 0)
        self.pri_out = model.get("pri_out", 0)
        self.max_tokens = model.get("max_tokens", global_config.model.model_max_output_length)
        
        # 记录配置文件中声明了哪些参数（不管值是什么）
        self.has_enable_thinking = "enable_thinking" in model
        self.has_thinking_budget = "thinking_budget" in model
        self.pri_out = model.get("pri_out", 0)
        self.max_tokens = model.get("max_tokens", global_config.model.model_max_output_length)
        
        # 记录配置文件中声明了哪些参数（不管值是什么）
        self.has_enable_thinking = "enable_thinking" in model
        self.has_thinking_budget = "thinking_budget" in model
        
        logger.debug("🔍 [模型初始化] 模型参数设置完成:")
        logger.debug(f"   - model_name: {self.model_name}")
        logger.debug(f"   - provider: {self.provider}")
        logger.debug(f"   - has_enable_thinking: {self.has_enable_thinking}")
        logger.debug(f"   - enable_thinking: {self.enable_thinking}")
        logger.debug(f"   - has_thinking_budget: {self.has_thinking_budget}")
        logger.debug(f"   - thinking_budget: {self.thinking_budget}")
        logger.debug(f"   - temp: {self.temp}")
        logger.debug(f"   - stream: {self.stream}")
        logger.debug(f"   - max_tokens: {self.max_tokens}")
        logger.debug(f"   - use_new_architecture: {self.use_new_architecture}")

        # 获取数据库实例
        self._init_database()
        
        logger.debug(f"🔍 [模型初始化] 初始化完成，request_type: {self.request_type}")

    def _determine_task_name(self, model: dict) -> str:
        """
        根据模型配置确定任务名称
        优先使用配置文件中明确定义的任务类型，避免基于模型名称的脆弱推断
        
        Args:
            model: 模型配置字典
        Returns:
            任务名称
        """
        # 方法1: 优先使用配置文件中明确定义的 task_type 字段
        if "task_type" in model:
            task_type = model["task_type"]
            logger.debug(f"🎯 [任务确定] 使用配置中的 task_type: {task_type}")
            return task_type
        
        # 方法2: 使用 capabilities 字段来推断主要任务类型
        if "capabilities" in model:
            capabilities = model["capabilities"]
            if isinstance(capabilities, list):
                # 按优先级顺序检查能力
                if "vision" in capabilities:
                    logger.debug(f"🎯 [任务确定] 从 capabilities {capabilities} 推断为: vision")
                    return "vision"
                elif "embedding" in capabilities:
                    logger.debug(f"🎯 [任务确定] 从 capabilities {capabilities} 推断为: embedding")
                    return "embedding"
                elif "speech" in capabilities:
                    logger.debug(f"🎯 [任务确定] 从 capabilities {capabilities} 推断为: speech")
                    return "speech"
                elif "text" in capabilities:
                    # 如果只有文本能力，则根据request_type细分
                    task = "llm_reasoning" if self.request_type == "reasoning" else "llm_normal"
                    logger.debug(f"🎯 [任务确定] 从 capabilities {capabilities} 和 request_type {self.request_type} 推断为: {task}")
                    return task
        
        # 方法3: 向后兼容 - 基于模型名称的关键字推断（不推荐但保留兼容性）
        model_name = model.get("model_name", model.get("name", ""))
        logger.warning(f"⚠️ [任务确定] 配置中未找到 task_type 或 capabilities，回退到基于模型名称的推断: {model_name}")
        logger.warning("⚠️ [建议] 请在 model_config.toml 中为模型添加明确的 task_type 或 capabilities 字段")
        
        # 保留原有的关键字匹配逻辑作为fallback
        if any(keyword in model_name.lower() for keyword in ["vlm", "vision", "gpt-4o", "claude", "vl-"]):
            logger.debug(f"🎯 [任务确定] 从模型名称 {model_name} 推断为: vision")
            return "vision"
        elif any(keyword in model_name.lower() for keyword in ["embed", "text-embedding", "bge-"]):
            logger.debug(f"🎯 [任务确定] 从模型名称 {model_name} 推断为: embedding")
            return "embedding" 
        elif any(keyword in model_name.lower() for keyword in ["whisper", "speech", "voice"]):
            logger.debug(f"🎯 [任务确定] 从模型名称 {model_name} 推断为: speech")
            return "speech"
        else:
            # 根据request_type确定，映射到配置文件中定义的任务
            task = "llm_reasoning" if self.request_type == "reasoning" else "llm_normal"
            logger.debug(f"🎯 [任务确定] 从 request_type {self.request_type} 推断为: {task}")
            return task

    @staticmethod
    def _init_database():
        """初始化数据库集合"""
        try:
            # 使用 Peewee 创建表，safe=True 表示如果表已存在则不会抛出错误
            db.create_tables([LLMUsage], safe=True)
            # logger.debug("LLMUsage 表已初始化/确保存在。")
        except Exception as e:
            logger.error(f"创建 LLMUsage 表失败: {str(e)}")

    def _record_usage(
        self,
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
                model_name=self.model_name,
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
                f"Token使用情况 - 模型: {self.model_name}, "
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

    @staticmethod
    def _extract_reasoning(content: str) -> Tuple[str, str]:
        """CoT思维链提取"""
        match = re.search(r"(?:<think>)?(.*?)</think>", content, re.DOTALL)
        content = re.sub(r"(?:<think>)?.*?</think>", "", content, flags=re.DOTALL, count=1).strip()
        reasoning = match[1].strip() if match else ""
        return content, reasoning

    # === 主要API方法 ===
    # 这些方法提供与新架构的桥接

    async def generate_response_for_image(self, prompt: str, image_base64: str, image_format: str) -> Tuple:
        """
        根据输入的提示和图片生成模型的异步响应
        使用新架构的模型请求处理器
        """
        if not self.use_new_architecture:
            raise RuntimeError(
                f"模型 {self.model_name} 无法使用新架构，请检查 config/model_config.toml 中的 API 配置。"
            )
        
        if self.request_handler is None:
            raise RuntimeError(
                f"模型 {self.model_name} 请求处理器未初始化，无法处理图片请求"
            )
        
        if MessageBuilder is None:
            raise RuntimeError("MessageBuilder不可用，请检查新架构配置")
            
        try:
            # 构建包含图片的消息
            message_builder = MessageBuilder()
            message_builder.add_text_content(prompt).add_image_content(
                image_format=image_format,
                image_base64=image_base64
            )
            messages = [message_builder.build()]
            
            # 使用新架构发送请求（只传递支持的参数）
            response = await self.request_handler.get_response(  # type: ignore
                messages=messages,
                tool_options=None,
                response_format=None
            )
            
            # 新架构返回的是 APIResponse 对象，直接提取内容
            content = response.content or ""
            reasoning_content = response.reasoning_content or ""
            tool_calls = response.tool_calls
            
            # 从内容中提取<think>标签的推理内容（向后兼容）
            if not reasoning_content and content:
                content, extracted_reasoning = self._extract_reasoning(content)
                reasoning_content = extracted_reasoning
            
            # 记录token使用情况
            if response.usage:
                self._record_usage(
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                    total_tokens=response.usage.total_tokens or 0,
                    user_id="system",
                    request_type=self.request_type,
                    endpoint="/chat/completions"
                )
            
            # 返回格式兼容旧版本
            if tool_calls:
                return content, reasoning_content, tool_calls
            else:
                return content, reasoning_content
            
        except Exception as e:
            logger.error(f"模型 {self.model_name} 图片响应生成失败: {str(e)}")
            # 向后兼容的异常处理
            if "401" in str(e) or "API key" in str(e):
                raise RuntimeError("API key 错误，认证失败，请检查 config/model_config.toml 中的 API key 配置是否正确") from e
            elif "429" in str(e):
                raise RuntimeError("请求过于频繁，请稍后再试") from e
            elif "500" in str(e) or "503" in str(e):
                raise RuntimeError("服务器负载过高，模型回复失败QAQ") from e
            else:
                raise RuntimeError(f"模型 {self.model_name} API请求失败: {str(e)}") from e

    async def generate_response_for_voice(self, voice_bytes: bytes) -> Tuple:
        """
        根据输入的语音文件生成模型的异步响应
        使用新架构的模型请求处理器
        """
        if not self.use_new_architecture:
            raise RuntimeError(
                f"模型 {self.model_name} 无法使用新架构，请检查 config/model_config.toml 中的 API 配置。"
            )
            
        if self.request_handler is None:
            raise RuntimeError(
                f"模型 {self.model_name} 请求处理器未初始化，无法处理语音请求"
            )
            
        try:
            # 构建语音识别请求参数
            # 注意：新架构中的语音识别可能使用不同的方法
            # 这里先使用get_response方法，可能需要根据实际API调整
            response = await self.request_handler.get_response(  # type: ignore
                messages=[],  # 语音识别可能不需要消息
                tool_options=None
            )
            
            # 新架构返回的是 APIResponse 对象，直接提取文本内容
            return (response.content,) if response.content else ("",)
            
        except Exception as e:
            logger.error(f"模型 {self.model_name} 语音识别失败: {str(e)}")
            # 向后兼容的异常处理
            if "401" in str(e) or "API key" in str(e):
                raise RuntimeError("API key 错误，认证失败，请检查 config/model_config.toml 中的 API key 配置是否正确") from e
            elif "429" in str(e):
                raise RuntimeError("请求过于频繁，请稍后再试") from e
            elif "500" in str(e) or "503" in str(e):
                raise RuntimeError("服务器负载过高，模型回复失败QAQ") from e
            else:
                raise RuntimeError(f"模型 {self.model_name} API请求失败: {str(e)}") from e

    async def generate_response_async(self, prompt: str, **kwargs) -> Union[str, Tuple]:
        """
        异步方式根据输入的提示生成模型的响应
        使用新架构的模型请求处理器，如无法使用则抛出错误
        """
        if not self.use_new_architecture:
            raise RuntimeError(
                f"模型 {self.model_name} 无法使用新架构，请检查 config/model_config.toml 中的 API 配置。"
            )
        
        if self.request_handler is None:
            raise RuntimeError(
                f"模型 {self.model_name} 请求处理器未初始化，无法生成响应"
            )
        
        if MessageBuilder is None:
            raise RuntimeError("MessageBuilder不可用，请检查新架构配置")
        
        try:
            # 构建消息
            message_builder = MessageBuilder()
            message_builder.add_text_content(prompt)
            messages = [message_builder.build()]
            
            # 使用新架构发送请求（只传递支持的参数）
            response = await self.request_handler.get_response(  # type: ignore
                messages=messages,
                tool_options=None,
                response_format=None
            )
            
            # 新架构返回的是 APIResponse 对象，直接提取内容
            content = response.content or ""
            reasoning_content = response.reasoning_content or ""
            tool_calls = response.tool_calls
            
            # 从内容中提取<think>标签的推理内容（向后兼容）
            if not reasoning_content and content:
                content, extracted_reasoning = self._extract_reasoning(content)
                reasoning_content = extracted_reasoning
            
            # 记录token使用情况
            if response.usage:
                self._record_usage(
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                    total_tokens=response.usage.total_tokens or 0,
                    user_id="system",
                    request_type=self.request_type,
                    endpoint="/chat/completions"
                )
            
            # 返回格式兼容旧版本
            if tool_calls:
                return content, (reasoning_content, self.model_name, tool_calls)
            else:
                return content, (reasoning_content, self.model_name)
            
        except Exception as e:
            logger.error(f"模型 {self.model_name} 生成响应失败: {str(e)}")
            # 向后兼容的异常处理
            if "401" in str(e) or "API key" in str(e):
                raise RuntimeError("API key 错误，认证失败，请检查 config/model_config.toml 中的 API key 配置是否正确") from e
            elif "429" in str(e):
                raise RuntimeError("请求过于频繁，请稍后再试") from e
            elif "500" in str(e) or "503" in str(e):
                raise RuntimeError("服务器负载过高，模型回复失败QAQ") from e
            else:
                raise RuntimeError(f"模型 {self.model_name} API请求失败: {str(e)}") from e

    async def get_embedding(self, text: str) -> Union[list, None]:
        """
        异步方法：获取文本的embedding向量
        使用新架构的模型请求处理器

        Args:
            text: 需要获取embedding的文本

        Returns:
            list: embedding向量，如果失败则返回None
        """
        if not text:
            logger.debug("该消息没有长度，不再发送获取embedding向量的请求")
            return None

        if not self.use_new_architecture:
            logger.warning(f"模型 {self.model_name} 无法使用新架构，embedding请求将被跳过")
            return None

        if self.request_handler is None:
            logger.warning(f"模型 {self.model_name} 请求处理器未初始化，embedding请求将被跳过")
            return None

        try:
            # 构建embedding请求参数
            # 使用新架构的get_embedding方法
            response = await self.request_handler.get_embedding(text)  # type: ignore
            
            # 新架构返回的是 APIResponse 对象，直接提取embedding
            if response.embedding:
                embedding = response.embedding
                
                # 记录token使用情况
                if response.usage:
                    self._record_usage(
                        prompt_tokens=response.usage.prompt_tokens or 0,
                        completion_tokens=response.usage.completion_tokens or 0,
                        total_tokens=response.usage.total_tokens or 0,
                        user_id="system",
                        request_type=self.request_type,
                        endpoint="/embeddings"
                    )
                
                return embedding
            else:
                logger.warning(f"模型 {self.model_name} 返回的embedding响应为空")
                return None
            
        except Exception as e:
            logger.error(f"模型 {self.model_name} 获取embedding失败: {str(e)}")
            # 向后兼容的异常处理
            if "401" in str(e) or "API key" in str(e):
                raise RuntimeError("API key 错误，认证失败，请检查 config/model_config.toml 中的 API key 配置是否正确") from e
            elif "429" in str(e):
                raise RuntimeError("请求过于频繁，请稍后再试") from e
            elif "500" in str(e) or "503" in str(e):
                raise RuntimeError("服务器负载过高，模型回复失败QAQ") from e
            else:
                logger.warning(f"模型 {self.model_name} embedding请求失败，返回None: {str(e)}")
                return None


def compress_base64_image_by_scale(base64_data: str, target_size: int = int(0.8 * 1024 * 1024)) -> str:
    """压缩base64格式的图片到指定大小
    Args:
        base64_data: base64编码的图片数据
        target_size: 目标文件大小（字节），默认0.8MB
    Returns:
        str: 压缩后的base64图片数据
    """
    try:
        # 将base64转换为字节数据
        # 确保base64字符串只包含ASCII字符
        if isinstance(base64_data, str):
            base64_data = base64_data.encode("ascii", errors="ignore").decode("ascii")
        image_data = base64.b64decode(base64_data)

        # 如果已经小于目标大小，直接返回原图
        if len(image_data) <= 2 * 1024 * 1024:
            return base64_data

        # 将字节数据转换为图片对象
        img = Image.open(io.BytesIO(image_data))

        # 获取原始尺寸
        original_width, original_height = img.size

        # 计算缩放比例
        scale = min(1.0, (target_size / len(image_data)) ** 0.5)

        # 计算新的尺寸
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)

        # 创建内存缓冲区
        output_buffer = io.BytesIO()

        # 如果是GIF，处理所有帧
        if getattr(img, "is_animated", False):
            frames = []
            n_frames = getattr(img, 'n_frames', 1)
            for frame_idx in range(n_frames):
                img.seek(frame_idx)
                new_frame = img.copy()
                new_frame = new_frame.resize((new_width // 2, new_height // 2), Image.Resampling.LANCZOS)  # 动图折上折
                frames.append(new_frame)

            # 保存到缓冲区
            frames[0].save(
                output_buffer,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                optimize=True,
                duration=img.info.get("duration", 100),
                loop=img.info.get("loop", 0),
            )
        else:
            # 处理静态图片
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 保存到缓冲区，保持原始格式
            if img.format == "PNG" and img.mode in ("RGBA", "LA"):
                resized_img.save(output_buffer, format="PNG", optimize=True)
            else:
                resized_img.save(output_buffer, format="JPEG", quality=95, optimize=True)

        # 获取压缩后的数据并转换为base64
        compressed_data = output_buffer.getvalue()
        logger.info(f"压缩图片: {original_width}x{original_height} -> {new_width}x{new_height}")
        logger.info(f"压缩前大小: {len(image_data) / 1024:.1f}KB, 压缩后大小: {len(compressed_data) / 1024:.1f}KB")

        return base64.b64encode(compressed_data).decode("utf-8")

    except Exception as e:
        logger.error(f"压缩图片失败: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        return base64_data
