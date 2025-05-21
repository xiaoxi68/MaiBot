from asyncio import CancelledError

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from uvicorn import Config, Server as UvicornServer
import os
from rich.traceback import install

from src.common.logger_manager import get_logger
from src.manager.async_task_manager import AsyncTask

install(extra_lines=3)

logger = get_logger("net_server")


class NetServerTask(AsyncTask):
    def __init__(self):
        super().__init__(task_name="Net Server Task")

    async def run(self):
        """运行服务器"""
        try:
            await global_server.run()
        except CancelledError:
            pass  # 捕获取消事件，不做处理，直接结束
        except Exception as e:
            logger.error(f"网络服务在运行时发生异常: {e}")
        finally:
            await global_server.shutdown()


class Server:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, app_name: str = "MaiMCore"):
        self._app = FastAPI(title=app_name)

        self.host: str = host or "127.0.0.1"
        self.port: int = port or 8080

        self._server: Optional[UvicornServer] = None

        # 配置 CORS
        # TODO: 建议在配置中添加相关配置项，而非硬编码
        origins = [
            "http://localhost:3000",  # 允许的前端源
            "http://127.0.0.1:3000",
            # 在生产环境中，您应该添加实际的前端域名
        ]

        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,  # 是否支持 cookie
            allow_methods=["*"],  # 允许所有 HTTP 方法
            allow_headers=["*"],  # 允许所有 HTTP 请求头
        )

    def register_router(self, router: APIRouter, prefix: str = ""):
        """注册路由

        APIRouter 用于对相关的路由端点进行分组和模块化管理：
        1. 可以将相关的端点组织在一起，便于管理
        2. 支持添加统一的路由前缀
        3. 可以为一组路由添加共同的依赖项、标签等

        示例:
            router = APIRouter()

            @router.get("/users")
            def get_users():
                return {"users": [...]}

            @router.post("/users")
            def create_user():
                return {"msg": "user created"}

            # 注册路由，添加前缀 "/api/v1"
            server.register_router(router, prefix="/api/v1")
        """
        self._app.include_router(router, prefix=prefix)

    async def run(self):
        """启动服务器"""
        # 禁用 uvicorn 默认日志和访问日志
        config = Config(app=self._app, host=self.host, port=self.port, log_config=None, access_log=False)
        self._server = UvicornServer(config=config)

        # 启动服务器
        logger.info("启动网络服务...")
        await self._server.serve()

    async def shutdown(self):
        """安全关闭服务器"""
        if self._server:
            await self._server.shutdown()
            logger.info("网络服务已安全关闭")

    def get_app(self) -> FastAPI:
        """获取 FastAPI 实例"""
        return self._app


global_server = Server(host=os.environ["HOST"], port=int(os.environ["PORT"]))
