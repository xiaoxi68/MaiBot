#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试日志轮转修复的脚本
"""

import logging
import time
import threading
from pathlib import Path
import sys
import os

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from common.logger import get_logger, force_initialize_logging, get_log_stats


def test_concurrent_logging():
    """测试并发日志写入"""
    logger = get_logger("test")
    
    def log_worker(worker_id):
        """工作线程函数"""
        for i in range(100):
            logger.info(f"工作线程 {worker_id} - 消息 {i}: 这是一条测试日志消息，用于测试并发写入和轮转功能")
            time.sleep(0.01)
    
    # 创建多个线程并发写入日志
    threads = []
    for i in range(5):
        thread = threading.Thread(target=log_worker, args=(i,))
        threads.append(thread)
        thread.start()
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    print("并发日志测试完成")


def test_log_rotation():
    """测试日志轮转"""
    logger = get_logger("rotation_test")
    
    # 生成大量日志来触发轮转
    large_message = "这是一条很长的日志消息用于测试轮转功能。" * 100
    
    print("开始生成大量日志以触发轮转...")
    for i in range(1000):
        logger.info(f"轮转测试消息 {i}: {large_message}")
        if i % 100 == 0:
            print(f"已生成 {i} 条日志...")
    
    print("日志轮转测试完成")


def main():
    """主函数"""
    print("开始测试日志系统修复...")
    
    # 强制初始化日志系统
    force_initialize_logging()
    
    # 显示初始日志统计
    stats = get_log_stats()
    print(f"初始日志统计: {stats}")
    
    # 测试并发日志
    print("\n=== 测试并发日志写入 ===")
    test_concurrent_logging()
    
    # 测试日志轮转
    print("\n=== 测试日志轮转 ===")
    test_log_rotation()
    
    # 显示最终日志统计
    stats = get_log_stats()
    print(f"\n最终日志统计: {stats}")
    
    # 检查日志文件
    log_dir = Path("logs")
    if log_dir.exists():
        log_files = list(log_dir.glob("app.log*"))
        print(f"\n生成的日志文件:")
        for log_file in sorted(log_files):
            size = log_file.stat().st_size / 1024 / 1024  # MB
            print(f"  {log_file.name}: {size:.2f} MB")
    
    print("\n测试完成！如果没有出现权限错误，说明修复成功。")


if __name__ == "__main__":
    main() 