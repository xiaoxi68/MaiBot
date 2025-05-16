#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.chat.focus_chat.working_memory.working_memory import WorkingMemory
from src.chat.focus_chat.working_memory.memory_item import MemoryItem
from src.common.logger_manager import get_logger

logger = get_logger("memory_loader")

class MemoryFileLoader:
    """从文件加载记忆内容的工具类"""
    
    def __init__(self, working_memory: WorkingMemory):
        """
        初始化记忆文件加载器
        
        Args:
            working_memory: 工作记忆实例
        """
        self.working_memory = working_memory
    
    async def load_from_directory(self, 
                                directory_path: str, 
                                file_pattern: str = "*.txt",
                                common_tags: List[str] = None,
                                source_prefix: str = "文件") -> List[MemoryItem]:
        """
        从指定目录加载符合模式的文件作为记忆
        
        Args:
            directory_path: 目录路径
            file_pattern: 文件模式（默认为*.txt）
            common_tags: 所有记忆共有的标签
            source_prefix: 来源前缀
            
        Returns:
            加载的记忆项列表
        """
        directory = Path(directory_path)
        if not directory.exists() or not directory.is_dir():
            logger.error(f"目录不存在或不是有效目录: {directory_path}")
            return []
        
        # 获取文件列表
        files = list(directory.glob(file_pattern))
        if not files:
            logger.warning(f"在目录 {directory_path} 中没有找到符合 {file_pattern} 的文件")
            return []
        
        logger.info(f"在目录 {directory_path} 中找到 {len(files)} 个符合条件的文件")
        
        # 加载文件内容为记忆
        loaded_memories = []
        for file_path in files:
            try:
                memory_item = await self._load_single_file(
                    file_path=str(file_path),
                    common_tags=common_tags,
                    source_prefix=source_prefix
                )
                if memory_item:
                    loaded_memories.append(memory_item)
                    logger.info(f"成功加载记忆: {file_path.name}")
                
            except Exception as e:
                logger.error(f"加载文件 {file_path} 失败: {str(e)}")
        
        logger.info(f"完成加载，共加载了 {len(loaded_memories)} 个记忆")
        return loaded_memories
    
    async def _load_single_file(self, 
                              file_path: str, 
                              common_tags: Optional[List[str]] = None,
                              source_prefix: str = "文件") -> Optional[MemoryItem]:
        """
        加载单个文件作为记忆
        
        Args:
            file_path: 文件路径
            common_tags: 记忆共有的标签
            source_prefix: 来源前缀
            
        Returns:
            记忆项，加载失败则返回None
        """
        try:
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if not content.strip():
                logger.warning(f"文件 {file_path} 内容为空")
                return None
            
            # 准备标签和来源
            file_name = os.path.basename(file_path)
            tags = list(common_tags) if common_tags else []
            tags.append(file_name)  # 添加文件名作为标签
            
            source = f"{source_prefix}_{file_name}"
            
            # 添加到工作记忆
            memory = await self.working_memory.add_memory(
                content=content,
                from_source=source,
                tags=tags
            )
            
            return memory
            
        except Exception as e:
            logger.error(f"加载文件 {file_path} 失败: {str(e)}")
            return None


async def main():
    """示例使用"""
    # 初始化工作记忆
    chat_id = "demo_chat"
    working_memory = WorkingMemory(chat_id=chat_id)
    
    try:
        # 初始化加载器
        loader = MemoryFileLoader(working_memory)
        
        # 加载当前目录中的txt文件
        current_dir = Path(__file__).parent
        memories = await loader.load_from_directory(
            directory_path=str(current_dir),
            file_pattern="*.txt",
            common_tags=["测试数据", "自动加载"],
            source_prefix="测试文件"
        )
        
        # 显示加载结果
        print(f"共加载了 {len(memories)} 个记忆")
        
        # 获取并显示所有记忆的概要
        all_memories = working_memory.memory_manager.get_all_items()
        for memory in all_memories:
            print("\n" + "=" * 40)
            print(f"记忆ID: {memory.id}")
            print(f"来源: {memory.from_source}")
            print(f"标签: {', '.join(memory.tags)}")
            
            if memory.summary:
                print(f"\n主题: {memory.summary.get('brief', '无主题')}")
                print(f"概述: {memory.summary.get('detailed', '无概述')}")
                print("\n要点:")
                for point in memory.summary.get('key_points', []):
                    print(f"- {point}")
            else:
                print("\n无摘要信息")
            
            print("=" * 40)
    
    finally:
        # 关闭工作记忆
        await working_memory.shutdown()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main()) 