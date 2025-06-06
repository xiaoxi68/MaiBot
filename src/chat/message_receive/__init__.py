import urllib3
from .message_recv import MessageRecv
from .message_send import MessageSend
from .message_sender import message_manager

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


__all__ = [
    "MessageRecv",
    "MessageSend",
    "message_manager",
]
