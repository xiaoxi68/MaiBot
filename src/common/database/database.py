from pathlib import Path

from rich.traceback import install
from sqlmodel import StaticPool, create_engine, Session

from src.common.logger_manager import get_logger
from src.config.config import global_config
from src.common.database.database_model import create_database

install(extra_lines=3)

logger = get_logger("database")

# 定义数据库文件路径
_DATA_DIR = Path(global_config.storage.data_path)
_DB_FILE = _DATA_DIR / "MaiBot.db"

logger.info("正在初始化数据库组件...")

# 确保数据库目录存在
_DB_FILE.mkdir(parents=True, exist_ok=True)


_SQLITE_URL = f"sqlite:///{_DB_FILE}"
# TODO: 支持更多的数据库类型

db_engine = create_engine(
    _SQLITE_URL,
    echo=True,  # echo=True  # 设置为True以启用SQLAlchemy的调试输出
    poolclass=StaticPool,  # 使用静态连接池
    connect_args={
        "check_same_thread": False,  # SQLite不支持多线程访问
        "timeout": 30,  # 连接超时时间
    },
)
"""全局的数据库引擎对象"""

"""
其它数据库的配置示例：
# PostgreSQL
engine = create_engine(
    "postgresql://user:password@localhost/dbname",
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800
)

# MySQL
engine = create_engine(
    "mysql+pymysql://user:password@localhost/dbname",
    poolclass=QueuePool,
    pool_size=5,
    pool_pre_ping=True  # MySQL推荐启用
)
"""

create_database(db_engine)  # 创建数据库表

logger.success("数据库组件初始化完成")


class DBSession:
    """
    数据库会话类
    """

    def __init__(self):
        self.session = None

    def __enter__(self):
        self.session = Session(db_engine)
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
