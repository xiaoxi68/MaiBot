
from src.plugin_system.apis import send_api

async def send_loading(chat_id: str, content: str):
    await send_api.custom_to_stream(
        message_type="loading",
        content=content,
        stream_id=chat_id,
        storage_message=False,
        show_log=True,
    )
    
async def send_unloading(chat_id: str):
    await send_api.custom_to_stream(
        message_type="loading",
        content="",
        stream_id=chat_id,
        storage_message=False,
        show_log=True,
    )
    