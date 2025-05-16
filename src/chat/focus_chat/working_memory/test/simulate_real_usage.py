#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import os
import sys
import time
import random
from pathlib import Path
from datetime import datetime

# 添加项目根目录到系统路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.chat.focus_chat.working_memory.working_memory import WorkingMemory
from src.chat.focus_chat.working_memory.memory_item import MemoryItem
from src.common.logger_manager import get_logger

logger = get_logger("real_usage_simulation")

class WorkingMemorySimulator:
    """模拟工作记忆的真实使用场景"""
    
    def __init__(self, chat_id="real_usage_test", cycle_interval=20):
        """
        初始化模拟器
        
        Args:
            chat_id: 聊天ID
            cycle_interval: 循环间隔时间(秒)
        """
        self.chat_id = chat_id
        self.cycle_interval = cycle_interval
        self.working_memory = WorkingMemory(chat_id=chat_id, max_memories_per_chat=20, auto_decay_interval=60)
        self.cycle_count = 0
        self.running = False
        
        # 获取测试文件路径
        self.test_files = self._get_test_files()
        if not self.test_files:
            raise FileNotFoundError("找不到测试文件，请确保test目录中有.txt文件")
            
        # 存储所有添加的记忆ID
        self.memory_ids = []
        
    async def start(self, total_cycles=5):
        """
        开始模拟循环
        
        Args:
            total_cycles: 总循环次数，设为None表示无限循环
        """
        self.running = True
        logger.info(f"开始模拟真实使用场景，循环间隔: {self.cycle_interval}秒")
        
        try:
            while self.running and (total_cycles is None or self.cycle_count < total_cycles):
                self.cycle_count += 1
                logger.info(f"\n===== 开始第 {self.cycle_count} 次循环 =====")
                
                # 执行一次循环
                await self._run_one_cycle()
                
                # 如果还有更多循环，则等待
                if self.running and (total_cycles is None or self.cycle_count < total_cycles):
                    wait_time = self.cycle_interval
                    logger.info(f"等待 {wait_time} 秒后开始下一循环...")
                    await asyncio.sleep(wait_time)
                
            logger.info(f"模拟完成，共执行了 {self.cycle_count} 次循环")
            
        except KeyboardInterrupt:
            logger.info("接收到中断信号，停止模拟")
        except Exception as e:
            logger.error(f"模拟过程中出错: {str(e)}", exc_info=True)
        finally:
            # 关闭工作记忆
            await self.working_memory.shutdown()
    
    def stop(self):
        """停止模拟循环"""
        self.running = False
        logger.info("正在停止模拟...")
    
    async def _run_one_cycle(self):
        """运行一次完整循环：先检索记忆，再添加新记忆"""
        start_time = time.time()
        
        # 1. 先检索已有记忆（如果有）
        await self._retrieve_memories()
        
        # 2. 添加新记忆
        await self._add_new_memory()
        
        # 3. 显示工作记忆状态
        await self._show_memory_status()
        
        # 计算循环耗时
        cycle_duration = time.time() - start_time
        logger.info(f"第 {self.cycle_count} 次循环完成，耗时: {cycle_duration:.2f}秒")
    
    async def _retrieve_memories(self):
        """检索现有记忆"""
        # 如果有已保存的记忆ID，随机选择1-3个进行检索
        if self.memory_ids:
            num_to_retrieve = min(len(self.memory_ids), random.randint(1, 3))
            retrieval_ids = random.sample(self.memory_ids, num_to_retrieve)
            
            logger.info(f"正在检索 {num_to_retrieve} 条记忆...")
            
            for memory_id in retrieval_ids:
                memory = await self.working_memory.retrieve_memory(memory_id)
                if memory:
                    logger.info(f"成功检索记忆 ID: {memory_id}")
                    logger.info(f"  - 强度: {memory.memory_strength:.2f}，检索次数: {memory.retrieval_count}")
                    if memory.summary:
                        logger.info(f"  - 主题: {memory.summary.get('brief', '无主题')}")
                else:
                    logger.warning(f"记忆 ID: {memory_id} 不存在或已被移除")
                    # 从ID列表中移除
                    if memory_id in self.memory_ids:
                        self.memory_ids.remove(memory_id)
        else:
            logger.info("当前没有可检索的记忆")
    
    async def _add_new_memory(self):
        """添加新记忆"""
        # 随机选择一个测试文件作为记忆内容
        file_path = random.choice(self.test_files)
        file_name = os.path.basename(file_path)
        
        try:
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # 添加时间戳，模拟不同内容
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            content_with_timestamp = f"[{timestamp}] {content}"
            
            # 添加记忆
            logger.info(f"正在添加新记忆，来源: {file_name}")
            memory = await self.working_memory.add_memory(
                content=content_with_timestamp,
                from_source=f"模拟_{file_name}",
                tags=["模拟测试", f"循环{self.cycle_count}", file_name]
            )
            
            # 保存记忆ID
            self.memory_ids.append(memory.id)
            
            # 显示记忆信息
            logger.info(f"已添加新记忆 ID: {memory.id}")
            if memory.summary:
                logger.info(f"记忆主题: {memory.summary.get('brief', '无主题')}")
                logger.info(f"记忆要点: {', '.join(memory.summary.get('key_points', ['无要点'])[:2])}...")
                
        except Exception as e:
            logger.error(f"添加记忆失败: {str(e)}")
    
    async def _show_memory_status(self):
        """显示当前工作记忆状态"""
        all_memories = self.working_memory.memory_manager.get_all_items()
        
        logger.info(f"\n当前工作记忆状态:")
        logger.info(f"记忆总数: {len(all_memories)}")
        
        # 按强度排序
        sorted_memories = sorted(all_memories, key=lambda x: x.memory_strength, reverse=True)
        
        logger.info("记忆强度排名 (前5项):")
        for i, memory in enumerate(sorted_memories[:5], 1):
            logger.info(f"{i}. ID: {memory.id}, 强度: {memory.memory_strength:.2f}, "
                      f"检索次数: {memory.retrieval_count}, "
                      f"主题: {memory.summary.get('brief', '无主题') if memory.summary else '无摘要'}")
    
    def _get_test_files(self):
        """获取测试文件列表"""
        test_dir = Path(__file__).parent
        return [
            os.path.join(test_dir, f)
            for f in os.listdir(test_dir)
            if f.endswith(".txt")
        ]

async def main():
    """主函数"""
    # 创建模拟器
    simulator = WorkingMemorySimulator(cycle_interval=20)  # 设置20秒的循环间隔
    
    # 设置运行5个循环
    await simulator.start(total_cycles=5)

if __name__ == "__main__":
    asyncio.run(main()) 