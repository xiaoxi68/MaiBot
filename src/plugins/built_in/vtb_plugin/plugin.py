from src.plugin_system.apis.plugin_register_api import register_plugin
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.component_types import ComponentInfo
from src.common.logger import get_logger
from src.plugin_system.base.base_action import BaseAction, ActionActivationType, ChatMode
from src.plugin_system.base.config_types import ConfigField
from typing import Tuple, List, Type

logger = get_logger("vtb")


class VTBAction(BaseAction):
    """VTB虚拟主播动作处理类"""

    action_name = "vtb_action"
    action_description = "使用虚拟主播预设动作表达心情或感觉，适用于需要生动表达情感的场景"
    action_parameters = {
        "text": "描述想要表达的心情或感觉的文本内容，必填，应当是对情感状态的自然描述",
    }
    action_require = [
        "当需要表达特定情感或心情时使用",
        "当用户明确要求使用虚拟主播动作时使用",
        "当回应内容需要更生动的情感表达时使用",
        "当想要通过预设动作增强互动体验时使用",
    ]
    enable_plugin = True  # 启用插件
    associated_types = ["vtb_text"]

    # 模式和并行控制
    mode_enable = ChatMode.ALL
    parallel_action = True  # VTB动作可以与回复并行执行，增强表达效果

    # 激活类型设置
    focus_activation_type = ActionActivationType.LLM_JUDGE  # Focus模式使用LLM判定，精确识别情感表达需求
    normal_activation_type = ActionActivationType.ALWAYS  # Normal模式使用随机激活，增加趣味性

    # LLM判定提示词（用于Focus模式）
    llm_judge_prompt = """
判定是否需要使用VTB虚拟主播动作的条件：
1. 当前聊天内容涉及明显的情感表达需求
2. 用户询问或讨论情感相关话题
3. 场景需要生动的情感回应
4. 当前回复内容可以通过VTB动作增强表达效果
4. 已经有足够的情感表达
"""

    # Random激活概率（用于Normal模式）
    random_activation_probability = 0.08  # 较低概率，避免过度使用

    async def execute(self) -> Tuple[bool, str]:
        """处理VTB虚拟主播动作"""
        logger.info(f"{self.log_prefix} 执行VTB动作: {self.reasoning}")

        # 获取要表达的心情或感觉文本
        text = self.action_data.get("text")

        if not text:
            logger.error(f"{self.log_prefix} 执行VTB动作时未提供文本内容")
            return False, "执行VTB动作失败：未提供文本内容"

        # 处理文本使其更适合VTB动作表达
        processed_text = self._process_text_for_vtb(text)

        try:
            # 发送VTB动作消息 - 使用新版本的send_type方法
            await self.send_custom(message_type="vtb_text", content=processed_text)

            logger.info(f"{self.log_prefix} VTB动作执行成功，文本内容: {processed_text}")
            return True, "VTB动作执行成功"

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行VTB动作时出错: {e}")
            return False, f"执行VTB动作时出错: {e}"

    def _process_text_for_vtb(self, text: str) -> str:
        """
        处理文本使其更适合VTB动作表达
        - 优化情感表达的准确性
        - 规范化心情描述格式
        - 确保文本适合虚拟主播动作系统理解
        """
        # 简单示例实现
        processed_text = text.strip()

        # 移除多余的空格和换行
        import re

        processed_text = re.sub(r"\s+", " ", processed_text)

        # 确保文本长度适中，避免过长的描述
        if len(processed_text) > 100:
            processed_text = processed_text[:100] + "..."

        # 如果文本为空，提供默认的情感描述
        if not processed_text:
            processed_text = "平静"

        return processed_text


@register_plugin
class VTBPlugin(BasePlugin):
    """VTB虚拟主播插件
    - 这是虚拟主播情感表达插件
    - Normal模式下依靠随机触发增加趣味性
    - Focus模式下由LLM判断触发，精确识别情感表达需求
    - 具有情感文本处理和优化能力
    """

    # 插件基本信息
    plugin_name = "vtb_plugin"  # 内部标识符
    enable_plugin = True
    dependencies = []  # 插件依赖列表
    python_dependencies = []  # Python包依赖列表
    config_file_name = "config.toml"

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本信息配置",
        "components": "组件启用配置",
        "vtb_action": "VTB动作专属配置",
        "logging": "日志记录配置",
    }

    # 配置Schema定义
    config_schema = {
        "plugin": {
            "name": ConfigField(type=str, default="vtb_plugin", description="插件名称", required=True),
            "version": ConfigField(type=str, default="0.1.0", description="插件版本号"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "description": ConfigField(type=str, default="虚拟主播情感表达插件", description="插件描述", required=True),
        },
        "components": {"enable_vtb": ConfigField(type=bool, default=True, description="是否启用VTB动作")},
        "vtb_action": {
            "random_activation_probability": ConfigField(
                type=float, default=0.08, description="Normal模式下，随机触发VTB动作的概率（0.0到1.0）", example=0.1
            ),
            "max_text_length": ConfigField(type=int, default=100, description="用于VTB动作的情感描述文本的最大长度"),
            "default_emotion": ConfigField(type=str, default="平静", description="当没有有效输入时，默认表达的情感"),
        },
        "logging": {
            "level": ConfigField(
                type=str, default="INFO", description="日志级别", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
            ),
            "prefix": ConfigField(type=str, default="[VTB]", description="日志记录前缀"),
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""

        # 从配置动态设置Action参数
        random_chance = self.get_config("vtb_action.random_activation_probability", 0.08)
        VTBAction.random_activation_probability = random_chance

        # 从配置获取组件启用状态
        enable_vtb = self.get_config("components.enable_vtb", True)
        components = []

        # 添加Action组件
        if enable_vtb:
            components.append(
                (
                    VTBAction.get_action_info(),
                    VTBAction,
                )
            )

        return components
