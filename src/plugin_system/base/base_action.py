from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional
from src.common.logger_manager import get_logger
from src.plugin_system.apis.plugin_api import PluginAPI
from src.plugin_system.base.component_types import ActionActivationType, ChatMode, ActionInfo, ComponentType

logger = get_logger("base_action")

class BaseAction(ABC):
    """Action组件基类
    
    Action是插件的一种组件类型，用于处理聊天中的动作逻辑
    
    子类可以通过类属性定义激活条件：
    - focus_activation_type: 专注模式激活类型
    - normal_activation_type: 普通模式激活类型
    - activation_keywords: 激活关键词列表
    - keyword_case_sensitive: 关键词是否区分大小写
    - mode_enable: 启用的聊天模式
    - parallel_action: 是否允许并行执行
    - random_activation_probability: 随机激活概率
    - llm_judge_prompt: LLM判断提示词
    """
    
    # 默认激活设置（子类可以覆盖）
    focus_activation_type: ActionActivationType = ActionActivationType.NEVER
    normal_activation_type: ActionActivationType = ActionActivationType.NEVER
    activation_keywords: list = []
    keyword_case_sensitive: bool = False
    mode_enable: ChatMode = ChatMode.ALL
    parallel_action: bool = True
    random_activation_probability: float = 0.0
    llm_judge_prompt: str = ""
    
    def __init__(self, 
                 action_data: dict, 
                 reasoning: str, 
                 cycle_timers: dict, 
                 thinking_id: str,
                 **kwargs):
        """初始化Action组件
        
        Args:
            action_data: 动作数据
            reasoning: 执行该动作的理由
            cycle_timers: 计时器字典
            thinking_id: 思考ID
            **kwargs: 其他参数（包含服务对象）
        """
        self.action_data = action_data
        self.reasoning = reasoning
        self.cycle_timers = cycle_timers
        self.thinking_id = thinking_id
        
        # 创建API实例
        self.api = PluginAPI(
            chat_stream=kwargs.get("chat_stream"),
            expressor=kwargs.get("expressor"), 
            replyer=kwargs.get("replyer"),
            observations=kwargs.get("observations"),
            log_prefix=kwargs.get("log_prefix", "")
        )
        
        self.log_prefix = kwargs.get("log_prefix", "")
        
        logger.debug(f"{self.log_prefix} Action组件初始化完成")
    
    async def send_reply(self, content: str) -> bool:
        """发送回复消息
        
        Args:
            content: 回复内容
            
        Returns:
            bool: 是否发送成功
        """
        return await self.api.send_message("text", content)
    
    @classmethod
    def get_action_info(cls, name: str = None, description: str = None) -> 'ActionInfo':
        """从类属性生成ActionInfo
        
        Args:
            name: Action名称，如果不提供则使用类名
            description: Action描述，如果不提供则使用类文档字符串
            
        Returns:
            ActionInfo: 生成的Action信息对象
        """

        
        # 自动生成名称和描述
        if name is None:
            name = cls.__name__.lower().replace('action', '')
        if description is None:
            description = cls.__doc__ or f"{cls.__name__} Action组件"
            description = description.strip().split('\n')[0]  # 取第一行作为描述
        
        return ActionInfo(
            name=name,
            component_type=ComponentType.ACTION,
            description=description,
            focus_activation_type=cls.focus_activation_type,
            normal_activation_type=cls.normal_activation_type,
            activation_keywords=cls.activation_keywords.copy() if cls.activation_keywords else [],
            keyword_case_sensitive=cls.keyword_case_sensitive,
            mode_enable=cls.mode_enable,
            parallel_action=cls.parallel_action,
            random_activation_probability=cls.random_activation_probability,
            llm_judge_prompt=cls.llm_judge_prompt
        )
    
    @abstractmethod
    async def execute(self) -> Tuple[bool, str]:
        """执行Action的抽象方法，子类必须实现
        
        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        pass 