from src.common.logger_manager import get_logger
from src.chat.command.command_handler import BaseCommand, register_command
from typing import Tuple, Optional
import random

logger = get_logger("custom_prefix_command")


@register_command
class DiceCommand(BaseCommand):
    """骰子命令，使用!前缀而不是/前缀"""

    command_name = "dice"
    command_description = "骰子命令，随机生成1-6的数字"
    command_pattern = r"^[!！](?:dice|骰子)(?:\s+(?P<count>\d+))?$"  # 匹配 !dice 或 !骰子，可选参数为骰子数量
    command_help = "使用方法: !dice [数量] 或 !骰子 [数量] - 掷骰子，默认掷1个"
    command_examples = ["!dice", "!骰子", "!dice 3", "！骰子 5"]
    enable_command = True

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
                        return False, "骰子数量必须大于0"
                    if count > 10:  # 限制最大数量
                        return False, "一次最多只能掷10个骰子"
                except ValueError:
                    return False, "骰子数量必须是整数"

            # 生成随机数
            results = [random.randint(1, 6) for _ in range(count)]

            # 构建回复消息
            if count == 1:
                message = f"🎲 掷出了 {results[0]} 点"
            else:
                dice_results = ", ".join(map(str, results))
                total = sum(results)
                message = f"🎲 掷出了 {count} 个骰子: [{dice_results}]，总点数: {total}"

            logger.info(f"{self.log_prefix} 执行骰子命令: {message}")
            return True, message

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行骰子命令时出错: {e}")
            return False, f"执行命令时出错: {str(e)}"
