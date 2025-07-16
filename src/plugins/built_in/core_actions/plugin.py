"""
核心动作插件

将系统核心动作（reply、no_reply、emoji）转换为新插件系统格式
这是系统的内置插件，提供基础的聊天交互功能
"""

import random
import time
from typing import List, Tuple, Type
import asyncio
import re
import traceback

# 导入新插件系统
from src.plugin_system import BasePlugin, register_plugin, BaseAction, ComponentInfo, ActionActivationType, ChatMode
from src.plugin_system.base.config_types import ConfigField
from src.config.config import global_config

# 导入依赖的系统组件
from src.common.logger import get_logger

# 导入API模块 - 标准Python包方式
from src.plugin_system.apis import generator_api, message_api
from src.plugins.built_in.core_actions.no_reply import NoReplyAction
from src.plugins.built_in.core_actions.emoji import EmojiAction
from src.person_info.person_info import get_person_info_manager

logger = get_logger("core_actions")

# 常量定义
WAITING_TIME_THRESHOLD = 1200  # 等待新消息时间阈值，单位秒


class ReplyAction(BaseAction):
    """回复动作 - 参与聊天回复"""

    # 激活设置
    focus_activation_type = ActionActivationType.ALWAYS
    normal_activation_type = ActionActivationType.ALWAYS
    mode_enable = ChatMode.FOCUS
    parallel_action = False

    # 动作基本信息
    action_name = "reply"
    action_description = "参与聊天回复，发送文本进行表达"

    # 动作参数定义
    action_parameters = {}

    # 动作使用场景
    action_require = ["你想要闲聊或者随便附和", "有人提到你", "如果你刚刚进行了回复，不要对同一个话题重复回应"]

    # 关联类型
    associated_types = ["text"]

    def _parse_reply_target(self, target_message: str) -> tuple:
        sender = ""
        target = ""
        if ":" in target_message or "：" in target_message:
            # 使用正则表达式匹配中文或英文冒号
            parts = re.split(pattern=r"[:：]", string=target_message, maxsplit=1)
            if len(parts) == 2:
                sender = parts[0].strip()
                target = parts[1].strip()
        return sender, target

    async def execute(self) -> Tuple[bool, str]:
        """执行回复动作"""
        logger.info(f"{self.log_prefix} 决定进行回复")
        start_time = self.action_data.get("loop_start_time", time.time())

        user_id = self.user_id
        platform = self.platform
        # logger.info(f"{self.log_prefix} 用户ID: {user_id}, 平台: {platform}")
        person_id = get_person_info_manager().get_person_id(platform, user_id)
        # logger.info(f"{self.log_prefix} 人物ID: {person_id}")
        person_name = get_person_info_manager().get_value_sync(person_id, "person_name")
        reply_to = f"{person_name}:{self.action_message.get('processed_plain_text', '')}"
        logger.info(f"{self.log_prefix} 回复目标: {reply_to}")

        try:
            prepared_reply = self.action_data.get("prepared_reply", "")
            if not prepared_reply:
                try:
                    success, reply_set, _ = await asyncio.wait_for(
                        generator_api.generate_reply(
                            extra_info="",
                            reply_to=reply_to,
                            chat_id=self.chat_id,
                            request_type="chat.replyer.focus",
                            enable_tool=global_config.tool.enable_in_focus_chat,
                        ),
                        timeout=global_config.chat.thinking_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"{self.log_prefix} 回复生成超时 ({global_config.chat.thinking_timeout}s)")
                    return False, "timeout"

                # 检查从start_time以来的新消息数量
                # 获取动作触发时间或使用默认值
                current_time = time.time()
                new_message_count = message_api.count_new_messages(
                    chat_id=self.chat_id, start_time=start_time, end_time=current_time
                )

                # 根据新消息数量决定是否使用reply_to
                need_reply = new_message_count >= random.randint(2, 4)
                logger.info(
                    f"{self.log_prefix} 从思考到回复，共有{new_message_count}条新消息，{'使用' if need_reply else '不使用'}引用回复"
                )
            else:
                reply_text = prepared_reply

            # 构建回复文本
            reply_text = ""
            first_replied = False
            for reply_seg in reply_set:
                data = reply_seg[1]
                if not first_replied:
                    if need_reply:
                        await self.send_text(content=data, reply_to=reply_to, typing=False)
                        first_replied = True
                    else:
                        await self.send_text(content=data, typing=False)
                        first_replied = True
                else:
                    await self.send_text(content=data, typing=True)
                reply_text += data

            # 存储动作记录
            reply_text = f"你对{person_name}进行了回复：{reply_text}"

            await self.store_action_info(
                action_build_into_prompt=False,
                action_prompt_display=reply_text,
                action_done=True,
            )

            # 重置NoReplyAction的连续计数器
            NoReplyAction.reset_consecutive_count()

            return success, reply_text

        except Exception as e:
            logger.error(f"{self.log_prefix} 回复动作执行失败: {e}")
            traceback.print_exc()
            return False, f"回复失败: {str(e)}"


@register_plugin
class CoreActionsPlugin(BasePlugin):
    """核心动作插件

    系统内置插件，提供基础的聊天交互功能：
    - Reply: 回复动作
    - NoReply: 不回复动作
    - Emoji: 表情动作

    注意：插件基本信息优先从_manifest.json文件中读取
    """

    # 插件基本信息
    plugin_name = "core_actions"  # 内部标识符
    enable_plugin = True
    dependencies = []  # 插件依赖列表
    python_dependencies = []  # Python包依赖列表
    config_file_name = "config.toml"

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件启用配置",
        "components": "核心组件启用配置",
    }

    # 配置Schema定义
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="0.4.0", description="配置文件版本"),
        },
        "components": {
            "enable_reply": ConfigField(type=bool, default=True, description="是否启用回复动作"),
            "enable_no_reply": ConfigField(type=bool, default=True, description="是否启用不回复动作"),
            "enable_emoji": ConfigField(type=bool, default=True, description="是否启用发送表情/图片动作"),
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""

        # --- 从配置动态设置Action/Command ---
        emoji_chance = global_config.emoji.emoji_chance
        if global_config.emoji.emoji_activate_type == "random":
            EmojiAction.random_activation_probability = emoji_chance
            EmojiAction.focus_activation_type = ActionActivationType.RANDOM
            EmojiAction.normal_activation_type = ActionActivationType.RANDOM
        elif global_config.emoji.emoji_activate_type == "llm":
            EmojiAction.random_activation_probability = 0.0
            EmojiAction.focus_activation_type = ActionActivationType.LLM_JUDGE
            EmojiAction.normal_activation_type = ActionActivationType.LLM_JUDGE

        # --- 根据配置注册组件 ---
        components = []
        if self.get_config("components.enable_reply", True):
            components.append((ReplyAction.get_action_info(), ReplyAction))
        if self.get_config("components.enable_no_reply", True):
            components.append((NoReplyAction.get_action_info(), NoReplyAction))
        if self.get_config("components.enable_emoji", True):
            components.append((EmojiAction.get_action_info(), EmojiAction))

        # components.append((DeepReplyAction.get_action_info(), DeepReplyAction))

        return components
