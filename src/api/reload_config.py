from fastapi import HTTPException
from rich.traceback import install
from src.config.config import BotConfig
import os

install(extra_lines=3)


async def reload_config():
    try:
        from src.config import config as config_module

        bot_config_path = os.path.join(BotConfig.get_config_dir(), "bot_config.toml")
        config_module.global_config = BotConfig.load_config(config_path=bot_config_path)
        return {"status": "reloaded"}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重载配置时发生错误: {str(e)}") from e
