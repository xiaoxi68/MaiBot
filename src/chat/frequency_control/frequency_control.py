import time
from typing import Optional, Dict, List
from src.plugin_system.apis import message_api
from src.chat.message_receive.chat_stream import ChatStream, get_chat_manager
from src.common.logger import get_logger
from src.config.config import global_config
from src.chat.frequency_control.talk_frequency_control import get_config_base_talk_frequency
from src.chat.frequency_control.focus_value_control import get_config_base_focus_value

logger = get_logger("frequency_control")


class FrequencyControl:
    """
    频率控制类，可以根据最近时间段的发言数量和发言人数动态调整频率
    """
    
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.chat_stream: ChatStream = get_chat_manager().get_stream(self.chat_id)
        if not self.chat_stream:
            raise ValueError(f"无法找到聊天流: {self.chat_id}")
        self.log_prefix = f"[{get_chat_manager().get_stream_name(self.chat_id) or self.chat_id}]"
        # 发言频率调整值
        self.talk_frequency_adjust: float = 1.0
        self.talk_frequency_external_adjust: float = 1.0
        # 专注度调整值
        self.focus_value_adjust: float = 1.0
        self.focus_value_external_adjust: float = 1.0
        
        # 动态调整相关参数
        self.last_update_time = time.time()
        self.update_interval = 60  # 每60秒更新一次
        
        # 历史数据缓存
        self._message_count_cache = 0
        self._user_count_cache = 0
        self._last_cache_time = 0
        self._cache_duration = 30  # 缓存30秒
        
        # 调整参数
        self.min_adjust = 0.3  # 最小调整值
        self.max_adjust = 2.0   # 最大调整值
        
        # 基准值（可根据实际情况调整）
        self.base_message_count = 5   # 基准消息数量
        self.base_user_count = 3      # 基准用户数量
        
        # 平滑因子
        self.smoothing_factor = 0.3


    def get_dynamic_talk_frequency_adjust(self) -> float:
        """
        获取纯动态调整值（不包含配置文件基础值）
        
        Returns:
            float: 动态调整值
        """
        self._update_talk_frequency_adjust()
        return self.talk_frequency_adjust

    def get_dynamic_focus_value_adjust(self) -> float:
        """
        获取纯动态调整值（不包含配置文件基础值）
        
        Returns:
            float: 动态调整值
        """
        self._update_focus_value_adjust()
        return self.focus_value_adjust

    def _update_talk_frequency_adjust(self):
        """
        更新发言频率调整值
        适合人少话多的时候：人少但消息多，提高回复频率
        """
        current_time = time.time()
        
        # 检查是否需要更新
        if current_time - self.last_update_time < self.update_interval:
            return
            
        try:
            # 获取最近30分钟的数据（发言频率更敏感）
            recent_messages = message_api.get_messages_by_time_in_chat(
                chat_id=self.chat_stream.stream_id,
                start_time=current_time - 1800,  # 30分钟前
                end_time=current_time,
                filter_mai=True,
                filter_command=True
            )
            
            # 计算消息数量和用户数量
            message_count = len(recent_messages)
            user_ids = set()
            for msg in recent_messages:
                if msg.user_info and msg.user_info.user_id:
                    user_ids.add(msg.user_info.user_id)
            user_count = len(user_ids)
            
            # 发言频率调整逻辑：人少话多时提高回复频率
            if user_count > 0:
                # 计算人均消息数
                messages_per_user = message_count / user_count
                # 基准人均消息数
                base_messages_per_user = self.base_message_count / self.base_user_count if self.base_user_count > 0 else 1.0
                
                # 如果人均消息数高，说明活跃度高，提高回复频率
                if messages_per_user > base_messages_per_user:
                    # 人少话多：提高回复频率
                    target_talk_adjust = min(self.max_adjust, messages_per_user / base_messages_per_user)
                else:
                    # 活跃度一般：保持正常
                    target_talk_adjust = 1.0
            else:
                target_talk_adjust = 1.0
            
            # 限制调整范围
            target_talk_adjust = max(self.min_adjust, min(self.max_adjust, target_talk_adjust))
            
            # 平滑调整
            self.talk_frequency_adjust = (
                self.talk_frequency_adjust * (1 - self.smoothing_factor) + 
                target_talk_adjust * self.smoothing_factor
            )
            
            logger.info(
                f"{self.log_prefix} 发言频率调整更新: "
                f"消息数={message_count}, 用户数={user_count}, "
                f"人均消息数={message_count/user_count if user_count > 0 else 0:.2f}, "
                f"调整值={self.talk_frequency_adjust:.2f}"
            )
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 更新发言频率调整值时出错: {e}")

    def _update_focus_value_adjust(self):
        """
        更新专注度调整值
        适合人多话多的时候：人多且消息多，提高专注度（LLM消耗更多，但回复更精准）
        """
        current_time = time.time()
        
        # 检查是否需要更新
        if current_time - self.last_update_time < self.update_interval:
            return
            
        try:
            # 获取最近1小时的数据
            recent_messages = message_api.get_messages_by_time_in_chat(
                chat_id=self.chat_stream.stream_id,
                start_time=current_time - 3600,  # 1小时前
                end_time=current_time,
                filter_mai=True,
                filter_command=True
            )
            
            # 计算消息数量和用户数量
            message_count = len(recent_messages)
            user_ids = set()
            for msg in recent_messages:
                if msg.user_info and msg.user_info.user_id:
                    user_ids.add(msg.user_info.user_id)
            user_count = len(user_ids)
            
            # 专注度调整逻辑：人多话多时提高专注度
            if user_count > 0 and self.base_user_count > 0:
                # 计算用户活跃度比率
                user_ratio = user_count / self.base_user_count
                # 计算消息活跃度比率
                message_ratio = message_count / self.base_message_count if self.base_message_count > 0 else 1.0
                
                # 如果用户多且消息多，提高专注度
                if user_ratio > 1.2 and message_ratio > 1.2:
                    # 人多话多：提高专注度，消耗更多LLM资源但回复更精准
                    target_focus_adjust = min(self.max_adjust, (user_ratio + message_ratio) / 2)
                elif user_ratio > 1.5:
                    # 用户特别多：适度提高专注度
                    target_focus_adjust = min(self.max_adjust, 1.0 + (user_ratio - 1.0) * 0.3)
                else:
                    # 正常情况：保持默认专注度
                    target_focus_adjust = 1.0
            else:
                target_focus_adjust = 1.0
            
            # 限制调整范围
            target_focus_adjust = max(self.min_adjust, min(self.max_adjust, target_focus_adjust))
            
            # 平滑调整
            self.focus_value_adjust = (
                self.focus_value_adjust * (1 - self.smoothing_factor) + 
                target_focus_adjust * self.smoothing_factor
            )
            
            logger.info(
                f"{self.log_prefix} 专注度调整更新: "
                f"消息数={message_count}, 用户数={user_count}, "
                f"用户比率={user_count/self.base_user_count if self.base_user_count > 0 else 0:.2f}, "
                f"消息比率={message_count/self.base_message_count if self.base_message_count > 0 else 0:.2f}, "
                f"调整值={self.focus_value_adjust:.2f}"
            )
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 更新专注度调整值时出错: {e}")

    def get_final_talk_frequency(self) -> float:
        return get_config_base_talk_frequency(self.chat_stream.stream_id) * self.get_dynamic_talk_frequency_adjust() * self.talk_frequency_external_adjust

    def get_final_focus_value(self) -> float:
        return get_config_base_focus_value(self.chat_stream.stream_id) * self.get_dynamic_focus_value_adjust() * self.focus_value_external_adjust


    def set_adjustment_parameters(
        self,
        min_adjust: Optional[float] = None,
        max_adjust: Optional[float] = None,
        base_message_count: Optional[int] = None,
        base_user_count: Optional[int] = None,
        smoothing_factor: Optional[float] = None,
        update_interval: Optional[int] = None
    ):
        """
        设置调整参数
        
        Args:
            min_adjust: 最小调整值
            max_adjust: 最大调整值
            base_message_count: 基准消息数量
            base_user_count: 基准用户数量
            smoothing_factor: 平滑因子
            update_interval: 更新间隔（秒）
        """
        if min_adjust is not None:
            self.min_adjust = max(0.1, min_adjust)
        if max_adjust is not None:
            self.max_adjust = max(1.0, max_adjust)
        if base_message_count is not None:
            self.base_message_count = max(1, base_message_count)
        if base_user_count is not None:
            self.base_user_count = max(1, base_user_count)
        if smoothing_factor is not None:
            self.smoothing_factor = max(0.0, min(1.0, smoothing_factor))
        if update_interval is not None:
            self.update_interval = max(10, update_interval)


class FrequencyControlManager:
    """
    频率控制管理器，管理多个聊天流的频率控制实例
    """
    
    def __init__(self):
        self.frequency_control_dict: Dict[str, FrequencyControl] = {}

    def get_or_create_frequency_control(self, chat_id: str) -> FrequencyControl:
        """
        获取或创建指定聊天流的频率控制实例
        
        Args:
            chat_id: 聊天流ID
            
        Returns:
            FrequencyControl: 频率控制实例
        """
        if chat_id not in self.frequency_control_dict:
            self.frequency_control_dict[chat_id] = FrequencyControl(chat_id)
        return self.frequency_control_dict[chat_id]

# 创建全局实例
frequency_control_manager = FrequencyControlManager()




