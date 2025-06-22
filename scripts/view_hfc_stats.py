#!/usr/bin/env python3
"""
HFC性能统计数据查看工具
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def format_time(seconds: float) -> str:
    """格式化时间显示"""
    if seconds < 1:
        return f"{seconds * 1000:.1f}毫秒"
    else:
        return f"{seconds:.3f}秒"


def display_chat_stats(chat_id: str, stats: Dict[str, Any]):
    """显示单个聊天的统计数据"""
    print(f"\n=== Chat ID: {chat_id} ===")
    print(f"版本: {stats.get('version', 'unknown')}")
    print(f"最后更新: {stats['last_updated']}")

    overall = stats["overall"]
    print("\n📊 总体统计:")
    print(f"  总记录数: {overall['total_records']}")
    print(f"  平均总时间: {format_time(overall['avg_total_time'])}")

    print("\n⏱️ 各步骤平均时间:")
    for step, avg_time in overall["avg_step_times"].items():
        print(f"  {step}: {format_time(avg_time)}")

    print("\n🎯 按动作类型统计:")
    by_action = stats["by_action"]

    # 按比例排序
    sorted_actions = sorted(by_action.items(), key=lambda x: x[1]["percentage"], reverse=True)

    for action, action_stats in sorted_actions:
        print(f"  📌 {action}:")
        print(f"    次数: {action_stats['count']} ({action_stats['percentage']:.1f}%)")
        print(f"    平均总时间: {format_time(action_stats['avg_total_time'])}")

        if action_stats["avg_step_times"]:
            print("    步骤时间:")
            for step, step_time in action_stats["avg_step_times"].items():
                print(f"      {step}: {format_time(step_time)}")


def display_comparison(stats_data: Dict[str, Dict[str, Any]]):
    """显示多个聊天的对比数据"""
    if len(stats_data) < 2:
        return

    print("\n=== 多聊天对比 ===")

    # 创建对比表格
    chat_ids = list(stats_data.keys())

    print("\n📊 总体对比:")
    print(f"{'Chat ID':<20} {'版本':<12} {'记录数':<8} {'平均时间':<12} {'最常见动作':<15}")
    print("-" * 70)

    for chat_id in chat_ids:
        stats = stats_data[chat_id]
        overall = stats["overall"]

        # 找到最常见的动作
        most_common_action = max(stats["by_action"].items(), key=lambda x: x[1]["count"])
        most_common_name = most_common_action[0]
        most_common_pct = most_common_action[1]["percentage"]

        version = stats.get("version", "unknown")
        print(
            f"{chat_id:<20} {version:<12} {overall['total_records']:<8} {format_time(overall['avg_total_time']):<12} {most_common_name}({most_common_pct:.0f}%)"
        )


def view_session_logs(chat_id: str = None, latest: bool = False):
    """查看会话日志文件"""
    log_dir = Path("log/hfc_loop")
    if not log_dir.exists():
        print("❌ 日志目录不存在")
        return

    if chat_id:
        pattern = f"{chat_id}_*.json"
    else:
        pattern = "*.json"

    log_files = list(log_dir.glob(pattern))

    if not log_files:
        print(f"❌ 没有找到匹配的日志文件: {pattern}")
        return

    if latest:
        # 按文件修改时间排序，取最新的
        log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        log_files = log_files[:1]

    for log_file in log_files:
        print(f"\n=== 会话日志: {log_file.name} ===")

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                records = json.load(f)

            if not records:
                print("  空文件")
                continue

            print(f"  记录数: {len(records)}")
            print(f"  时间范围: {records[0]['timestamp']} ~ {records[-1]['timestamp']}")

            # 统计动作分布
            action_counts = {}
            total_time = 0

            for record in records:
                action = record["action_type"]
                action_counts[action] = action_counts.get(action, 0) + 1
                total_time += record["total_time"]

            print(f"  总耗时: {format_time(total_time)}")
            print(f"  平均耗时: {format_time(total_time / len(records))}")
            print(f"  动作分布: {dict(action_counts)}")

        except Exception as e:
            print(f"  ❌ 读取文件失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="HFC性能统计数据查看工具")
    parser.add_argument("--chat-id", help="指定要查看的Chat ID")
    parser.add_argument("--logs", action="store_true", help="查看会话日志文件")
    parser.add_argument("--latest", action="store_true", help="只显示最新的日志文件")
    parser.add_argument("--compare", action="store_true", help="显示多聊天对比")

    args = parser.parse_args()

    if args.logs:
        view_session_logs(args.chat_id, args.latest)
        return

    # 读取统计数据
    stats_file = Path("data/hfc/time.json")
    if not stats_file.exists():
        print("❌ 统计数据文件不存在，请先运行一些HFC循环以生成数据")
        return

    try:
        with open(stats_file, "r", encoding="utf-8") as f:
            stats_data = json.load(f)
    except Exception as e:
        print(f"❌ 读取统计数据失败: {e}")
        return

    if not stats_data:
        print("❌ 统计数据为空")
        return

    if args.chat_id:
        if args.chat_id in stats_data:
            display_chat_stats(args.chat_id, stats_data[args.chat_id])
        else:
            print(f"❌ 没有找到Chat ID '{args.chat_id}' 的数据")
            print(f"可用的Chat ID: {list(stats_data.keys())}")
    else:
        # 显示所有聊天的统计数据
        for chat_id, stats in stats_data.items():
            display_chat_stats(chat_id, stats)

        if args.compare:
            display_comparison(stats_data)


if __name__ == "__main__":
    main()
