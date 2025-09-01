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
    
    特点：
    - 发言频率调整：基于最近10分钟的数据，评估单位为"消息数/10分钟"
    - 专注度调整：基于最近10分钟的数据，评估单位为"消息数/10分钟"
    - 历史基准值：基于最近一周的数据，按小时统计，每小时都有独立的基准值（需要至少50条历史消息）
    - 统一标准：两个调整都使用10分钟窗口，确保逻辑一致性和响应速度
    - 双向调整：根据活跃度高低，既能提高也能降低频率和专注度
    - 数据充足性检查：当历史数据不足50条时，不更新基准值；当基准值为默认值时，不进行动态调整
    - 基准值更新：直接使用新计算的周均值，无平滑更新
    """
    
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.chat_stream: ChatStream = get_chat_manager().get_stream(self.chat_id)
        if not self.chat_stream:
            raise ValueError(f"无法找到聊天流: {chat_id}")
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
        
        # 动态基准值（将根据历史数据计算）
        self.base_message_count = 5   # 默认基准消息数量，将被动态更新
        self.base_user_count = 3      # 默认基准用户数量，将被动态更新
        
        # 平滑因子
        self.smoothing_factor = 0.3
        
        # 历史数据相关参数
        self._last_historical_update = 0
        self._historical_update_interval = 600  # 每十分钟更新一次历史基准值
        self._historical_days = 7  # 使用最近7天的数据计算基准值
        
        # 按小时统计的历史基准值
        self._hourly_baseline = {
            'messages': {},  # {0-23: 平均消息数}
            'users': {}      # {0-23: 平均用户数}
        }
        
        # 初始化24小时的默认基准值
        for hour in range(24):
            self._hourly_baseline['messages'][hour] = 0.0
            self._hourly_baseline['users'][hour] = 0.0

    def _update_historical_baseline(self):
        """
        更新基于历史数据的基准值
        使用最近一周的数据，按小时统计平均消息数量和用户数量
        """
        current_time = time.time()
        
        # 检查是否需要更新历史基准值
        if current_time - self._last_historical_update < self._historical_update_interval:
            return
            
        try:
            # 计算一周前的时间戳
            week_ago = current_time - (self._historical_days * 24 * 3600)
            
            # 获取最近一周的消息数据
            historical_messages = message_api.get_messages_by_time_in_chat(
                chat_id=self.chat_stream.stream_id,
                start_time=week_ago,
                end_time=current_time,
                filter_mai=True,
                filter_command=True
            )
            
            if historical_messages and len(historical_messages) >= 50:
                # 按小时统计消息数和用户数
                hourly_stats = {hour: {'messages': [], 'users': set()} for hour in range(24)}
                
                for msg in historical_messages:
                    # 获取消息的小时（UTC时间）
                    msg_time = time.localtime(msg.time)
                    msg_hour = msg_time.tm_hour
                    
                    # 统计消息数
                    hourly_stats[msg_hour]['messages'].append(msg)
                    
                    # 统计用户数
                    if msg.user_info and msg.user_info.user_id:
                        hourly_stats[msg_hour]['users'].add(msg.user_info.user_id)
                
                # 计算每个小时的平均值（基于一周的数据）
                for hour in range(24):
                    # 计算该小时的平均消息数（一周内该小时的总消息数 / 7天）
                    total_messages = len(hourly_stats[hour]['messages'])
                    total_users = len(hourly_stats[hour]['users'])
                    
                    # 只计算有消息的时段，没有消息的时段设为0
                    if total_messages > 0:
                        avg_messages = total_messages / self._historical_days
                        avg_users = total_users / self._historical_days
                        self._hourly_baseline['messages'][hour] = avg_messages
                        self._hourly_baseline['users'][hour] = avg_users
                    else:
                        # 没有消息的时段设为0，表示该时段不活跃
                        self._hourly_baseline['messages'][hour] = 0.0
                        self._hourly_baseline['users'][hour] = 0.0
                
                # 更新整体基准值（用于兼容性）- 基于原始数据计算，不受max(1.0)限制影响
                overall_avg_messages = sum(len(hourly_stats[hour]['messages']) for hour in range(24)) / (24 * self._historical_days)
                overall_avg_users = sum(len(hourly_stats[hour]['users']) for hour in range(24)) / (24 * self._historical_days)
                
                self.base_message_count = overall_avg_messages
                self.base_user_count = overall_avg_users
                
                logger.info(
                    f"{self.log_prefix} 历史基准值更新完成: "
                    f"整体平均消息数={overall_avg_messages:.2f}, 整体平均用户数={overall_avg_users:.2f}"
                )
                
                # 记录几个关键时段的基准值
                key_hours = [8, 12, 18, 22]  # 早、中、晚、夜
                for hour in key_hours:
                    # 计算该小时平均每10分钟的消息数和用户数
                    hourly_10min_messages = self._hourly_baseline['messages'][hour] / 6  # 1小时 = 6个10分钟
                    hourly_10min_users = self._hourly_baseline['users'][hour] / 6
                    logger.info(
                        f"{self.log_prefix} {hour}时基准值: "
                        f"消息数={self._hourly_baseline['messages'][hour]:.2f}/小时 "
                        f"({hourly_10min_messages:.2f}/10分钟), "
                        f"用户数={self._hourly_baseline['users'][hour]:.2f}/小时 "
                        f"({hourly_10min_users:.2f}/10分钟)"
                    )
                    
            elif historical_messages and len(historical_messages) < 50:
                # 历史数据不足50条，不更新基准值
                logger.info(f"{self.log_prefix} 历史数据不足50条({len(historical_messages)}条)，不更新基准值")
            else:
                # 如果没有历史数据，不更新基准值
                logger.info(f"{self.log_prefix} 无历史数据，不更新基准值")
                
        except Exception as e:
            logger.error(f"{self.log_prefix} 更新历史基准值时出错: {e}")
            # 出错时保持原有基准值不变
        
        self._last_historical_update = current_time

    def _get_current_hour_baseline(self) -> tuple[float, float]:
        """
        获取当前小时的基准值
        
        Returns:
            tuple: (基准消息数, 基准用户数)
        """
        current_hour = time.localtime().tm_hour
        return (
            self._hourly_baseline['messages'][current_hour],
            self._hourly_baseline['users'][current_hour]
        )

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
            
        # 先更新历史基准值
        self._update_historical_baseline()
        
        try:
            # 获取最近10分钟的数据（发言频率更敏感）
            recent_messages = message_api.get_messages_by_time_in_chat(
                chat_id=self.chat_stream.stream_id,
                start_time=current_time - 600,  # 10分钟前
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
            
            # 获取当前小时的基准值
            current_hour_base_messages, current_hour_base_users = self._get_current_hour_baseline()
            
            # 计算当前小时平均每10分钟的基准值
            current_hour_10min_messages = current_hour_base_messages / 6  # 1小时 = 6个10分钟
            current_hour_10min_users = current_hour_base_users / 6
            
            # 发言频率调整逻辑：根据活跃度双向调整
            # 检查是否有足够的数据进行分析
            if user_count > 0 and message_count >= 2:  # 至少需要2条消息才能进行有意义的分析
                # 检查历史基准值是否有效（该时段有活跃度）
                if current_hour_base_messages > 0.0 and current_hour_base_users > 0.0:
                    # 计算人均消息数（10分钟窗口）
                    messages_per_user = message_count / user_count
                    # 使用当前小时每10分钟的基准人均消息数
                    base_messages_per_user = current_hour_10min_messages / current_hour_10min_users if current_hour_10min_users > 0 else 1.0
                    
                    # 双向调整逻辑
                    if messages_per_user > base_messages_per_user * 1.2:
                        # 活跃度很高：提高回复频率
                        target_talk_adjust = min(self.max_adjust, messages_per_user / base_messages_per_user)
                    elif messages_per_user < base_messages_per_user * 0.8:
                        # 活跃度很低：降低回复频率
                        target_talk_adjust = max(self.min_adjust, messages_per_user / base_messages_per_user)
                    else:
                        # 活跃度正常：保持正常
                        target_talk_adjust = 1.0
                else:
                    # 历史基准值不足，不调整
                    target_talk_adjust = 1.0
            else:
                # 数据不足：不调整
                target_talk_adjust = 1.0
            
            # 限制调整范围
            target_talk_adjust = max(self.min_adjust, min(self.max_adjust, target_talk_adjust))
            
            # 记录调整前的值
            old_adjust = self.talk_frequency_adjust
            
            # 平滑调整
            self.talk_frequency_adjust = (
                self.talk_frequency_adjust * (1 - self.smoothing_factor) + 
                target_talk_adjust * self.smoothing_factor
            )
            
            # 判断调整方向
            if target_talk_adjust > 1.0:
                adjust_direction = "提高"
            elif target_talk_adjust < 1.0:
                adjust_direction = "降低"
            else:
                if current_hour_base_messages <= 0.0 or current_hour_base_users <= 0.0:
                    adjust_direction = "不调整(该时段无活跃度)"
                else:
                    adjust_direction = "保持"
            
            # 计算实际变化方向
            actual_change = ""
            if self.talk_frequency_adjust > old_adjust:
                actual_change = f"{old_adjust:.2f}x → {self.talk_frequency_adjust:.2f}x"
            elif self.talk_frequency_adjust < old_adjust:
                actual_change = f"{old_adjust:.2f}x → {self.talk_frequency_adjust:.2f}x"
            else:
                actual_change = f"无变化: {self.talk_frequency_adjust:.2f}x"
                
            logger.info(
                f"{self.log_prefix} 发言频率调整: "
                f"{user_count}名用户正在参与聊天，当前消息数: {message_count}|"
                f"群基准: {current_hour_10min_messages:.2f}消息/{current_hour_10min_users:.2f}用户|"
                f"[{adjust_direction}]{actual_change}"
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
            # 获取最近10分钟的数据（与发言频率保持一致）
            recent_messages = message_api.get_messages_by_time_in_chat(
                chat_id=self.chat_stream.stream_id,
                start_time=current_time - 600,  # 10分钟前
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
            
            # 获取当前小时的基准值
            current_hour_base_messages, current_hour_base_users = self._get_current_hour_baseline()
            
            # 计算当前小时平均每10分钟的基准值
            current_hour_10min_messages = current_hour_base_messages / 6  # 1小时 = 6个10分钟
            current_hour_10min_users = current_hour_base_users / 6
            
            # 专注度调整逻辑：根据活跃度双向调整
            # 检查是否有足够的数据进行分析
            if user_count > 0 and current_hour_10min_users > 0 and message_count >= 2:
                # 检查历史基准值是否有效（该时段有活跃度）
                if current_hour_base_messages > 0.0 and current_hour_base_users > 0.0:
                    # 计算用户活跃度比率（基于10分钟数据）
                    user_ratio = user_count / current_hour_10min_users
                    # 计算消息活跃度比率（基于10分钟数据）
                    message_ratio = message_count / current_hour_10min_messages if current_hour_10min_messages > 0 else 1.0
                    
                    # 双向调整逻辑
                    if user_ratio > 1.3 and message_ratio > 1.3:
                        # 活跃度很高：提高专注度，消耗更多LLM资源但回复更精准
                        target_focus_adjust = min(self.max_adjust, (user_ratio + message_ratio) / 2)
                    elif user_ratio > 1.1 and message_ratio > 1.1:
                        # 活跃度较高：适度提高专注度
                        target_focus_adjust = min(self.max_adjust, 1.0 + (user_ratio + message_ratio - 2.0) * 0.2)
                    elif user_ratio < 0.7 or message_ratio < 0.7:
                        # 活跃度很低：降低专注度，节省LLM资源
                        target_focus_adjust = max(self.min_adjust, min(user_ratio, message_ratio))
                    else:
                        # 正常情况：保持默认专注度
                        target_focus_adjust = 1.0
                else:
                    # 历史基准值不足，不调整
                    target_focus_adjust = 1.0
            else:
                # 数据不足：不调整
                target_focus_adjust = 1.0
            
            # 限制调整范围
            target_focus_adjust = max(self.min_adjust, min(self.max_adjust, target_focus_adjust))
            
            # 记录调整前的值
            old_focus_adjust = self.focus_value_adjust
            
            # 平滑调整
            self.focus_value_adjust = (
                self.focus_value_adjust * (1 - self.smoothing_factor) + 
                target_focus_adjust * self.smoothing_factor
            )
            
            # 计算当前小时平均每10分钟的基准值
            current_hour_10min_messages = current_hour_base_messages / 6  # 1小时 = 6个10分钟
            current_hour_10min_users = current_hour_base_users / 6
            
            # 判断调整方向
            if target_focus_adjust > 1.0:
                adjust_direction = "提高"
            elif target_focus_adjust < 1.0:
                adjust_direction = "降低"
            else:
                if current_hour_base_messages <= 0.0 or current_hour_base_users <= 0.0:
                    adjust_direction = "不调整(该时段无活跃度)"
                else:
                    adjust_direction = "保持"
            
            # 计算实际变化方向
            actual_change = ""
            if self.focus_value_adjust > old_focus_adjust:
                actual_change = f"{old_focus_adjust:.2f}x → {self.focus_value_adjust:.2f}x"
            elif self.focus_value_adjust < old_focus_adjust:
                actual_change = f"{old_focus_adjust:.2f}x → {self.focus_value_adjust:.2f}x"
            else:
                actual_change = f"无变化: {self.focus_value_adjust:.2f}x"
                
            logger.info(
                f"{self.log_prefix} 专注度调整: "
                f"{user_count}名用户正在参与聊天，当前消息数: {message_count}|"
                f"群基准: {current_hour_10min_messages:.2f}消息/{current_hour_10min_users:.2f}用户|"
                f"[{adjust_direction}]{actual_change}"
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
        update_interval: Optional[int] = None,
        historical_update_interval: Optional[int] = None,
        historical_days: Optional[int] = None
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
        if historical_update_interval is not None:
            self._historical_update_interval = max(300, historical_update_interval)  # 最少5分钟
        if historical_days is not None:
            self._historical_days = max(1, min(30, historical_days))  # 1-30天之间


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




