from rich.traceback import install

import urllib3

from src.common.logger_manager import get_logger

install(extra_lines=3)

logger = get_logger("chat_message")

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
