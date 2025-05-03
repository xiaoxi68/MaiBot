from fastapi import APIRouter
from strawberry.fastapi import GraphQLRouter

# from src.config.config import BotConfig
from src.common.logger_manager import get_logger
from src.api.reload_config import reload_config as reload_config_func
from src.common.server import global_server
# import uvicorn
# import os

router = APIRouter()


logger = get_logger("api")

# maiapi = FastAPI()
logger.info("API server started.")
graphql_router = GraphQLRouter(schema=None, path="/")  # Replace `None` with your actual schema

router.include_router(graphql_router, prefix="/graphql", tags=["GraphQL"])


@router.post("/config/reload")
async def reload_config():
    return await reload_config_func()


def start_api_server():
    """启动API服务器"""
    global_server.register_router(router, prefix="/api/v1")
