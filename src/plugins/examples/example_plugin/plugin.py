"""
综合示例插件

将旧的示例插件功能重写为新插件系统架构，展示完整的插件开发模式。

包含功能：
- 智能问候Action
- 帮助系统Command
- 消息发送Command
- 状态查询Command
- 回声Command
- 自定义前缀Command
- 消息信息查询Command
- 高级消息发送Command

演示新插件系统的完整功能：
- Action和Command组件的定义
- 拦截控制功能
- 配置驱动的行为
- API的多种使用方式
- 日志和错误处理
"""

from typing import List, Tuple, Type, Optional
import time
import random

# 导入新插件系统
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.base_plugin import register_plugin
from src.plugin_system.base.base_action import BaseAction
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ComponentInfo, ActionActivationType, ChatMode
from src.common.logger import get_logger

logger = get_logger("example_comprehensive")


# ===== Action组件 =====


class SmartGreetingAction(BaseAction):
    """智能问候Action - 基于关键词触发的问候系统"""

    # 激活设置
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["你好", "hello", "hi", "嗨", "问候", "早上好", "晚上好"]
    keyword_case_sensitive = False
    mode_enable = ChatMode.ALL
    parallel_action = False

    # Action参数定义
    action_parameters = {"username": "要问候的用户名（可选）"}

    # Action使用场景
    action_require = ["用户发送包含问候词汇的消息", "检测到新用户加入时", "响应友好交流需求"]


# ===== Command组件 =====


class ComprehensiveHelpCommand(BaseCommand):
    """综合帮助系统 - 显示所有可用命令和Action"""

    command_pattern = r"^/help(?:\s+(?P<command>\w+))?$"
    command_help = "显示所有命令帮助或特定命令详情，用法：/help [命令名]"
    command_examples = ["/help", "/help send", "/help status"]
    intercept_message = True  # 拦截消息，不继续处理

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行帮助命令"""
        try:
            command_name = self.matched_groups.get("command")

            if command_name:
                # 显示特定命令帮助
                return await self._show_specific_help(command_name)
            else:
                # 显示所有命令概览
                return await self._show_all_commands()

        except Exception as e:
            logger.error(f"{self.log_prefix} 帮助命令执行失败: {e}")
            await self.send_reply(f"❌ 帮助系统错误: {str(e)}")
            return False, str(e)

    async def _show_specific_help(self, command_name: str) -> Tuple[bool, str]:
        """显示特定命令的详细帮助"""
        # 这里可以扩展为动态获取所有注册的Command信息
        help_info = {
            "help": {"description": "显示帮助信息", "usage": "/help [命令名]", "examples": ["/help", "/help send"]},
            "send": {
                "description": "发送消息到指定目标",
                "usage": "/send <group|user> <ID> <消息内容>",
                "examples": ["/send group 123456 你好", "/send user 789456 私聊"],
            },
            "status": {
                "description": "查询系统状态",
                "usage": "/status [类型]",
                "examples": ["/status", "/status 系统", "/status 插件"],
            },
        }

        info = help_info.get(command_name.lower())
        if not info:
            response = f"❌ 未找到命令: {command_name}\n使用 /help 查看所有可用命令"
        else:
            response = f"""
📖 命令帮助: {command_name}

📝 描述: {info["description"]}
⚙️ 用法: {info["usage"]}
💡 示例:
{chr(10).join(f"  • {example}" for example in info["examples"])}
            """.strip()

        await self.send_reply(response)
        return True, response

    async def _show_all_commands(self) -> Tuple[bool, str]:
        """显示所有可用命令"""
        help_text = """
🤖 综合示例插件 - 命令帮助

📝 可用命令:
• /help [命令] - 显示帮助信息
• /send <目标类型> <ID> <消息> - 发送消息
• /status [类型] - 查询系统状态  
• /echo <消息> - 回声重复消息
• /info - 查询当前消息信息
• /prefix <前缀> <内容> - 自定义前缀消息

🎯 智能功能:
• 智能问候 - 关键词触发自动问候
• 状态监控 - 实时系统状态查询
• 消息转发 - 跨群聊/私聊消息发送

⚙️ 拦截控制:
• 部分命令拦截消息处理（如 /help）
• 部分命令允许继续处理（如 /log）

💡 使用 /help <命令名> 获取特定命令的详细说明
        """.strip()

        await self.send_reply(help_text)
        return True, help_text


class MessageSendCommand(BaseCommand):
    """消息发送Command - 向指定群聊或私聊发送消息"""

    command_pattern = r"^/send\s+(?P<target_type>group|user)\s+(?P<target_id>\d+)\s+(?P<content>.+)$"
    command_help = "向指定群聊或私聊发送消息，用法：/send <group|user> <ID> <消息内容>"
    command_examples = [
        "/send group 123456789 大家好！",
        "/send user 987654321 私聊消息",
        "/send group 555666777 这是来自插件的消息",
    ]
    intercept_message = True  # 拦截消息处理

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行消息发送"""
        try:
            target_type = self.matched_groups.get("target_type")
            target_id = self.matched_groups.get("target_id")
            content = self.matched_groups.get("content")

            if not all([target_type, target_id, content]):
                await self.send_reply("❌ 命令参数不完整，请检查格式")
                return False, "参数不完整"

            # 长度限制检查
            max_length = self.api.get_config("send.max_message_length", 500)
            if len(content) > max_length:
                await self.send_reply(f"❌ 消息过长，最大长度: {max_length} 字符")
                return False, "消息过长"

            logger.info(f"{self.log_prefix} 发送消息: {target_type}:{target_id} -> {content[:50]}...")

            # 根据目标类型发送消息
            if target_type == "group":
                success = await self.api.send_text_to_group(text=content, group_id=target_id, platform="qq")
                target_desc = f"群聊 {target_id}"
            elif target_type == "user":
                success = await self.api.send_text_to_user(text=content, user_id=target_id, platform="qq")
                target_desc = f"用户 {target_id}"
            else:
                await self.send_reply(f"❌ 不支持的目标类型: {target_type}")
                return False, f"不支持的目标类型: {target_type}"

            # 返回结果
            if success:
                response = f"✅ 消息已成功发送到 {target_desc}"
                await self.send_reply(response)
                return True, response
            else:
                response = f"❌ 消息发送失败，目标 {target_desc} 可能不存在"
                await self.send_reply(response)
                return False, response

        except Exception as e:
            logger.error(f"{self.log_prefix} 消息发送失败: {e}")
            error_msg = f"❌ 发送失败: {str(e)}"
            await self.send_reply(error_msg)
            return False, str(e)


class DiceCommand(BaseCommand):
    """骰子命令，使用!前缀而不是/前缀"""

    command_pattern = r"^[!！](?:dice|骰子)(?:\s+(?P<count>\d+))?$"  # 匹配 !dice 或 !骰子，可选参数为骰子数量
    command_help = "使用方法: !dice [数量] 或 !骰子 [数量] - 掷骰子，默认掷1个"
    command_examples = ["!dice", "!骰子", "!dice 3", "！骰子 5"]
    intercept_message = True  # 拦截消息处理

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行骰子命令

        Returns:
            Tuple[bool, Optional[str]]: (是否执行成功, 回复消息)
        """
        try:
            # 获取骰子数量，默认为1
            count_str = self.matched_groups.get("count")

            # 确保count_str不为None
            if count_str is None:
                count = 1  # 默认值
            else:
                try:
                    count = int(count_str)
                    if count <= 0:
                        response = "❌ 骰子数量必须大于0"
                        await self.send_reply(response)
                        return False, response
                    if count > 10:  # 限制最大数量
                        response = "❌ 一次最多只能掷10个骰子"
                        await self.send_reply(response)
                        return False, response
                except ValueError:
                    response = "❌ 骰子数量必须是整数"
                    await self.send_reply(response)
                    return False, response

            # 生成随机数
            results = [random.randint(1, 6) for _ in range(count)]

            # 构建回复消息
            if count == 1:
                message = f"🎲 掷出了 {results[0]} 点"
            else:
                dice_results = ", ".join(map(str, results))
                total = sum(results)
                message = f"🎲 掷出了 {count} 个骰子: [{dice_results}]，总点数: {total}"

            await self.send_reply(message)
            logger.info(f"{self.log_prefix} 执行骰子命令: {message}")
            return True, message

        except Exception as e:
            error_msg = f"❌ 执行命令时出错: {str(e)}"
            await self.send_reply(error_msg)
            logger.error(f"{self.log_prefix} 执行骰子命令时出错: {e}")
            return False, error_msg


class EchoCommand(BaseCommand):
    """回声Command - 重复用户输入的消息"""

    command_pattern = r"^/echo\s+(?P<message>.+)$"
    command_help = "重复你的消息内容，用法：/echo <消息内容>"
    command_examples = ["/echo Hello World", "/echo 你好世界", "/echo 测试回声"]
    intercept_message = True  # 拦截消息处理

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行回声命令"""
        try:
            message = self.matched_groups.get("message", "")

            if not message:
                response = "❌ 请提供要重复的消息！用法：/echo <消息内容>"
                await self.send_reply(response)
                return False, response

            # 检查消息长度限制
            max_length = self.api.get_config("echo.max_length", 200)
            if len(message) > max_length:
                response = f"❌ 消息过长，最大长度: {max_length} 字符"
                await self.send_reply(response)
                return False, response

            # 格式化回声消息
            enable_formatting = self.api.get_config("echo.enable_formatting", True)
            if enable_formatting:
                response = f"🔊 回声: {message}"
            else:
                response = message

            await self.send_reply(response)
            logger.info(f"{self.log_prefix} 回声消息: {message}")
            return True, response

        except Exception as e:
            logger.error(f"{self.log_prefix} 回声命令失败: {e}")
            error_msg = f"❌ 回声失败: {str(e)}"
            await self.send_reply(error_msg)
            return False, str(e)


class MessageInfoCommand(BaseCommand):
    """消息信息Command - 显示当前消息的详细信息"""

    command_pattern = r"^/info$"
    command_help = "显示当前消息的详细信息"
    command_examples = ["/info"]
    intercept_message = True  # 拦截消息处理

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行消息信息查询"""
        try:
            message = self.message

            # 收集消息信息
            user_info = message.message_info.user_info
            group_info = message.message_info.group_info

            info_parts = [
                "📋 消息信息详情",
                "",
                "👤 用户信息:",
                f"  • ID: {user_info.user_id}",
                f"  • 昵称: {user_info.user_nickname}",
                f"  • 群名片: {getattr(user_info, 'user_cardname', '无')}",
                f"  • 平台: {message.message_info.platform}",
                "",
                "💬 消息信息:",
                f"  • 消息ID: {message.message_info.message_id}",
                f"  • 时间戳: {message.message_info.time}",
                f"  • 原始内容: {message.processed_plain_text[:100]}{'...' if len(message.processed_plain_text) > 100 else ''}",
                f"  • 是否表情: {'是' if getattr(message, 'is_emoji', False) else '否'}",
            ]

            # 群聊信息
            if group_info:
                info_parts.extend(
                    [
                        "",
                        "👥 群聊信息:",
                        f"  • 群ID: {group_info.group_id}",
                        f"  • 群名: {getattr(group_info, 'group_name', '未知')}",
                        "  • 聊天类型: 群聊",
                    ]
                )
            else:
                info_parts.extend(["", "💭 聊天类型: 私聊"])

            # 流信息
            if hasattr(message, "chat_stream") and message.chat_stream:
                stream = message.chat_stream
                info_parts.extend(
                    [
                        "",
                        "🌊 聊天流信息:",
                        f"  • 流ID: {stream.stream_id}",
                        f"  • 创建时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stream.create_time))}",
                        f"  • 最后活跃: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stream.last_active_time))}",
                    ]
                )

            response = "\n".join(info_parts)
            await self.send_reply(response)
            logger.info(f"{self.log_prefix} 显示消息信息: {user_info.user_id}")
            return True, response

        except Exception as e:
            logger.error(f"{self.log_prefix} 消息信息查询失败: {e}")
            error_msg = f"❌ 信息查询失败: {str(e)}"
            await self.send_reply(error_msg)
            return False, str(e)


@register_plugin
class ExampleComprehensivePlugin(BasePlugin):
    """综合示例插件

    整合了旧示例插件的所有功能，展示新插件系统的完整能力：
    - 多种Action和Command组件
    - 拦截控制功能演示
    - 配置驱动的行为
    - 完整的错误处理
    - 日志记录和监控
    """

    # 插件基本信息
    plugin_name = "example_plugin"
    plugin_description = "综合示例插件，展示新插件系统的完整功能"
    plugin_version = "2.0.0"
    plugin_author = "MaiBot开发团队"
    enable_plugin = True
    config_file_name = "config.toml"

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""

        # 从配置获取组件启用状态
        enable_greeting = self.get_config("components.enable_greeting", True)
        enable_help = self.get_config("components.enable_help", True)
        enable_send = self.get_config("components.enable_send", True)
        enable_echo = self.get_config("components.enable_echo", True)
        enable_info = self.get_config("components.enable_info", True)
        enable_dice = self.get_config("components.enable_dice", True)
        components = []

        # 添加Action组件
        if enable_greeting:
            components.append(
                (
                    SmartGreetingAction.get_action_info(
                        name="smart_greeting", description="智能问候系统，基于关键词触发"
                    ),
                    SmartGreetingAction,
                )
            )

        # 添加Command组件
        if enable_help:
            components.append(
                (
                    ComprehensiveHelpCommand.get_command_info(
                        name="comprehensive_help", description="综合帮助系统，显示所有命令信息"
                    ),
                    ComprehensiveHelpCommand,
                )
            )

        if enable_send:
            components.append(
                (
                    MessageSendCommand.get_command_info(
                        name="message_send", description="消息发送命令，支持群聊和私聊"
                    ),
                    MessageSendCommand,
                )
            )

        if enable_echo:
            components.append(
                (EchoCommand.get_command_info(name="echo", description="回声命令，重复用户输入"), EchoCommand)
            )

        if enable_info:
            components.append(
                (
                    MessageInfoCommand.get_command_info(name="message_info", description="消息信息查询，显示详细信息"),
                    MessageInfoCommand,
                )
            )

        if enable_dice:
            components.append((DiceCommand.get_command_info(name="dice", description="骰子命令，掷骰子"), DiceCommand))

        return components
