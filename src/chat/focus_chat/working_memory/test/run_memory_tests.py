#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到系统路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.chat.focus_chat.working_memory.working_memory import WorkingMemory

async def test_load_memories_from_files():
    """测试从文件加载记忆的功能"""
    print("开始测试从文件加载记忆...")
    
    # 初始化工作记忆
    chat_id = "test_memory_load"
    working_memory = WorkingMemory(chat_id=chat_id, max_memories_per_chat=10, auto_decay_interval=60)
    
    try:
        # 获取测试文件列表
        test_dir = Path(__file__).parent
        test_files = [
            os.path.join(test_dir, f)
            for f in os.listdir(test_dir)
            if f.endswith(".txt")
        ]
        
        print(f"找到 {len(test_files)} 个测试文件")
        
        # 从每个文件加载记忆
        for file_path in test_files:
            file_name = os.path.basename(file_path)
            print(f"从文件 {file_name} 加载记忆...")
            
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 添加记忆
            memory = await working_memory.add_memory(
                content=content,
                from_source=f"文件_{file_name}",
                tags=["测试文件", file_name]
            )
            
            print(f"已添加记忆: ID={memory.id}")
            if memory.summary:
                print(f"记忆概要: {memory.summary.get('brief', '无概要')}")
                print(f"记忆要点: {', '.join(memory.summary.get('key_points', ['无要点']))}")
            print("-" * 50)
        
        # 获取所有记忆
        all_memories = working_memory.memory_manager.get_all_items()
        print(f"\n成功加载 {len(all_memories)} 个记忆")
        
        # 测试检索记忆
        if all_memories:
            print("\n测试检索第一个记忆...")
            first_memory = all_memories[0]
            retrieved = await working_memory.retrieve_memory(first_memory.id)
            
            if retrieved:
                print(f"成功检索记忆: ID={retrieved.id}")
                print(f"检索后强度: {retrieved.memory_strength} (初始为10.0)")
                print(f"检索次数: {retrieved.retrieval_count}")
            else:
                print("检索失败")
        
        # 测试记忆衰减
        print("\n测试记忆衰减...")
        for memory in all_memories:
            print(f"记忆 {memory.id} 衰减前强度: {memory.memory_strength}")
        
        await working_memory.decay_all_memories(decay_factor=0.5)
        
        all_memories_after = working_memory.memory_manager.get_all_items()
        for memory in all_memories_after:
            print(f"记忆 {memory.id} 衰减后强度: {memory.memory_strength}")
    
    finally:
        # 关闭工作记忆
        await working_memory.shutdown()
        print("\n测试完成，已关闭工作记忆")

if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_load_memories_from_files()) 