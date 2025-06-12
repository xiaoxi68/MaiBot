import logging
import logging.handlers
from pathlib import Path
from typing import Callable, Optional
import json

import structlog

# 创建logs目录
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# 配置标准logging以支持文件输出和压缩
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        # 带压缩的轮转文件处理器
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "app.log.jsonl",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        ),
        # 控制台处理器
        logging.StreamHandler(),
    ],
)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        # 根据输出类型选择不同的渲染器
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# 为文件输出配置JSON格式
file_formatter = structlog.stdlib.ProcessorFormatter(
    processor=structlog.processors.JSONRenderer(ensure_ascii=False),
    foreign_pre_chain=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ],
)

# 为控制台输出配置可读格式
console_formatter = structlog.stdlib.ProcessorFormatter(
    processor=structlog.dev.ConsoleRenderer(colors=True),
    foreign_pre_chain=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ],
)

# 获取根logger并配置格式化器
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if isinstance(handler, logging.handlers.RotatingFileHandler):
        handler.setFormatter(file_formatter)
    else:
        handler.setFormatter(console_formatter)

raw_logger = structlog.get_logger()

binds: dict[str, Callable] = {}


def get_logger(name: Optional[str]):
    """获取logger实例，支持按名称绑定"""
    if name is None:
        return raw_logger
    logger = binds.get(name)
    if logger is None:
        binds[name] = logger = structlog.get_logger(name).bind(logger_name=name)
    return logger


def configure_logging(
    level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    log_dir: str = "logs",
):
    """动态配置日志参数"""
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # 更新文件handler配置
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.maxBytes = max_bytes
            handler.backupCount = backup_count
            handler.baseFilename = str(log_path / "app.log.jsonl")
    
    # 设置日志级别
    root_logger.setLevel(getattr(logging, level.upper()))

def format_json_for_logging(data, indent=2, ensure_ascii=False):
    """将JSON数据格式化为可读字符串
    
    Args:
        data: 要格式化的数据（字典、列表等）
        indent: 缩进空格数
        ensure_ascii: 是否确保ASCII编码
        
    Returns:
        str: 格式化后的JSON字符串
    """
    if isinstance(data, str):
        try:
            # 如果是JSON字符串，先解析再格式化
            parsed_data = json.loads(data)
            return json.dumps(parsed_data, indent=indent, ensure_ascii=ensure_ascii)
        except json.JSONDecodeError:
            # 如果不是有效JSON，直接返回
            return data
    else:
        # 如果是对象，直接格式化
        try:
            return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
        except (TypeError, ValueError):
            # 如果无法序列化，返回字符串表示
            return str(data)
