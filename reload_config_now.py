#!/usr/bin/env python3
"""
立即重新加载日志配置
"""

import sys
from pathlib import Path

# 添加src目录到路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from common.logger import reload_log_config

print("🔄 重新加载日志配置...")
reload_log_config()
print("✅ 配置已重新加载！faiss日志已被屏蔽。") 