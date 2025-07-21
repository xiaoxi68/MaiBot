from .willing_manager import BaseWillingManager

text = "你丫的不配置你选什么custom模式，给你退了快点给你麦爹配置\n注：以上内容由gemini生成，如有不满请投诉gemini"

class CustomWillingManager(BaseWillingManager):
    async def async_task_starter(self) -> None:
        raise NotImplementedError(text)

    async def before_generate_reply_handle(self, message_id: str):
        raise NotImplementedError(text)

    async def after_generate_reply_handle(self, message_id: str):
        raise NotImplementedError(text)

    async def not_reply_handle(self, message_id: str):
        raise NotImplementedError(text)

    async def get_reply_probability(self, message_id: str):
        raise NotImplementedError(text)

    def __init__(self):
        super().__init__()
