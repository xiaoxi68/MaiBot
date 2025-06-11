from typing import Callable, Optional

import structlog

raw_logger = structlog.get_logger()

binds: dict[str, Callable] = {}


def get_logger(name: Optional[str]):
    if name is None:
        return raw_logger
    logger = binds.get(name)
    if logger is None:
        binds[name] = logger = structlog.get_logger(name).bind(name=name)
    return logger
