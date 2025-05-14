from typing import Dict, List, Optional, Callable, Coroutine, Type
from src.chat.focus_chat.planners.actions.base_action import BaseAction
from src.chat.focus_chat.planners.actions.reply_action import ReplyAction
from src.chat.focus_chat.planners.actions.no_reply_action import NoReplyAction
from src.chat.heart_flow.observation.observation import Observation
from src.chat.focus_chat.expressors.default_expressor import DefaultExpressor
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.focus_chat.heartFC_Cycleinfo import CycleDetail
from src.common.logger_manager import get_logger

logger = get_logger("action_factory")


class ActionFactory:
    """
    动作工厂类，用于创建各种类型的动作处理器
    """

    # 注册的动作处理器类映射
    _action_handlers: Dict[str, Type[BaseAction]] = {
        "reply": ReplyAction,
        "no_reply": NoReplyAction,
    }

    # 可用动作集定义（原ActionManager.DEFAULT_ACTIONS）
    DEFAULT_ACTIONS: Dict[str, str] = {
        "no_reply": "不操作，继续浏览",
        "reply": "表达想法，可以只包含文本、表情或两者都有",
    }
    _available_actions: Dict[str, str] = DEFAULT_ACTIONS.copy()
    _original_actions_backup: Optional[Dict[str, str]] = None

    @classmethod
    def register_action_handler(cls, action_name: str, handler_class: Type[BaseAction]) -> None:
        """
        注册新的动作处理器类

        Args:
            action_name: 动作名称
            handler_class: 处理器类，必须是BaseAction的子类
        """
        if not issubclass(handler_class, BaseAction):
            raise TypeError(f"{handler_class.__name__} 不是 BaseAction 的子类")

        cls._action_handlers[action_name] = handler_class
        logger.info(f"已注册动作处理器: {action_name} -> {handler_class.__name__}")

    @classmethod
    def create_action(
        cls,
        action_name: str,
        action_data: dict,
        reasoning: str,
        cycle_timers: dict,
        thinking_id: str,
        observations: List[Observation],
        expressor: DefaultExpressor,
        chat_stream: ChatStream,
        current_cycle: CycleDetail,
        log_prefix: str,
        on_consecutive_no_reply_callback: Callable[[], Coroutine[None, None, None]],
        total_no_reply_count: int = 0,
        total_waiting_time: float = 0.0,
        shutting_down: bool = False,
    ) -> Optional[BaseAction]:
        """
        创建动作处理器实例

        Args:
            action_name: 动作名称
            action_data: 动作数据
            reasoning: 执行理由
            cycle_timers: 计时器字典
            thinking_id: 思考ID
            observations: 观察列表
            expressor: 表达器
            chat_stream: 聊天流
            current_cycle: 当前循环信息
            log_prefix: 日志前缀
            on_consecutive_no_reply_callback: 连续不回复回调
            total_no_reply_count: 连续不回复计数
            total_waiting_time: 累计等待时间
            shutting_down: 是否正在关闭

        Returns:
            Optional[BaseAction]: 创建的动作处理器实例，如果动作名称未注册则返回None
        """
        handler_class = cls._action_handlers.get(action_name)
        if not handler_class:
            logger.warning(f"未注册的动作类型: {action_name}")
            return None

        try:
            if action_name == "reply":
                return handler_class(
                    action_name=action_name,
                    action_data=action_data,
                    reasoning=reasoning,
                    cycle_timers=cycle_timers,
                    thinking_id=thinking_id,
                    observations=observations,
                    expressor=expressor,
                    chat_stream=chat_stream,
                    current_cycle=current_cycle,
                    log_prefix=log_prefix,
                )
            elif action_name == "no_reply":
                return handler_class(
                    action_name=action_name,
                    action_data=action_data,
                    reasoning=reasoning,
                    cycle_timers=cycle_timers,
                    thinking_id=thinking_id,
                    observations=observations,
                    on_consecutive_no_reply_callback=on_consecutive_no_reply_callback,
                    current_cycle=current_cycle,
                    log_prefix=log_prefix,
                    total_no_reply_count=total_no_reply_count,
                    total_waiting_time=total_waiting_time,
                    shutting_down=shutting_down,
                )
            else:
                # 对于未来可能添加的其他动作类型，可以在这里扩展
                logger.warning(f"未实现的动作处理逻辑: {action_name}")
                return None

        except Exception as e:
            logger.error(f"创建动作处理器实例失败: {e}")
            return None

    @classmethod
    def get_available_actions(cls) -> Dict[str, str]:
        """获取当前可用的动作集"""
        return cls._available_actions.copy()

    @classmethod
    def add_action(cls, action_name: str, description: str) -> bool:
        """添加新的动作"""
        if action_name in cls._available_actions:
            return False
        cls._available_actions[action_name] = description
        return True

    @classmethod
    def remove_action(cls, action_name: str) -> bool:
        """移除指定动作"""
        if action_name not in cls._available_actions:
            return False
        del cls._available_actions[action_name]
        return True

    @classmethod
    def temporarily_remove_actions(cls, actions_to_remove: List[str]) -> None:
        """临时移除指定动作，备份原始动作集"""
        if cls._original_actions_backup is None:
            cls._original_actions_backup = cls._available_actions.copy()
        for name in actions_to_remove:
            cls._available_actions.pop(name, None)

    @classmethod
    def restore_actions(cls) -> None:
        """恢复之前备份的原始动作集"""
        if cls._original_actions_backup is not None:
            cls._available_actions = cls._original_actions_backup.copy()
            cls._original_actions_backup = None
