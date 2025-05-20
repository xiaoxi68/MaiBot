import unittest
import sys
import os
import datetime
import time

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.message_repository import find_messages
from src.chat.utils.chat_message_builder import get_raw_msg_by_timestamp_with_chat


class TestExtractMessages(unittest.TestCase):
    def setUp(self):
        # 这个测试使用真实的数据库，所以不需要创建测试数据
        pass

    def test_extract_latest_messages_direct(self):
        """测试直接使用message_repository.find_messages函数"""
        chat_id = "5ed68437e28644da51f314f37df68d18"

        # 提取最新的10条消息
        results = find_messages({"chat_id": chat_id}, limit=10)

        # 打印结果数量
        print(f"\n直接使用find_messages，找到 {len(results)} 条消息")

        # 如果有结果，打印一些信息
        if results:
            print("\n消息时间顺序:")
            for idx, msg in enumerate(results):
                msg_time = datetime.datetime.fromtimestamp(msg["time"]).strftime("%Y-%m-%d %H:%M:%S")
                print(f"{idx + 1}. ID: {msg['message_id']}, 时间: {msg_time}")
                print(f"   文本: {msg.get('processed_plain_text', '无文本内容')[:50]}...")

            # 验证结果按时间排序
            times = [msg["time"] for msg in results]
            self.assertEqual(times, sorted(times), "消息应该按时间升序排列")
        else:
            print(f"未找到chat_id为 {chat_id} 的消息")

        # 最基本的断言，确保测试有效
        self.assertIsInstance(results, list, "结果应该是一个列表")

    def test_extract_latest_messages_via_builder(self):
        """使用chat_message_builder中的函数测试从真实数据库提取消息"""
        chat_id = "5ed68437e28644da51f314f37df68d18"

        # 设置时间范围为过去30天到现在
        current_time = time.time()
        thirty_days_ago = current_time - (30 * 24 * 60 * 60)  # 30天前的时间戳

        # 使用chat_message_builder中的函数
        results = get_raw_msg_by_timestamp_with_chat(
            chat_id=chat_id, timestamp_start=thirty_days_ago, timestamp_end=current_time, limit=10, limit_mode="latest"
        )

        # 打印结果数量
        print(f"\n使用get_raw_msg_by_timestamp_with_chat，找到 {len(results)} 条消息")

        # 如果有结果，打印一些信息
        if results:
            print("\n消息时间顺序:")
            for idx, msg in enumerate(results):
                msg_time = datetime.datetime.fromtimestamp(msg["time"]).strftime("%Y-%m-%d %H:%M:%S")
                print(f"{idx + 1}. ID: {msg['message_id']}, 时间: {msg_time}")
                print(f"   文本: {msg.get('processed_plain_text', '无文本内容')[:50]}...")

            # 验证结果按时间排序
            times = [msg["time"] for msg in results]
            self.assertEqual(times, sorted(times), "消息应该按时间升序排列")
        else:
            print(f"未找到chat_id为 {chat_id} 的消息")

        # 最基本的断言，确保测试有效
        self.assertIsInstance(results, list, "结果应该是一个列表")


if __name__ == "__main__":
    unittest.main()
