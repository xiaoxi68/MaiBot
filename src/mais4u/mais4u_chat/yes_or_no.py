from src.llm_models.utils_model import LLMRequest
from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.apis import send_api
logger = get_logger(__name__)

head_actions_list = [
    "不做额外动作",
    "点头一次",
    "点头两次",
    "摇头",
    "歪脑袋",
    "低头望向一边"
]

async def yes_or_no_head(text: str,emotion: str = "",chat_history: str = "",chat_id: str = ""):
    prompt = f"""
{chat_history}
以上是对方的发言：

对这个发言，你的心情是：{emotion}
对上面的发言，你的回复是：{text}
请判断时是否要伴随回复做头部动作，你可以选择：

不做额外动作
点头一次
点头两次
摇头
歪脑袋
低头望向一边

请从上面的动作中选择一个，并输出，请只输出你选择的动作就好，不要输出其他内容。"""
    model = LLMRequest(
            model=global_config.model.emotion,
            temperature=0.7,
            request_type="motion",
    )
    
    try:
        # logger.info(f"prompt: {prompt}")
        response, (reasoning_content, model_name) = await model.generate_response_async(prompt=prompt)
        logger.info(f"response: {response}")
        
        if response in head_actions_list:
            head_action = response
        else:
            head_action = "不做额外动作"
        
        await send_api.custom_to_stream(
            message_type="head_action",
            content=head_action,
            stream_id=chat_id,
            storage_message=False,
            show_log=True,
        )
        
        
        
    except Exception as e:
        logger.error(f"yes_or_no_head error: {e}")
        return "不做额外动作"
    

