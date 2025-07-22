from .willing_manager import BaseWillingManager

NOT_IMPLEMENTED_MESSAGE = "\ncustom模式你实现了吗？没自行实现不要选custom。给你退了快点给你麦爹配置\n注：以上内容由gemini生成，如有不满请投诉gemini"

class CustomWillingManager(BaseWillingManager):
    async def async_task_starter(self) -> None:
        raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)

    async def before_generate_reply_handle(self, message_id: str):
        raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)

    async def after_generate_reply_handle(self, message_id: str):
        raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)

    async def not_reply_handle(self, message_id: str):
        raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)

    async def get_reply_probability(self, message_id: str):
        raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)

    def __init__(self):
        super().__init__()
        raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)
