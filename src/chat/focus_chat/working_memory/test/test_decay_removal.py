#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到系统路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.chat.focus_chat.working_memory.working_memory import WorkingMemory
from src.chat.focus_chat.working_memory.test.memory_file_loader import MemoryFileLoader
from src.common.logger_manager import get_logger

logger = get_logger("memory_decay_test")

async def test_manual_decay_until_removal():
    """测试手动衰减直到记忆被自动移除"""
    print("\n===== 测试手动衰减直到记忆被自动移除 =====")
    
    # 初始化工作记忆，设置较大的衰减间隔，避免自动衰减影响测试
    chat_id = "decay_test_manual"
    working_memory = WorkingMemory(chat_id=chat_id, max_memories_per_chat=10, auto_decay_interval=3600)
    
    try:
        # 创建加载器并加载测试文件
        loader = MemoryFileLoader(working_memory)
        test_dir = current_dir
        
        # 加载第一个测试文件作为记忆
        memories = await loader.load_from_directory(
            directory_path=str(test_dir),
            file_pattern="test1.txt",  # 只加载test1.txt
            common_tags=["测试", "衰减", "自动移除"],
            source_prefix="衰减测试"
        )
        
        if not memories:
            print("未能加载记忆文件，测试结束")
            return
            
        # 获取加载的记忆
        memory = memories[0]
        memory_id = memory.id
        print(f"已加载测试记忆，ID: {memory_id}")
        print(f"初始强度: {memory.memory_strength}")
        if memory.summary:
            print(f"记忆主题: {memory.summary.get('brief', '无主题')}")
        
        # 执行多次衰减，直到记忆被移除
        decay_count = 0
        decay_factor = 0.5  # 每次衰减为原来的一半
        
        while True:
            # 获取当前记忆
            current_memory = working_memory.memory_manager.get_by_id(memory_id)
            
            # 如果记忆已被移除，退出循环
            if current_memory is None:
                print(f"记忆已在第 {decay_count} 次衰减后被自动移除!")
                break
                
            # 输出当前强度
            print(f"衰减 {decay_count} 次后强度: {current_memory.memory_strength}")
            
            # 执行衰减
            await working_memory.decay_all_memories(decay_factor=decay_factor)
            decay_count += 1
            
            # 输出衰减后的详细信息
            after_memory = working_memory.memory_manager.get_by_id(memory_id)
            if after_memory:
                print(f"第 {decay_count} 次衰减结果: 强度={after_memory.memory_strength}，压缩次数={after_memory.compress_count}")
                if after_memory.summary:
                    print(f"记忆概要: {after_memory.summary.get('brief', '无概要')}")
                    print(f"记忆要点数量: {len(after_memory.summary.get('key_points', []))}")
            else:
                print(f"第 {decay_count} 次衰减结果: 记忆已被移除")
                
            # 防止无限循环
            if decay_count > 20:
                print("达到最大衰减次数(20)，退出测试。")
                break
                
            # 短暂等待
            await asyncio.sleep(0.5)
        
        # 验证记忆是否真的被移除
        all_memories = working_memory.memory_manager.get_all_items()
        print(f"剩余记忆数量: {len(all_memories)}")
        if len(all_memories) == 0:
            print("测试通过: 记忆在强度低于阈值后被成功移除。")
        else:
            print("测试失败: 记忆应该被移除但仍然存在。")
            
    finally:
        await working_memory.shutdown()

async def test_auto_decay():
    """测试自动衰减功能"""
    print("\n===== 测试自动衰减功能 =====")
    
    # 初始化工作记忆，设置短的衰减间隔，便于测试
    chat_id = "decay_test_auto"
    decay_interval = 3  # 3秒
    working_memory = WorkingMemory(chat_id=chat_id, max_memories_per_chat=10, auto_decay_interval=decay_interval)
    
    try:
        # 创建加载器并加载测试文件
        loader = MemoryFileLoader(working_memory)
        test_dir = current_dir
        
        # 加载第二个测试文件作为记忆
        memories = await loader.load_from_directory(
            directory_path=str(test_dir),
            file_pattern="test1.txt",  # 只加载test2.txt
            common_tags=["测试", "自动衰减"],
            source_prefix="自动衰减测试"
        )
        
        if not memories:
            print("未能加载记忆文件，测试结束")
            return
            
        # 获取加载的记忆
        memory = memories[0]
        memory_id = memory.id
        print(f"已加载测试记忆，ID: {memory_id}")
        print(f"初始强度: {memory.memory_strength}")
        if memory.summary:
            print(f"记忆主题: {memory.summary.get('brief', '无主题')}")
            print(f"记忆概要: {memory.summary.get('detailed', '无概要')}")
            print(f"记忆要点: {memory.summary.get('keypoints', '无要点')}")
            print(f"记忆事件: {memory.summary.get('events', '无事件')}")
        # 观察自动衰减
        print(f"等待自动衰减任务执行 (间隔 {decay_interval} 秒)...")
        
        for i in range(3):  # 观察3次自动衰减
            # 等待自动衰减发生
            await asyncio.sleep(decay_interval + 1)  # 多等1秒确保任务执行
            
            # 获取当前记忆
            current_memory = working_memory.memory_manager.get_by_id(memory_id)
            
            # 如果记忆已被移除，退出循环
            if current_memory is None:
                print(f"记忆已在第 {i+1} 次自动衰减后被移除!")
                break
                
            # 输出当前强度和详细信息
            print(f"第 {i+1} 次自动衰减后强度: {current_memory.memory_strength}")
            print(f"自动衰减详细结果: 压缩次数={current_memory.compress_count}, 提取次数={current_memory.retrieval_count}")
            if current_memory.summary:
                print(f"记忆概要: {current_memory.summary.get('brief', '无概要')}")
        
        print(f"\n自动衰减测试结束。")
        
        # 验证自动衰减是否发生
        final_memory = working_memory.memory_manager.get_by_id(memory_id)
        if final_memory is None:
            print("记忆已被自动衰减移除。")
        elif final_memory.memory_strength < memory.memory_strength:
            print(f"自动衰减有效：初始强度 {memory.memory_strength} -> 最终强度 {final_memory.memory_strength}")
            print(f"衰减历史记录: {final_memory.history}")
        else:
            print("测试失败：记忆强度未减少，自动衰减可能未生效。")
            
    finally:
        await working_memory.shutdown()

async def test_decay_and_retrieval_balance():
    """测试记忆衰减和检索的平衡"""
    print("\n===== 测试记忆衰减和检索的平衡 =====")
    
    # 初始化工作记忆
    chat_id = "decay_retrieval_balance"
    working_memory = WorkingMemory(chat_id=chat_id, max_memories_per_chat=10, auto_decay_interval=60)
    
    try:
        # 创建加载器并加载测试文件
        loader = MemoryFileLoader(working_memory)
        test_dir = current_dir
        
        # 加载第三个测试文件作为记忆
        memories = await loader.load_from_directory(
            directory_path=str(test_dir),
            file_pattern="test3.txt",  # 只加载test3.txt
            common_tags=["测试", "衰减", "检索"],
            source_prefix="平衡测试"
        )
        
        if not memories:
            print("未能加载记忆文件，测试结束")
            return
            
        # 获取加载的记忆
        memory = memories[0]
        memory_id = memory.id
        print(f"已加载测试记忆，ID: {memory_id}")
        print(f"初始强度: {memory.memory_strength}")
        if memory.summary:
            print(f"记忆主题: {memory.summary.get('brief', '无主题')}")
        
        # 先衰减几次
        print("\n开始衰减：")
        for i in range(3):
            await working_memory.decay_all_memories(decay_factor=0.5)
            current = working_memory.memory_manager.get_by_id(memory_id)
            if current:
                print(f"衰减 {i+1} 次后强度: {current.memory_strength}")
                print(f"衰减详细信息: 压缩次数={current.compress_count}, 历史操作数={len(current.history)}")
                if current.summary:
                    print(f"记忆概要: {current.summary.get('brief', '无概要')}")
            else:
                print(f"记忆已在第 {i+1} 次衰减后被移除。")
                break
        
        # 如果记忆还存在，则检索几次增强它
        current = working_memory.memory_manager.get_by_id(memory_id)
        if current:
            print("\n开始检索增强：")
            for i in range(2):
                retrieved = await working_memory.retrieve_memory(memory_id)
                print(f"检索 {i+1} 次后强度: {retrieved.memory_strength}")
                print(f"检索后详细信息: 提取次数={retrieved.retrieval_count}, 历史记录长度={len(retrieved.history)}")
            
            # 再次衰减几次，测试是否会被移除
            print("\n再次衰减：")
            for i in range(5):
                await working_memory.decay_all_memories(decay_factor=0.5)
                current = working_memory.memory_manager.get_by_id(memory_id)
                if current:
                    print(f"最终衰减 {i+1} 次后强度: {current.memory_strength}")
                    print(f"衰减详细结果: 压缩次数={current.compress_count}")
                else:
                    print(f"记忆已在最终衰减第 {i+1} 次后被移除。")
                    break
        
        print("\n测试结束。")
            
    finally:
        await working_memory.shutdown()

async def test_multi_memories_decay():
    """测试多条记忆同时衰减"""
    print("\n===== 测试多条记忆同时衰减 =====")
    
    # 初始化工作记忆
    chat_id = "multi_decay_test"
    working_memory = WorkingMemory(chat_id=chat_id, max_memories_per_chat=10, auto_decay_interval=60)
    
    try:
        # 创建加载器并加载所有测试文件
        loader = MemoryFileLoader(working_memory)
        test_dir = current_dir
        
        # 加载所有测试文件作为记忆
        memories = await loader.load_from_directory(
            directory_path=str(test_dir),
            file_pattern="*.txt",
            common_tags=["测试", "多记忆衰减"],
            source_prefix="多记忆测试"
        )
        
        if not memories or len(memories) < 2:
            print("未能加载足够的记忆文件，测试结束")
            return
        
        # 显示已加载的记忆
        print(f"已加载 {len(memories)} 条记忆:")
        for idx, mem in enumerate(memories):
            print(f"{idx+1}. ID: {mem.id}, 强度: {mem.memory_strength}, 来源: {mem.from_source}")
            if mem.summary:
                print(f"   主题: {mem.summary.get('brief', '无主题')}")
        
        # 进行多次衰减测试
        print("\n开始多记忆衰减测试:")
        for decay_round in range(5):
            # 执行衰减
            await working_memory.decay_all_memories(decay_factor=0.5)
            
            # 获取并显示所有记忆
            all_memories = working_memory.memory_manager.get_all_items()
            print(f"\n第 {decay_round+1} 次衰减后，剩余记忆数量: {len(all_memories)}")
            
            for idx, mem in enumerate(all_memories):
                print(f"{idx+1}. ID: {mem.id}, 强度: {mem.memory_strength}, 压缩次数: {mem.compress_count}")
                if mem.summary:
                    print(f"   概要: {mem.summary.get('brief', '无概要')[:30]}...")
            
            # 如果所有记忆都被移除，退出循环
            if not all_memories:
                print("所有记忆已被移除，测试结束。")
                break
            
            # 等待一下
            await asyncio.sleep(0.5)
        
        print("\n多记忆衰减测试结束。")
    
    finally:
        await working_memory.shutdown()

async def main():
    """运行所有测试"""
    # 测试手动衰减直到移除
    await test_manual_decay_until_removal()
    
    # 测试自动衰减
    await test_auto_decay()
    
    # 测试衰减和检索的平衡
    await test_decay_and_retrieval_balance()
    
    # 测试多条记忆同时衰减
    await test_multi_memories_decay()

if __name__ == "__main__":
    asyncio.run(main()) 