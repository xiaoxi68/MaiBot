import unittest
import datetime
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from peewee import SqliteDatabase
from src.common.database.database_model import Messages, BaseModel
from src.common.message_repository import find_messages


class TestMessageRepository(unittest.TestCase):
    def setUp(self):
        # 创建内存中的SQLite数据库用于测试
        self.test_db = SqliteDatabase(":memory:")

        # 覆盖原有数据库连接
        BaseModel._meta.database = self.test_db
        Messages._meta.database = self.test_db

        # 创建表
        self.test_db.create_tables([Messages])

        # 添加测试数据
        current_time = datetime.datetime.now().timestamp()
        self.test_messages = [
            {
                "message_id": "msg1",
                "time": current_time - 3600,  # 1小时前
                "chat_id": "5ed68437e28644da51f314f37df68d18",
                "chat_info_stream_id": "stream1",
                "chat_info_platform": "qq",
                "chat_info_user_platform": "qq",
                "chat_info_user_id": "user1",
                "chat_info_user_nickname": "用户1",
                "chat_info_user_cardname": "卡片名1",
                "chat_info_group_platform": "qq",
                "chat_info_group_id": "group1",
                "chat_info_group_name": "群组1",
                "chat_info_create_time": current_time - 7200,  # 2小时前
                "chat_info_last_active_time": current_time - 1800,  # 30分钟前
                "user_platform": "qq",
                "user_id": "user1",
                "user_nickname": "用户1",
                "user_cardname": "卡片名1",
                "processed_plain_text": "你好",
                "detailed_plain_text": "你好",
                "memorized_times": 1,
            },
            {
                "message_id": "msg2",
                "time": current_time - 1800,  # 30分钟前
                "chat_id": "chat1",
                "chat_info_stream_id": "stream1",
                "chat_info_platform": "qq",
                "chat_info_user_platform": "qq",
                "chat_info_user_id": "user1",
                "chat_info_user_nickname": "用户1",
                "chat_info_user_cardname": "卡片名1",
                "chat_info_group_platform": "qq",
                "chat_info_group_id": "group1",
                "chat_info_group_name": "群组1",
                "chat_info_create_time": current_time - 7200,
                "chat_info_last_active_time": current_time - 900,  # 15分钟前
                "user_platform": "qq",
                "user_id": "user1",
                "user_nickname": "用户1",
                "user_cardname": "卡片名1",
                "processed_plain_text": "世界",
                "detailed_plain_text": "世界",
                "memorized_times": 2,
            },
            {
                "message_id": "msg3",
                "time": current_time - 900,  # 15分钟前
                "chat_id": "chat2",
                "chat_info_stream_id": "stream2",
                "chat_info_platform": "wechat",
                "chat_info_user_platform": "wechat",
                "chat_info_user_id": "user2",
                "chat_info_user_nickname": "用户2",
                "chat_info_user_cardname": "卡片名2",
                "chat_info_group_platform": "wechat",
                "chat_info_group_id": "group2",
                "chat_info_group_name": "群组2",
                "chat_info_create_time": current_time - 3600,
                "chat_info_last_active_time": current_time - 600,  # 10分钟前
                "user_platform": "wechat",
                "user_id": "user2",
                "user_nickname": "用户2",
                "user_cardname": "卡片名2",
                "processed_plain_text": "测试",
                "detailed_plain_text": "测试",
                "memorized_times": 0,
            },
        ]

        for msg_data in self.test_messages:
            Messages.create(**msg_data)

    def tearDown(self):
        # 关闭测试数据库连接
        self.test_db.close()

    def test_find_messages_no_filter(self):
        """测试不带过滤器的查询"""
        results = find_messages({})
        self.assertEqual(len(results), 3)
        # 验证结果是否按时间升序排列
        self.assertEqual(results[0]["message_id"], "msg1")
        self.assertEqual(results[1]["message_id"], "msg2")
        self.assertEqual(results[2]["message_id"], "msg3")

    def test_find_messages_with_filter(self):
        """测试带过滤器的查询"""
        results = find_messages({"chat_id": "chat1"})
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["message_id"], "msg1")
        self.assertEqual(results[1]["message_id"], "msg2")

        results = find_messages({"user_id": "user2"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message_id"], "msg3")

    def test_find_messages_with_operators(self):
        """测试带操作符的查询"""
        results = find_messages({"memorized_times": {"$gt": 0}})
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["message_id"], "msg1")
        self.assertEqual(results[1]["message_id"], "msg2")

        results = find_messages({"memorized_times": {"$gte": 2}})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message_id"], "msg2")

    def test_find_messages_with_sort(self):
        """测试带排序的查询"""
        results = find_messages({}, sort=[("memorized_times", -1)])
        self.assertEqual(len(results), 3)
        # 验证结果是否按memorized_times降序排列
        self.assertEqual(results[0]["message_id"], "msg2")  # memorized_times = 2
        self.assertEqual(results[1]["message_id"], "msg1")  # memorized_times = 1
        self.assertEqual(results[2]["message_id"], "msg3")  # memorized_times = 0

    def test_find_messages_with_limit(self):
        """测试带限制的查询"""
        # 默认limit_mode为latest，应返回最新的2条记录
        results = find_messages({}, limit=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["message_id"], "msg2")
        self.assertEqual(results[1]["message_id"], "msg3")

        # 使用earliest模式，应返回最早的2条记录
        results = find_messages({}, limit=2, limit_mode="earliest")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["message_id"], "msg1")
        self.assertEqual(results[1]["message_id"], "msg2")

    def test_find_messages_with_combined_criteria(self):
        """测试组合查询条件"""
        results = find_messages(
            {"chat_info_platform": "qq", "memorized_times": {"$gt": 0}}, sort=[("time", 1)], limit=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message_id"], "msg2")


if __name__ == "__main__":
    unittest.main()
