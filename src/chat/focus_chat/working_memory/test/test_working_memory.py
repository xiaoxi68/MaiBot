import asyncio
import os
import unittest
from typing import List, Dict, Any
from pathlib import Path

from src.chat.focus_chat.working_memory.working_memory import WorkingMemory
from src.chat.focus_chat.working_memory.memory_item import MemoryItem

class TestWorkingMemory(unittest.TestCase):
    """工作记忆测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.chat_id = "test_chat_123"
        self.working_memory = WorkingMemory(chat_id=self.chat_id, max_memories_per_chat=10, auto_decay_interval=60)
        self.test_dir = Path(__file__).parent
        
    def tearDown(self):
        """测试后清理"""
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.working_memory.shutdown())
        
    def test_init(self):
        """测试初始化"""
        self.assertEqual(self.working_memory.max_memories_per_chat, 10)
        self.assertEqual(self.working_memory.auto_decay_interval, 60)
        
    def test_add_memory_from_files(self):
        """从文件添加记忆"""
        loop = asyncio.get_event_loop()
        test_files = self._get_test_files()
        
        # 添加记忆
        memories = []
        for file_path in test_files:
            content = self._read_file_content(file_path)
            file_name = os.path.basename(file_path)
            source = f"test_file_{file_name}"
            tags = ["测试", f"文件_{file_name}"]
            
            memory = loop.run_until_complete(
                self.working_memory.add_memory(
                    content=content,
                    from_source=source,
                    tags=tags
                )
            )
            memories.append(memory)
            
        # 验证记忆数量
        all_items = self.working_memory.memory_manager.get_all_items()
        self.assertEqual(len(all_items), len(test_files))
        
        # 验证每个记忆的内容和标签
        for i, memory in enumerate(memories):
            file_name = os.path.basename(test_files[i])
            retrieved_memory = loop.run_until_complete(
                self.working_memory.retrieve_memory(memory.id)
            )
            
            self.assertIsNotNone(retrieved_memory)
            self.assertTrue(retrieved_memory.has_tag("测试"))
            self.assertTrue(retrieved_memory.has_tag(f"文件_{file_name}"))
            self.assertEqual(retrieved_memory.from_source, f"test_file_{file_name}")
            
            # 验证检索后强度增加
            self.assertGreater(retrieved_memory.memory_strength, 10.0)  # 原始强度为10.0，检索后增加1.5倍
            self.assertEqual(retrieved_memory.retrieval_count, 1)
        
    def test_decay_memories(self):
        """测试记忆衰减"""
        loop = asyncio.get_event_loop()
        test_files = self._get_test_files()[:1]  # 只使用一个文件测试衰减
        
        # 添加记忆
        for file_path in test_files:
            content = self._read_file_content(file_path)
            loop.run_until_complete(
                self.working_memory.add_memory(
                    content=content,
                    from_source="decay_test",
                    tags=["衰减测试"]
                )
            )
            
        # 获取添加后的记忆项
        all_items_before = self.working_memory.memory_manager.get_all_items()
        self.assertEqual(len(all_items_before), 1)
        
        # 记录原始强度
        original_strength = all_items_before[0].memory_strength
        
        # 执行衰减
        loop.run_until_complete(
            self.working_memory.decay_all_memories(decay_factor=0.5)
        )
        
        # 获取衰减后的记忆项
        all_items_after = self.working_memory.memory_manager.get_all_items()
        
        # 验证强度衰减
        self.assertEqual(len(all_items_after), 1)
        self.assertLess(all_items_after[0].memory_strength, original_strength)
    
    def _get_test_files(self) -> List[str]:
        """获取测试文件列表"""
        test_dir = self.test_dir
        return [
            os.path.join(test_dir, f)
            for f in os.listdir(test_dir)
            if f.endswith(".txt")
        ]
    
    def _read_file_content(self, file_path: str) -> str:
        """读取文件内容"""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

if __name__ == "__main__":
    unittest.main() 