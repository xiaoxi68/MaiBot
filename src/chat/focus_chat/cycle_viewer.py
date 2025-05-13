import os
import argparse
from src.chat.focus_chat.cycle_analyzer import CycleAnalyzer


def print_section(title: str, width: int = 80):
    """打印分隔线和标题"""
    print("\n" + "=" * width)
    print(f" {title} ".center(width, "="))
    print("=" * width)


def list_streams_cmd(analyzer: CycleAnalyzer, args: argparse.Namespace):
    """列出所有聊天流"""
    print_section("所有聊天流")
    streams = analyzer.list_streams()

    if not streams:
        print("没有找到任何聊天流记录。")
        return

    for i, stream_id in enumerate(streams):
        count = analyzer.get_stream_cycle_count(stream_id)
        print(f"[{i + 1}] {stream_id} - {count} 个循环")


def analyze_stream_cmd(analyzer: CycleAnalyzer, args: argparse.Namespace):
    """分析指定聊天流的循环信息"""
    stream_id = args.stream_id

    print_section(f"聊天流 {stream_id} 分析")
    stats = analyzer.analyze_stream_cycles(stream_id)

    if "error" in stats:
        print(f"错误: {stats['error']}")
        return

    print("基本统计:")
    print(f"  总循环数: {stats['总循环数']}")
    print(f"  总耗时: {stats['总耗时']}")
    print(f"  平均耗时: {stats['平均耗时']}")

    print("\n动作统计:")
    for action, count in stats["动作统计"].items():
        if count > 0:
            percent = (count / stats["总循环数"]) * 100
            print(f"  {action}: {count} ({percent:.1f}%)")

    if stats.get("工具使用次数"):
        print("\n工具使用次数:")
        for tool, count in stats["工具使用次数"].items():
            print(f"  {tool}: {count}")


def list_cycles_cmd(analyzer: CycleAnalyzer, args: argparse.Namespace):
    """列出指定聊天流的循环"""
    stream_id = args.stream_id
    limit = args.limit if args.limit > 0 else -1

    print_section(f"聊天流 {stream_id} 的循环列表")
    cycles = analyzer.get_stream_cycles(stream_id)

    if not cycles:
        print("没有找到任何循环记录。")
        return

    if limit > 0:
        cycles = cycles[-limit:]  # 取最新的limit个
        print(f"显示最新的 {limit} 个循环 (共 {len(cycles)} 个):")
    else:
        print(f"共找到 {len(cycles)} 个循环:")

    for i, filepath in enumerate(cycles):
        filename = os.path.basename(filepath)
        cycle_id = filename.split("_")[1]
        timestamp = filename.split("_", 2)[2].split(".")[0]
        print(f"[{i + 1}] 循环ID: {cycle_id}, 时间: {timestamp}, 文件: {filename}")


def view_cycle_cmd(analyzer: CycleAnalyzer, args: argparse.Namespace):
    """查看指定循环的详细信息"""
    stream_id = args.stream_id
    cycle_index = args.cycle_index - 1  # 转换为0-based索引

    cycles = analyzer.get_stream_cycles(stream_id)
    if not cycles:
        print(f"错误: 聊天流 {stream_id} 没有找到任何循环记录。")
        return

    if cycle_index < 0 or cycle_index >= len(cycles):
        print(f"错误: 循环索引 {args.cycle_index} 超出范围 (1-{len(cycles)})。")
        return

    filepath = cycles[cycle_index]
    filename = os.path.basename(filepath)

    print_section(f"循环详情: {filename}")
    content = analyzer.get_cycle_content(filepath)
    print(content)


def latest_cycles_cmd(analyzer: CycleAnalyzer, args: argparse.Namespace):
    """查看所有聊天流中最新的几个循环"""
    count = args.count if args.count > 0 else 10

    print_section(f"最新的 {count} 个循环")
    latest_cycles = analyzer.get_latest_cycles(count)

    if not latest_cycles:
        print("没有找到任何循环记录。")
        return

    for i, (stream_id, filepath) in enumerate(latest_cycles):
        filename = os.path.basename(filepath)
        cycle_id = filename.split("_")[1]
        timestamp = filename.split("_", 2)[2].split(".")[0]
        print(f"[{i + 1}] 聊天流: {stream_id}, 循环ID: {cycle_id}, 时间: {timestamp}")

        # 可以选择性添加提取基本信息的功能
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("动作:"):
                    action = line.strip()
                    print(f"    {action}")
                    break
        print()


def main():
    parser = argparse.ArgumentParser(description="HeartFC循环信息查看工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 分析聊天流
    analyze_parser = subparsers.add_parser("analyze", help="分析指定聊天流的循环信息")
    analyze_parser.add_argument("stream_id", help="聊天流ID")

    # 列出聊天流的循环
    list_cycles_parser = subparsers.add_parser("list-cycles", help="列出指定聊天流的循环")
    list_cycles_parser.add_argument("stream_id", help="聊天流ID")
    list_cycles_parser.add_argument("-l", "--limit", type=int, default=-1, help="显示最新的N个循环")

    # 查看指定循环
    view_parser = subparsers.add_parser("view", help="查看指定循环的详细信息")
    view_parser.add_argument("stream_id", help="聊天流ID")
    view_parser.add_argument("cycle_index", type=int, help="循环索引（从1开始）")

    # 查看最新循环
    latest_parser = subparsers.add_parser("latest", help="查看所有聊天流中最新的几个循环")
    latest_parser.add_argument("-c", "--count", type=int, default=10, help="显示的数量")

    args = parser.parse_args()

    analyzer = CycleAnalyzer()

    if args.command == "list-streams":
        list_streams_cmd(analyzer, args)
    elif args.command == "analyze":
        analyze_stream_cmd(analyzer, args)
    elif args.command == "list-cycles":
        list_cycles_cmd(analyzer, args)
    elif args.command == "view":
        view_cycle_cmd(analyzer, args)
    elif args.command == "latest":
        latest_cycles_cmd(analyzer, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
