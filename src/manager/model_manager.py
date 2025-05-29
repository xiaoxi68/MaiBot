import maibot_api_adapter
from maibot_api_adapter.model_manager import ModelManager
from maibot_api_adapter.config.parser import load_config

from common.logger_manager import get_logger

maibot_api_adapter.init_logger(get_logger("model_manager"))

_model_config = load_config("model_config.yaml")

global_model_manager = ModelManager(_model_config)
