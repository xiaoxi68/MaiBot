import logging
import logging.handlers
from pathlib import Path
from typing import Callable, Optional
import json

import structlog
import toml

# 创建logs目录
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


# 读取日志配置
def load_log_config():
    """从配置文件加载日志设置"""
    config_path = Path("config/bot_config.toml")
    default_config = {
        "date_style": "Y-m-d H:i:s",
        "log_level_style": "lite",
        "color_text": "title",
        "log_level": "INFO",
        "suppress_libraries": [],
        "library_log_levels": {},
    }

    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = toml.load(f)
                return config.get("log", default_config)
    except Exception:
        pass

    return default_config


LOG_CONFIG = load_log_config()


def get_timestamp_format():
    """将配置中的日期格式转换为Python格式"""
    date_style = LOG_CONFIG.get("date_style", "Y-m-d H:i:s")
    # 转换PHP风格的日期格式到Python格式
    format_map = {
        "Y": "%Y",  # 4位年份
        "m": "%m",  # 月份（01-12）
        "d": "%d",  # 日期（01-31）
        "H": "%H",  # 小时（00-23）
        "i": "%M",  # 分钟（00-59）
        "s": "%S",  # 秒数（00-59）
    }

    python_format = date_style
    for php_char, python_char in format_map.items():
        python_format = python_format.replace(php_char, python_char)

    return python_format


def configure_third_party_loggers():
    """配置第三方库的日志级别"""
    # 设置全局日志级别
    global_log_level = LOG_CONFIG.get("log_level", "INFO")
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, global_log_level.upper(), logging.INFO))

    # 完全屏蔽的库
    suppress_libraries = LOG_CONFIG.get("suppress_libraries", [])
    for lib_name in suppress_libraries:
        lib_logger = logging.getLogger(lib_name)
        lib_logger.setLevel(logging.CRITICAL + 1)  # 设置为比CRITICAL更高的级别，基本屏蔽所有日志
        lib_logger.propagate = False  # 阻止向上传播

    # 设置特定级别的库
    library_log_levels = LOG_CONFIG.get("library_log_levels", {})
    for lib_name, level_name in library_log_levels.items():
        lib_logger = logging.getLogger(lib_name)
        level = getattr(logging, level_name.upper(), logging.WARNING)
        lib_logger.setLevel(level)


def reconfigure_existing_loggers():
    """重新配置所有已存在的logger，解决加载顺序问题"""
    # 获取根logger
    root_logger = logging.getLogger()

    # 重新设置根logger的所有handler的格式化器
    for handler in root_logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.setFormatter(file_formatter)
        elif isinstance(handler, logging.StreamHandler):
            handler.setFormatter(console_formatter)

    # 遍历所有已存在的logger并重新配置
    logger_dict = logging.getLogger().manager.loggerDict
    for name, logger_obj in logger_dict.items():
        if isinstance(logger_obj, logging.Logger):
            # 检查是否是第三方库logger
            suppress_libraries = LOG_CONFIG.get("suppress_libraries", [])
            library_log_levels = LOG_CONFIG.get("library_log_levels", {})

            # 如果在屏蔽列表中
            if any(name.startswith(lib) for lib in suppress_libraries):
                logger_obj.setLevel(logging.CRITICAL + 1)
                logger_obj.propagate = False
                continue

            # 如果在特定级别设置中
            for lib_name, level_name in library_log_levels.items():
                if name.startswith(lib_name):
                    level = getattr(logging, level_name.upper(), logging.WARNING)
                    logger_obj.setLevel(level)
                    break

            # 强制清除并重新设置所有handler
            original_handlers = logger_obj.handlers[:]
            for handler in original_handlers:
                logger_obj.removeHandler(handler)

            # 如果logger没有handler，让它使用根logger的handler（propagate=True）
            if not logger_obj.handlers:
                logger_obj.propagate = True

            # 如果logger有自己的handler，重新配置它们
            for handler in original_handlers:
                if isinstance(handler, logging.handlers.RotatingFileHandler):
                    handler.setFormatter(file_formatter)
                elif isinstance(handler, logging.StreamHandler):
                    handler.setFormatter(console_formatter)
                logger_obj.addHandler(handler)


# 定义模块颜色映射
MODULE_COLORS = {
    # 核心模块
    "main": "\033[1;97m",  # 亮白色+粗体 (主程序)
    "api": "\033[92m",  # 亮绿色
    "emoji": "\033[92m",  # 亮绿色
    "chat": "\033[94m",  # 亮蓝色
    "config": "\033[93m",  # 亮黄色
    "common": "\033[95m",  # 亮紫色
    "tools": "\033[96m",  # 亮青色
    "lpmm": "\033[96m",
    "plugin_system": "\033[91m",  # 亮红色
    "experimental": "\033[97m",  # 亮白色
    "person_info": "\033[32m",  # 绿色
    "individuality": "\033[34m",  # 蓝色
    "manager": "\033[35m",  # 紫色
    "llm_models": "\033[36m",  # 青色
    "plugins": "\033[31m",  # 红色
    "plugin_api": "\033[33m",  # 黄色
    "remote": "\033[38;5;93m",  # 紫蓝色
    "planner": "\033[36m",
    "memory": "\033[34m",
    "hfc": "\033[96m",
    "base_action": "\033[96m",
    "action_manager": "\033[34m",
    
    # 聊天相关模块
    "normal_chat": "\033[38;5;81m",  # 亮蓝绿色
    "normal_chat_response": "\033[38;5;123m",  # 青绿色
    "normal_chat_expressor": "\033[38;5;117m",  # 浅蓝色
    "normal_chat_action_modifier": "\033[38;5;111m",  # 蓝色
    "normal_chat_planner": "\033[38;5;75m",  # 浅蓝色
    "heartflow": "\033[38;5;213m",  # 粉色
    "heartflow_utils": "\033[38;5;219m",  # 浅粉色
    "sub_heartflow": "\033[38;5;207m",  # 粉紫色
    "subheartflow_manager": "\033[38;5;201m",  # 深粉色
    "observation": "\033[38;5;141m",  # 紫色
    "background_tasks": "\033[38;5;240m",  # 灰色
    "chat_message": "\033[38;5;45m",  # 青色
    "chat_stream": "\033[38;5;51m",  # 亮青色
    "sender": "\033[38;5;39m",  # 蓝色
    "message_storage": "\033[38;5;33m",  # 深蓝色
    
    # 专注聊天模块
    "replyer": "\033[38;5;166m",  # 橙色
    "expressor": "\033[38;5;172m",  # 黄橙色
    "planner_factory": "\033[38;5;178m",  # 黄色
    "processor": "\033[38;5;184m",  # 黄绿色
    "base_processor": "\033[38;5;190m",  # 绿黄色
    "working_memory": "\033[38;5;22m",  # 深绿色
    "memory_activator": "\033[38;5;28m",  # 绿色
    
    # 插件系统
    "plugin_manager": "\033[38;5;196m",  # 红色
    "base_plugin": "\033[38;5;202m",  # 橙红色
    "base_command": "\033[38;5;208m",  # 橙色
    "component_registry": "\033[38;5;214m",  # 橙黄色
    "stream_api": "\033[38;5;220m",  # 黄色
    "config_api": "\033[38;5;226m",  # 亮黄色
    "hearflow_api": "\033[38;5;154m",  # 黄绿色
    "action_apis": "\033[38;5;118m",  # 绿色
    "independent_apis": "\033[38;5;82m",  # 绿色
    "llm_api": "\033[38;5;46m",  # 亮绿色
    "database_api": "\033[38;5;10m",  # 绿色
    "utils_api": "\033[38;5;14m",  # 青色
    "message_api": "\033[38;5;6m",  # 青色
    
    # 管理器模块
    "async_task_manager": "\033[38;5;129m",  # 紫色
    "mood": "\033[38;5;135m",  # 紫红色
    "local_storage": "\033[38;5;141m",  # 紫色
    "willing": "\033[38;5;147m",  # 浅紫色
    
    # 工具模块
    "tool_use": "\033[38;5;64m",  # 深绿色
    "base_tool": "\033[38;5;70m",  # 绿色
    "compare_numbers_tool": "\033[38;5;76m",  # 浅绿色
    "change_mood_tool": "\033[38;5;82m",  # 绿色
    "relationship_tool": "\033[38;5;88m",  # 深红色
    
    # 工具和实用模块
    "prompt": "\033[38;5;99m",  # 紫色
    "prompt_build": "\033[38;5;105m",  # 紫色
    "chat_utils": "\033[38;5;111m",  # 蓝色
    "chat_image": "\033[38;5;117m",  # 浅蓝色
    "typo_gen": "\033[38;5;123m",  # 青绿色
    "maibot_statistic": "\033[38;5;129m",  # 紫色
    
    # 特殊功能插件
    "mute_plugin": "\033[38;5;240m",  # 灰色
    "example_comprehensive": "\033[38;5;246m",  # 浅灰色
    "core_actions": "\033[38;5;52m",  # 深红色
    "tts_action": "\033[38;5;58m",  # 深黄色
    "doubao_pic_plugin": "\033[38;5;64m",  # 深绿色
    "vtb_action": "\033[38;5;70m",  # 绿色
    
    # 数据库和消息
    "database_model": "\033[38;5;94m",  # 橙褐色
    "maim_message": "\033[38;5;100m",  # 绿褐色
    
    # 实验性模块
    "pfc": "\033[38;5;252m",  # 浅灰色
    
    # 日志系统
    "logger": "\033[38;5;8m",  # 深灰色
    "demo": "\033[38;5;15m",  # 白色
    "confirm": "\033[1;93m",  # 黄色+粗体
    
    # 模型相关
    "model_utils": "\033[38;5;164m",  # 紫红色
}

RESET_COLOR = "\033[0m"


class ModuleColoredConsoleRenderer:
    """自定义控制台渲染器，为不同模块提供不同颜色"""

    def __init__(self, colors=True):
        self._colors = colors
        self._config = LOG_CONFIG

        # 日志级别颜色
        self._level_colors = {
            "debug": "\033[38;5;208m",  # 橙色
            "info": "\033[34m",  # 蓝色
            "success": "\033[32m",  # 绿色
            "warning": "\033[33m",  # 黄色
            "error": "\033[31m",  # 红色
            "critical": "\033[35m",  # 紫色
        }

        # 根据配置决定是否启用颜色
        color_text = self._config.get("color_text", "title")
        if color_text == "none":
            self._colors = False
        elif color_text == "title":
            self._enable_module_colors = True
            self._enable_level_colors = False
            self._enable_full_content_colors = False
        elif color_text == "full":
            self._enable_module_colors = True
            self._enable_level_colors = True
            self._enable_full_content_colors = True
        else:
            self._enable_module_colors = True
            self._enable_level_colors = False
            self._enable_full_content_colors = False

    def __call__(self, logger, method_name, event_dict):
        """渲染日志消息"""
        # 获取基本信息
        timestamp = event_dict.get("timestamp", "")
        level = event_dict.get("level", "info")
        logger_name = event_dict.get("logger_name", "")
        event = event_dict.get("event", "")

        # 构建输出
        parts = []

        # 日志级别样式配置
        log_level_style = self._config.get("log_level_style", "lite")
        level_color = self._level_colors.get(level.lower(), "") if self._colors else ""

        # 时间戳（lite模式下按级别着色）
        if timestamp:
            if log_level_style == "lite" and level_color:
                timestamp_part = f"{level_color}{timestamp}{RESET_COLOR}"
            else:
                timestamp_part = timestamp
            parts.append(timestamp_part)

        # 日志级别显示（根据配置样式）
        if log_level_style == "full":
            # 显示完整级别名并着色
            level_text = level.upper()
            if level_color:
                level_part = f"{level_color}[{level_text:>8}]{RESET_COLOR}"
            else:
                level_part = f"[{level_text:>8}]"
            parts.append(level_part)

        elif log_level_style == "compact":
            # 只显示首字母并着色
            level_text = level.upper()[0]
            if level_color:
                level_part = f"{level_color}[{level_text:>8}]{RESET_COLOR}"
            else:
                level_part = f"[{level_text:>8}]"
            parts.append(level_part)

        # lite模式不显示级别，只给时间戳着色

        # 获取模块颜色，用于full模式下的整体着色
        module_color = ""
        if self._colors and self._enable_module_colors and logger_name:
            module_color = MODULE_COLORS.get(logger_name, "")

        # 模块名称（带颜色）
        if logger_name:
            if self._colors and self._enable_module_colors:
                if module_color:
                    module_part = f"{module_color}[{logger_name}]{RESET_COLOR}"
                else:
                    module_part = f"[{logger_name}]"
            else:
                module_part = f"[{logger_name}]"
            parts.append(module_part)

        # 消息内容（确保转换为字符串）
        event_content = ""
        if isinstance(event, str):
            event_content = event
        elif isinstance(event, dict):
            # 如果是字典，格式化为可读字符串
            try:
                event_content = json.dumps(event, ensure_ascii=False, indent=None)
            except (TypeError, ValueError):
                event_content = str(event)
        else:
            # 其他类型直接转换为字符串
            event_content = str(event)

        # 在full模式下为消息内容着色
        if self._colors and self._enable_full_content_colors and module_color:
            event_content = f"{module_color}{event_content}{RESET_COLOR}"
        
        parts.append(event_content)

        # 处理其他字段
        extras = []
        for key, value in event_dict.items():
            if key not in ("timestamp", "level", "logger_name", "event"):
                # 确保值也转换为字符串
                if isinstance(value, (dict, list)):
                    try:
                        value_str = json.dumps(value, ensure_ascii=False, indent=None)
                    except (TypeError, ValueError):
                        value_str = str(value)
                else:
                    value_str = str(value)
                
                # 在full模式下为额外字段着色
                extra_field = f"{key}={value_str}"
                if self._colors and self._enable_full_content_colors and module_color:
                    extra_field = f"{module_color}{extra_field}{RESET_COLOR}"
                
                extras.append(extra_field)

        if extras:
            parts.append(" ".join(extras))

        return " ".join(parts)


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


def configure_structlog():
    """配置structlog"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt=get_timestamp_format(), utc=False),
            # 根据输出类型选择不同的渲染器
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# 配置structlog
configure_structlog()

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
    processor=ModuleColoredConsoleRenderer(colors=True),
    foreign_pre_chain=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt=get_timestamp_format(), utc=False),
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


# 立即配置日志系统，确保最早期的日志也使用正确格式
def _immediate_setup():
    """立即设置日志系统，在模块导入时就生效"""
    # 重新配置structlog
    configure_structlog()

    # 清除所有已有的handler，重新配置
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 重新添加配置好的handler
    root_logger.addHandler(
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "app.log.jsonl",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    )
    root_logger.addHandler(logging.StreamHandler())

    # 设置格式化器
    for handler in root_logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.setFormatter(file_formatter)
        else:
            handler.setFormatter(console_formatter)

    # 配置第三方库日志
    configure_third_party_loggers()

    # 重新配置所有已存在的logger
    reconfigure_existing_loggers()


# 立即执行配置
_immediate_setup()

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


def set_module_color(module_name: str, color_code: str):
    """为指定模块设置颜色

    Args:
        module_name: 模块名称
        color_code: ANSI颜色代码，例如 '\033[92m' 表示亮绿色
    """
    MODULE_COLORS[module_name] = color_code


def get_module_colors():
    """获取当前模块颜色配置"""
    return MODULE_COLORS.copy()


def reload_log_config():
    """重新加载日志配置"""
    global LOG_CONFIG
    LOG_CONFIG = load_log_config()

    # 重新配置console渲染器
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.handlers.RotatingFileHandler):
            # 这是控制台处理器，更新其格式化器
            handler.setFormatter(
                structlog.stdlib.ProcessorFormatter(
                    processor=ModuleColoredConsoleRenderer(colors=True),
                    foreign_pre_chain=[
                        structlog.stdlib.add_logger_name,
                        structlog.stdlib.add_log_level,
                        structlog.stdlib.PositionalArgumentsFormatter(),
                        structlog.processors.TimeStamper(fmt=get_timestamp_format(), utc=False),
                        structlog.processors.StackInfoRenderer(),
                        structlog.processors.format_exc_info,
                    ],
                )
            )

    # 重新配置第三方库日志
    configure_third_party_loggers()

    # 重新配置所有已存在的logger
    reconfigure_existing_loggers()


def get_log_config():
    """获取当前日志配置"""
    return LOG_CONFIG.copy()


def force_reset_all_loggers():
    """强制重置所有logger，解决格式不一致问题"""
    # 清除所有现有的logger配置
    logging.getLogger().manager.loggerDict.clear()

    # 重新配置根logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # 重新添加我们的handler
    root_logger.addHandler(
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "app.log.jsonl",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    )
    root_logger.addHandler(logging.StreamHandler())

    # 设置格式化器
    for handler in root_logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.setFormatter(file_formatter)
        else:
            handler.setFormatter(console_formatter)

    # 设置级别
    global_log_level = LOG_CONFIG.get("log_level", "INFO")
    root_logger.setLevel(getattr(logging, global_log_level.upper(), logging.INFO))


def initialize_logging():
    """手动初始化日志系统，确保所有logger都使用正确的配置

    在应用程序的早期调用此函数，确保所有模块都使用统一的日志配置
    """
    global LOG_CONFIG
    LOG_CONFIG = load_log_config()
    configure_third_party_loggers()
    reconfigure_existing_loggers()

    # 输出初始化信息
    logger = get_logger("logger")
    log_level = LOG_CONFIG.get("log_level", "INFO")
    logger.info(f"日志系统已重新初始化，日志级别: {log_level}，所有logger已统一配置")


def force_initialize_logging():
    """强制重新初始化整个日志系统，解决格式不一致问题"""
    global LOG_CONFIG
    LOG_CONFIG = load_log_config()

    # 强制重置所有logger
    force_reset_all_loggers()

    # 重新配置structlog
    configure_structlog()

    # 配置第三方库
    configure_third_party_loggers()

    # 输出初始化信息
    logger = get_logger("logger")
    log_level = LOG_CONFIG.get("log_level", "INFO")
    logger.info(f"日志系统已强制重新初始化，日志级别: {log_level}，所有logger格式已统一")


def show_module_colors():
    """显示所有模块的颜色效果"""
    get_logger("demo")
    print("\n=== 模块颜色展示 ===")

    for module_name, _color_code in MODULE_COLORS.items():
        # 临时创建一个该模块的logger来展示颜色
        demo_logger = structlog.get_logger(module_name).bind(logger_name=module_name)
        demo_logger.info(f"这是 {module_name} 模块的颜色效果")

    print("=== 颜色展示结束 ===\n")


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
        # 如果是JSON字符串，先解析再格式化
        parsed_data = json.loads(data)
        return json.dumps(parsed_data, indent=indent, ensure_ascii=ensure_ascii)
    else:
        # 如果是对象，直接格式化
        return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
