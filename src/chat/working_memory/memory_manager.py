from typing import Dict, TypeVar, List, Optional
import traceback
from json_repair import repair_json
from rich.traceback import install
from src.common.logger import get_logger
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
from src.chat.focus_chat.working_memory.memory_item import MemoryItem
import json  # 添加json模块导入


install(extra_lines=3)
logger = get_logger("working_memory")

T = TypeVar("T")


class MemoryManager:
    def __init__(self, chat_id: str):
        """
        初始化工作记忆

        Args:
            chat_id: 关联的聊天ID，用于标识该工作记忆属于哪个聊天
        """
        # 关联的聊天ID
        self._chat_id = chat_id

        # 记忆项列表
        self._memories: List[MemoryItem] = []

        # ID到记忆项的映射
        self._id_map: Dict[str, MemoryItem] = {}

        self.llm_summarizer = LLMRequest(
            model=global_config.model.memory,
            temperature=0.3,
            request_type="working_memory",
        )

    @property
    def chat_id(self) -> str:
        """获取关联的聊天ID"""
        return self._chat_id

    @chat_id.setter
    def chat_id(self, value: str):
        """设置关联的聊天ID"""
        self._chat_id = value

    def push_item(self, memory_item: MemoryItem) -> str:
        """
        推送一个已创建的记忆项到工作记忆中

        Args:
            memory_item: 要存储的记忆项

        Returns:
            记忆项的ID
        """
        # 添加到内存和ID映射
        self._memories.append(memory_item)
        self._id_map[memory_item.id] = memory_item

        return memory_item.id

    def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """
        通过ID获取记忆项

        Args:
            memory_id: 记忆项ID

        Returns:
            找到的记忆项，如果不存在则返回None
        """
        memory_item = self._id_map.get(memory_id)
        if memory_item:
            # 检查记忆强度，如果小于1则删除
            if not memory_item.is_memory_valid():
                print(f"记忆 {memory_id} 强度过低 ({memory_item.memory_strength})，已自动移除")
                self.delete(memory_id)
                return None

        return memory_item

    def get_all_items(self) -> List[MemoryItem]:
        """获取所有记忆项"""
        return list(self._id_map.values())

    def find_items(
        self,
        source: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        memory_id: Optional[str] = None,
        limit: Optional[int] = None,
        newest_first: bool = False,
        min_strength: float = 0.0,
    ) -> List[MemoryItem]:
        """
        按条件查找记忆项

        Args:
            source: 数据来源
            start_time: 开始时间戳
            end_time: 结束时间戳
            memory_id: 特定记忆项ID
            limit: 返回结果的最大数量
            newest_first: 是否按最新优先排序
            min_strength: 最小记忆强度

        Returns:
            符合条件的记忆项列表
        """
        # 如果提供了特定ID，直接查找
        if memory_id:
            item = self.get_by_id(memory_id)
            return [item] if item else []

        results = []

        # 获取所有项目
        items = self._memories

        # 如果需要最新优先，则反转遍历顺序
        if newest_first:
            items_to_check = list(reversed(items))
        else:
            items_to_check = items

        # 遍历项目
        for item in items_to_check:
            # 检查来源是否匹配
            if source is not None and not item.matches_source(source):
                continue

            # 检查时间范围
            if start_time is not None and item.timestamp < start_time:
                continue
            if end_time is not None and item.timestamp > end_time:
                continue

            # 检查记忆强度
            if min_strength > 0 and item.memory_strength < min_strength:
                continue

            # 所有条件都满足，添加到结果中
            results.append(item)

            # 如果达到限制数量，提前返回
            if limit is not None and len(results) >= limit:
                return results

        return results

    async def summarize_memory_item(self, content: str) -> Dict[str, str]:
        """
        使用LLM总结记忆项

        Args:
            content: 需要总结的内容

        Returns:
            包含brief和summary的字典
        """
        prompt = f"""请对以下内容进行总结，总结成记忆，输出两部分：
1. 记忆内容主题（精简，20字以内）：让用户可以一眼看出记忆内容是什么
2. 记忆内容概括：对内容进行概括，保留重要信息，200字以内

内容：
{content}

请按以下JSON格式输出：
{{
  "brief": "记忆内容主题",
  "summary": "记忆内容概括"
}}
请确保输出是有效的JSON格式，不要添加任何额外的说明或解释。
"""
        default_summary = {
            "brief": "主题未知的记忆",
            "summary": "无法概括的记忆内容",
        }

        try:
            # 调用LLM生成总结
            response, _ = await self.llm_summarizer.generate_response_async(prompt)

            # 使用repair_json解析响应
            try:
                # 使用repair_json修复JSON格式
                fixed_json_string = repair_json(response)

                # 如果repair_json返回的是字符串，需要解析为Python对象
                if isinstance(fixed_json_string, str):
                    try:
                        json_result = json.loads(fixed_json_string)
                    except json.JSONDecodeError as decode_error:
                        logger.error(f"JSON解析错误: {str(decode_error)}")
                        return default_summary
                else:
                    # 如果repair_json直接返回了字典对象，直接使用
                    json_result = fixed_json_string

                # 进行额外的类型检查
                if not isinstance(json_result, dict):
                    logger.error(f"修复后的JSON不是字典类型: {type(json_result)}")
                    return default_summary

                # 确保所有必要字段都存在且类型正确
                if "brief" not in json_result or not isinstance(json_result["brief"], str):
                    json_result["brief"] = "主题未知的记忆"

                if "summary" not in json_result or not isinstance(json_result["summary"], str):
                    json_result["summary"] = "无法概括的记忆内容"

                return json_result

            except Exception as json_error:
                logger.error(f"JSON处理失败: {str(json_error)}，将使用默认摘要")
                return default_summary

        except Exception as e:
            logger.error(f"生成总结时出错: {str(e)}")
            return default_summary

    def decay_memory(self, memory_id: str, decay_factor: float = 0.8) -> bool:
        """
        使单个记忆衰减

        Args:
            memory_id: 记忆ID
            decay_factor: 衰减因子(0-1之间)

        Returns:
            是否成功衰减
        """
        memory_item = self.get_by_id(memory_id)
        if not memory_item:
            return False

        # 计算衰减量（当前强度 * (1-衰减因子)）
        old_strength = memory_item.memory_strength
        decay_amount = old_strength * (1 - decay_factor)

        # 更新强度
        memory_item.memory_strength = decay_amount

        return True

    def delete(self, memory_id: str) -> bool:
        """
        删除指定ID的记忆项

        Args:
            memory_id: 要删除的记忆项ID

        Returns:
            是否成功删除
        """
        if memory_id not in self._id_map:
            return False

        # 获取要删除的项
        self._id_map[memory_id]

        # 从内存中删除
        self._memories = [i for i in self._memories if i.id != memory_id]

        # 从ID映射中删除
        del self._id_map[memory_id]

        return True

    def clear(self) -> None:
        """清除所有记忆"""
        self._memories.clear()
        self._id_map.clear()

    async def merge_memories(
        self, memory_id1: str, memory_id2: str, reason: str, delete_originals: bool = True
    ) -> MemoryItem:
        """
        合并两个记忆项

        Args:
            memory_id1: 第一个记忆项ID
            memory_id2: 第二个记忆项ID
            reason: 合并原因
            delete_originals: 是否删除原始记忆，默认为True

        Returns:
            合并后的记忆项
        """
        # 获取两个记忆项
        memory_item1 = self.get_by_id(memory_id1)
        memory_item2 = self.get_by_id(memory_id2)

        if not memory_item1 or not memory_item2:
            raise ValueError("无法找到指定的记忆项")

        # 构建合并提示
        prompt = f"""
请根据以下原因，将两段记忆内容有机合并成一段新的记忆内容。
合并时保留两段记忆的重要信息，避免重复，确保生成的内容连贯、自然。

合并原因：{reason}

记忆1主题：{memory_item1.brief}
记忆1内容：{memory_item1.summary}

记忆2主题：{memory_item2.brief}
记忆2内容：{memory_item2.summary}

请按以下JSON格式输出合并结果：
{{
    "brief": "合并后的主题（20字以内）",
    "summary": "合并后的内容概括（200字以内）"
}}
请确保输出是有效的JSON格式，不要添加任何额外的说明或解释。
"""

        # 默认合并结果
        default_merged = {
            "brief": f"合并：{memory_item1.brief} + {memory_item2.brief}",
            "summary": f"合并的记忆：{memory_item1.summary}\n{memory_item2.summary}",
        }

        try:
            # 调用LLM合并记忆
            response, _ = await self.llm_summarizer.generate_response_async(prompt)

            # 处理LLM返回的合并结果
            try:
                # 修复JSON格式
                fixed_json_string = repair_json(response)

                # 将修复后的字符串解析为Python对象
                if isinstance(fixed_json_string, str):
                    try:
                        merged_data = json.loads(fixed_json_string)
                    except json.JSONDecodeError as decode_error:
                        logger.error(f"JSON解析错误: {str(decode_error)}")
                        merged_data = default_merged
                else:
                    # 如果repair_json直接返回了字典对象，直接使用
                    merged_data = fixed_json_string

                # 确保是字典类型
                if not isinstance(merged_data, dict):
                    logger.error(f"修复后的JSON不是字典类型: {type(merged_data)}")
                    merged_data = default_merged

                if "brief" not in merged_data or not isinstance(merged_data["brief"], str):
                    merged_data["brief"] = default_merged["brief"]

                if "summary" not in merged_data or not isinstance(merged_data["summary"], str):
                    merged_data["summary"] = default_merged["summary"]

            except Exception as e:
                logger.error(f"合并记忆时处理JSON出错: {str(e)}")
                traceback.print_exc()
                merged_data = default_merged
        except Exception as e:
            logger.error(f"合并记忆调用LLM出错: {str(e)}")
            traceback.print_exc()
            merged_data = default_merged

        # 创建新的记忆项
        # 取两个记忆项中更强的来源
        merged_source = (
            memory_item1.from_source
            if memory_item1.memory_strength >= memory_item2.memory_strength
            else memory_item2.from_source
        )

        # 创建新的记忆项
        merged_memory = MemoryItem(
            summary=merged_data["summary"], from_source=merged_source, brief=merged_data["brief"]
        )

        # 记忆强度取两者最大值
        merged_memory.memory_strength = max(memory_item1.memory_strength, memory_item2.memory_strength)

        # 添加到存储中
        self.push_item(merged_memory)

        # 如果需要，删除原始记忆
        if delete_originals:
            self.delete(memory_id1)
            self.delete(memory_id2)

        return merged_memory

    def delete_earliest_memory(self) -> bool:
        """
        删除最早的记忆项

        Returns:
            是否成功删除
        """
        # 获取所有记忆项
        all_memories = self.get_all_items()

        if not all_memories:
            return False

        # 按时间戳排序，找到最早的记忆项
        earliest_memory = min(all_memories, key=lambda item: item.timestamp)

        # 删除最早的记忆项
        return self.delete(earliest_memory.id)
