import logging
from typing import Callable, Optional

import structlog

# TODO: customize the logger configuration as needed
# TODO: compress the log output
# TODO: output to a file with JSON format
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

raw_logger = structlog.get_logger()

binds: dict[str, Callable] = {}


def get_logger(name: Optional[str]):
    if name is None:
        return raw_logger
    logger = binds.get(name)
    if logger is None:
        binds[name] = logger = structlog.get_logger(name).bind(logger_name=name)
    return logger
