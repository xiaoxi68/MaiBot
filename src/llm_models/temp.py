
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config.config import model_config
print(f"当前模型配置: {model_config}")
print(model_config.req_conf.default_max_tokens)