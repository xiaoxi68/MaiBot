# 定义了来自外部世界的信息
# 外部世界可以是某个聊天 不同平台的聊天 也可以是任意媒体
from datetime import datetime
from src.common.logger_manager import get_logger
from src.plugins.utils.prompt_builder import Prompt

# Import the new utility function

logger = get_logger("observation")

# --- Define Prompt Templates for Chat Summary ---
Prompt(
    """这是qq群聊的聊天记录，请总结以下聊天记录的主题：
{chat_logs}
请用一句话概括，包括人物、事件和主要信息，不要分点。""",
    "chat_summary_group_prompt",  # Template for group chat
)

Prompt(
    """这是你和{chat_target}的私聊记录，请总结以下聊天记录的主题：
{chat_logs}
请用一句话概括，包括事件，时间，和主要信息，不要分点。""",
    "chat_summary_private_prompt",  # Template for private chat
)
# --- End Prompt Template Definition ---


# 所有观察的基类
class Observation:
    def __init__(self, observe_id):
        self.observe_info = ""
        self.observe_id = observe_id
        self.last_observe_time = datetime.now().timestamp()  # 初始化为当前时间

    async def observe(self):
        pass
