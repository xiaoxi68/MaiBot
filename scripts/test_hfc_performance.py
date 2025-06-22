#!/usr/bin/env python3
"""
HFC性能记录功能测试脚本
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chat.focus_chat.hfc_performance_logger import HFCPerformanceLogger
from src.chat.focus_chat.hfc_version_manager import set_hfc_version, get_hfc_version, auto_generate_hfc_version


def test_performance_logger():
    """测试性能记录器功能"""

    # 设置测试版本号
    test_version = "v1.2.3_test"
    set_hfc_version(test_version)
    print(f"设置测试版本号: {test_version}")
    print(f"当前版本号: {get_hfc_version()}")

    # 创建测试用的性能记录器
    test_chat_id = "test_chat_123"
    logger = HFCPerformanceLogger(test_chat_id, test_version)

    print(f"测试 HFC 性能记录器 - Chat ID: {test_chat_id}, Version: {logger.version}")

    # 模拟记录几个循环的数据
    test_cycles = [
        {
            "cycle_id": 1,
            "action_type": "reply",
            "total_time": 2.5,
            "step_times": {"观察": 0.1, "并行调整动作、处理": 1.2, "规划器": 0.8, "执行动作": 0.4},
            "reasoning": "用户询问天气，需要回复",
            "success": True,
        },
        {
            "cycle_id": 2,
            "action_type": "no_reply",
            "total_time": 1.8,
            "step_times": {"观察": 0.08, "并行调整动作、处理": 0.9, "规划器": 0.6, "执行动作": 0.22},
            "reasoning": "无需回复的日常对话",
            "success": True,
        },
        {
            "cycle_id": 3,
            "action_type": "reply",
            "total_time": 3.2,
            "step_times": {"观察": 0.12, "并行调整动作、处理": 1.5, "规划器": 1.1, "执行动作": 0.48},
            "reasoning": "用户提出复杂问题，需要详细回复",
            "success": True,
        },
        {
            "cycle_id": 4,
            "action_type": "no_reply",
            "total_time": 1.5,
            "step_times": {"观察": 0.07, "并行调整动作、处理": 0.8, "规划器": 0.5, "执行动作": 0.13},
            "reasoning": "群聊中的无关对话",
            "success": True,
        },
        {
            "cycle_id": 5,
            "action_type": "error",
            "total_time": 0.5,
            "step_times": {"观察": 0.05, "并行调整动作、处理": 0.2, "规划器": 0.15, "执行动作": 0.1},
            "reasoning": "处理过程中出现错误",
            "success": False,
        },
    ]

    # 记录测试数据
    for cycle_data in test_cycles:
        logger.record_cycle(cycle_data)
        print(f"已记录循环 {cycle_data['cycle_id']}: {cycle_data['action_type']} ({cycle_data['total_time']:.1f}s)")

    # 获取当前会话统计
    current_stats = logger.get_current_session_stats()
    print("\n=== 当前会话统计 ===")
    print(json.dumps(current_stats, ensure_ascii=False, indent=2))

    # 完成会话
    logger.finalize_session()
    print("\n=== 会话已完成 ===")
    print(f"日志文件: {logger.session_file}")
    print(f"统计文件: {logger.stats_file}")

    # 检查生成的文件
    if logger.session_file.exists():
        print(f"\n会话文件大小: {logger.session_file.stat().st_size} 字节")

    if logger.stats_file.exists():
        print(f"统计文件大小: {logger.stats_file.stat().st_size} 字节")

        # 读取并显示统计数据
        with open(logger.stats_file, "r", encoding="utf-8") as f:
            stats_data = json.load(f)

        print("\n=== 最终统计数据 ===")
        if test_chat_id in stats_data:
            chat_stats = stats_data[test_chat_id]
            print(f"Chat ID: {test_chat_id}")
            print(f"最后更新: {chat_stats['last_updated']}")
            print(f"总记录数: {chat_stats['overall']['total_records']}")
            print(f"平均总时间: {chat_stats['overall']['avg_total_time']:.2f}秒")

            print("\n各步骤平均时间:")
            for step, avg_time in chat_stats["overall"]["avg_step_times"].items():
                print(f"  {step}: {avg_time:.3f}秒")

            print("\n按动作类型统计:")
            for action, action_stats in chat_stats["by_action"].items():
                print(
                    f"  {action}: {action_stats['count']}次 ({action_stats['percentage']:.1f}%), 平均{action_stats['avg_total_time']:.2f}秒"
                )


def test_version_manager():
    """测试版本号管理功能"""
    print("\n=== 测试版本号管理器 ===")

    # 测试默认版本
    print(f"默认版本: {get_hfc_version()}")

    # 测试设置版本
    test_versions = ["v2.0.0", "1.5.0", "v1.0.0.beta", "v1.0.build123"]
    for version in test_versions:
        success = set_hfc_version(version)
        print(f"设置版本 '{version}': {'成功' if success else '失败'} -> {get_hfc_version()}")

    # 测试自动生成版本
    auto_version = auto_generate_hfc_version()
    print(f"自动生成版本: {auto_version}")

    # 测试基于现有版本的自动生成
    auto_version2 = auto_generate_hfc_version("v2.1.0")
    print(f"基于v2.1.0自动生成: {auto_version2}")


if __name__ == "__main__":
    test_version_manager()
    test_performance_logger()
