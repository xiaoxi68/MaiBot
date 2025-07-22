
# 导入新插件系统
from src.plugin_system import BaseAction, ActionActivationType, ChatMode
from src.config.config import global_config
import random
import time
from typing import Tuple
import asyncio
import re
import traceback
# 导入依赖的系统组件
from src.common.logger import get_logger

# 导入API模块 - 标准Python包方式
from src.plugin_system.apis import generator_api, message_api
from src.plugins.built_in.core_actions.no_reply import NoReplyAction
from src.person_info.person_info import get_person_info_manager
from src.chat.mai_thinking.mai_think import mai_thinking_manager
from src.mais4u.constant_s4u import ENABLE_S4U

logger = get_logger("reply_action")

class ReplyAction(BaseAction):
    """回复动作 - 参与聊天回复"""

    # 激活设置
    focus_activation_type = ActionActivationType.NEVER
    normal_activation_type = ActionActivationType.NEVER
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
            if prepared_reply := self.action_data.get("prepared_reply", ""):
                reply_text = prepared_reply
            else:
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
            # 构建回复文本
            reply_text = ""
            first_replied = False
            reply_to_platform_id = f"{platform}:{user_id}"
            for reply_seg in reply_set:
                data = reply_seg[1]
                if not first_replied:
                    if need_reply:
                        await self.send_text(
                            content=data, reply_to=reply_to, reply_to_platform_id=reply_to_platform_id, typing=False
                        )
                    else:
                        await self.send_text(content=data, reply_to_platform_id=reply_to_platform_id, typing=False)
                    first_replied = True
                else:
                    await self.send_text(content=data, reply_to_platform_id=reply_to_platform_id, typing=True)
                reply_text += data

            # 存储动作记录
            reply_text = f"你对{person_name}进行了回复：{reply_text}"
            
            
            if ENABLE_S4U:
                await mai_thinking_manager.get_mai_think(self.chat_id).do_think_after_response(reply_text)
            

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