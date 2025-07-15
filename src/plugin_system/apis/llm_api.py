"""LLM API模块

提供了与LLM模型交互的功能
使用方式：
    from src.plugin_system.apis import llm_api
    models = llm_api.get_available_models()
    success, response, reasoning, model_name = await llm_api.generate_with_model(prompt, model_config)
"""

from typing import Tuple, Dict, Any
from src.common.logger import get_logger
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config

logger = get_logger("llm_api")

# =============================================================================
# LLM模型API函数
# =============================================================================




def get_available_models() -> Dict[str, Any]:
    """获取所有可用的模型配置

    Returns:
        Dict[str, Any]: 模型配置字典，key为模型名称，value为模型配置
    """
    try:
        if not hasattr(global_config, "model"):
            logger.error("[LLMAPI] 无法获取模型列表：全局配置中未找到 model 配置")
            return {}

        # 自动获取所有属性并转换为字典形式
        rets = {}
        models = global_config.model
        attrs = dir(models)
        for attr in attrs:
            if not attr.startswith("__"):
                try:
                    value = getattr(models, attr)
                    if not callable(value):  # 排除方法
                        rets[attr] = value
                except Exception as e:
                    logger.debug(f"[LLMAPI] 获取属性 {attr} 失败: {e}")
                    continue
        return rets

    except Exception as e:
        logger.error(f"[LLMAPI] 获取可用模型失败: {e}")
        return {}


async def generate_with_model(
    prompt: str, model_config: Dict[str, Any], request_type: str = "plugin.generate", **kwargs
) -> Tuple[bool, str, str, str]:
    """使用指定模型生成内容

    Args:
        prompt: 提示词
        model_config: 模型配置（从 get_available_models 获取的模型配置）
        request_type: 请求类型标识
        **kwargs: 其他模型特定参数，如temperature、max_tokens等

    Returns:
        Tuple[bool, str, str, str]: (是否成功, 生成的内容, 推理过程, 模型名称)
    """
    try:
        model_name = model_config.get("name")
        logger.info(f"[LLMAPI] 使用模型 {model_name} 生成内容")
        logger.debug(f"[LLMAPI] 完整提示词: {prompt}")

        llm_request = LLMRequest(model=model_config, request_type=request_type, **kwargs)

        response, (reasoning, model_name) = await llm_request.generate_response_async(prompt)
        return True, response, reasoning, model_name

    except Exception as e:
        error_msg = f"生成内容时出错: {str(e)}"
        logger.error(f"[LLMAPI] {error_msg}")
        return False, error_msg, "", ""
