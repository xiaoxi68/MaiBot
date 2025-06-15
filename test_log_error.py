#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试日志轮转错误的脚本
"""

import logging
import sys
import os
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from common.logger import get_logger, force_initialize_logging


def test_log_rotation_with_error_detection():
    """测试日志轮转并捕获错误"""
    print("开始测试日志轮转错误检测...")
    
    # 强制初始化日志系统
    force_initialize_logging()
    
    logger = get_logger("error_test")
    
    # 生成足够多的日志来强制轮转
    large_message = "这是一条用于强制轮转的长消息。" * 200
    
    print("开始生成日志以强制轮转...")
    
    # 监控控制台输出中的错误信息
    original_print = print
    errors = []
    
    def capture_print(*args, **kwargs):
        message = ' '.join(str(arg) for arg in args)
        if "重命名失败" in message or "删除失败" in message or "错误" in message:
            errors.append(message)
        original_print(*args, **kwargs)
    
    # 临时替换print函数来捕获错误
    import builtins
    builtins.print = capture_print
    
    try:
        # 生成大量日志
        for i in range(500):
            logger.info(f"错误测试消息 {i}: {large_message}")
            if i % 50 == 0:
                original_print(f"已生成 {i} 条日志...")
        
        # 等待一段时间让压缩线程完成
        import time
        time.sleep(2)
        
    finally:
        # 恢复原始print函数
        builtins.print = original_print
    
    print(f"\n检测到的错误信息:")
    if errors:
        for error in errors:
            print(f"  - {error}")
    else:
        print("  没有检测到错误")
    
    # 检查日志文件状态
    log_dir = Path("logs")
    if log_dir.exists():
        log_files = list(log_dir.glob("app.log*"))
        print(f"\n当前日志文件:")
        for log_file in sorted(log_files):
            size = log_file.stat().st_size / 1024  # KB
            print(f"  {log_file.name}: {size:.1f} KB")
    
    return errors


if __name__ == "__main__":
    errors = test_log_rotation_with_error_detection()
    if errors:
        print("\n⚠️  发现错误，需要进一步修复")
        sys.exit(1)
    else:
        print("\n✅ 测试通过，没有发现错误")
        sys.exit(0) 