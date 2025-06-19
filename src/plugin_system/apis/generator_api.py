"""
回复器API模块

提供回复器相关功能，采用标准Python包设计模式
使用方式：
    from src.plugin_system.apis import generator_api
    replyer = generator_api.get_replyer(chat_stream)
    success, reply_set = await generator_api.generate_reply(chat_stream, action_data, reasoning)
"""

from typing import Tuple, Any, Dict, List
from src.common.logger import get_logger
from src.chat.focus_chat.replyer.default_generator import DefaultReplyer
from src.chat.message_receive.chat_stream import get_chat_manager

logger = get_logger("generator_api")



# =============================================================================
# 回复器获取API函数
# =============================================================================

def get_replyer(chat_stream=None, platform: str = None, chat_id: str = None, is_group: bool = True) -> DefaultReplyer:
    """获取回复器对象
    
    优先使用chat_stream，如果没有则使用platform和chat_id组合
    
    Args:
        chat_stream: 聊天流对象（优先）
        platform: 平台名称，如"qq"
        chat_id: 聊天ID（群ID或用户ID）
        is_group: 是否为群聊
        
    Returns:
        Optional[Any]: 回复器对象，如果获取失败则返回None
    """
    try:
        # 优先使用聊天流
        if chat_stream:
            logger.debug("[GeneratorAPI] 使用聊天流获取回复器")
            return DefaultReplyer(chat_stream=chat_stream)
        
        # 使用平台和ID组合
        if platform and chat_id:
            logger.debug("[GeneratorAPI] 使用平台和ID获取回复器")
            chat_manager = get_chat_manager()
            if not chat_manager:
                logger.warning("[GeneratorAPI] 无法获取聊天管理器")
                return None
                
            # 查找对应的聊天流
            target_stream = None
            for _stream_id, stream in chat_manager.streams.items():
                if stream.platform == platform:
                    if is_group and stream.group_info:
                        if str(stream.group_info.group_id) == str(chat_id):
                            target_stream = stream
                            break
                    elif not is_group and stream.user_info:
                        if str(stream.user_info.user_id) == str(chat_id):
                            target_stream = stream
                            break
            
            return DefaultReplyer(chat_stream=target_stream)
        
        logger.warning("[GeneratorAPI] 缺少必要参数，无法获取回复器")
        return None
        
    except Exception as e:
        logger.error(f"[GeneratorAPI] 获取回复器失败: {e}")
        return None

# =============================================================================
# 回复生成API函数
# =============================================================================

async def generate_reply(
    chat_stream=None,
    action_data: Dict[str, Any] = None,
    platform: str = None,
    chat_id: str = None,
    is_group: bool = True
) -> Tuple[bool, List[Tuple[str, Any]]]:
    """生成回复
    
    Args:
        chat_stream: 聊天流对象（优先）
        action_data: 动作数据
        reasoning: 推理原因
        thinking_id: 思考ID
        cycle_timers: 循环计时器
        anchor_message: 锚点消息
        platform: 平台名称（备用）
        chat_id: 聊天ID（备用）
        is_group: 是否为群聊（备用）
        
    Returns:
        Tuple[bool, List[Tuple[str, Any]]]: (是否成功, 回复集合)
    """
    try:
        # 获取回复器
        replyer = get_replyer(chat_stream, platform, chat_id, is_group)
        if not replyer:
            logger.error("[GeneratorAPI] 无法获取回复器")
            return False, []
        
        logger.info("[GeneratorAPI] 开始生成回复")
        
        # 调用回复器生成回复
        success, reply_set = await replyer.generate_reply_with_context(
            reply_data=action_data or {},
        )
        
        if success:
            logger.info(f"[GeneratorAPI] 回复生成成功，生成了 {len(reply_set)} 个回复项")
        else:
            logger.warning("[GeneratorAPI] 回复生成失败")
        
        return success, reply_set or []
        
    except Exception as e:
        logger.error(f"[GeneratorAPI] 生成回复时出错: {e}")
        return False, []

async def rewrite_reply(
    chat_stream=None,
    reply_data: Dict[str, Any] = None,
    platform: str = None,
    chat_id: str = None,
    is_group: bool = True
) -> Tuple[bool, List[Tuple[str, Any]]]:
    """重写回复
    
    Args:
        chat_stream: 聊天流对象（优先）
        action_data: 动作数据
        platform: 平台名称（备用）
        chat_id: 聊天ID（备用）
        is_group: 是否为群聊（备用）
        
    Returns:
        Tuple[bool, List[Tuple[str, Any]]]: (是否成功, 回复集合)
    """
    try:
        # 获取回复器
        replyer = get_replyer(chat_stream, platform, chat_id, is_group)
        if not replyer:
            logger.error("[GeneratorAPI] 无法获取回复器")
            return False, []
        
        logger.info("[GeneratorAPI] 开始重写回复")
        
        # 调用回复器重写回复
        success, reply_set = await replyer.rewrite_reply_with_context(
            reply_data=reply_data or {},
        )
        
        if success:
            logger.info(f"[GeneratorAPI] 重写回复成功，生成了 {len(reply_set)} 个回复项")
        else:
            logger.warning("[GeneratorAPI] 重写回复失败")
        
        return success, reply_set or []
    
    except Exception as e:
        logger.error(f"[GeneratorAPI] 重写回复时出错: {e}")
        return False, []
    

