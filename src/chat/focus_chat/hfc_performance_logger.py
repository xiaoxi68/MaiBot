import json
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path
from src.common.logger import get_logger

logger = get_logger("hfc_performance")


class HFCPerformanceLogger:
    """HFC性能记录管理器"""

    # 版本号常量，可在启动时修改
    INTERNAL_VERSION = "v1.0.0"

    def __init__(self, chat_id: str, version: str = None):
        self.chat_id = chat_id
        self.version = version or self.INTERNAL_VERSION
        self.log_dir = Path("log/hfc_loop")
        self.data_dir = Path("data/hfc")
        self.session_start_time = datetime.now()

        # 确保目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 当前会话的日志文件，包含版本号
        version_suffix = self.version.replace(".", "_")
        self.session_file = (
            self.log_dir / f"{chat_id}_{version_suffix}_{self.session_start_time.strftime('%Y%m%d_%H%M%S')}.json"
        )
        self.current_session_data = []

        # 统计数据文件
        self.stats_file = self.data_dir / "time.json"

        # 初始化时计算历史统计数据
        self._update_historical_stats()

    def record_cycle(self, cycle_data: Dict[str, Any]):
        """记录单次循环数据"""
        try:
            # 构建记录数据
            record = {
                "timestamp": datetime.now().isoformat(),
                "version": self.version,
                "cycle_id": cycle_data.get("cycle_id"),
                "chat_id": self.chat_id,
                "action_type": cycle_data.get("action_type", "unknown"),
                "total_time": cycle_data.get("total_time", 0),
                "step_times": cycle_data.get("step_times", {}),
                "reasoning": cycle_data.get("reasoning", ""),
                "success": cycle_data.get("success", False),
            }

            # 添加到当前会话数据
            self.current_session_data.append(record)

            # 立即写入文件（防止数据丢失）
            self._write_session_data()

            logger.debug(
                f"记录HFC循环数据: cycle_id={record['cycle_id']}, action={record['action_type']}, time={record['total_time']:.2f}s"
            )

        except Exception as e:
            logger.error(f"记录HFC循环数据失败: {e}")

    def _write_session_data(self):
        """写入当前会话数据到文件"""
        try:
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(self.current_session_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入会话数据失败: {e}")

    def _update_historical_stats(self):
        """更新历史统计数据"""
        try:
            # 读取所有历史会话文件
            all_records = []

            # 读取当前chat_id的所有历史文件（包括不同版本）
            for file_path in self.log_dir.glob(f"{self.chat_id}_*.json"):
                if file_path == self.session_file:
                    continue  # 跳过当前会话文件

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        records = json.load(f)
                        if isinstance(records, list):
                            all_records.extend(records)
                except Exception as e:
                    logger.warning(f"读取历史文件 {file_path} 失败: {e}")

            if not all_records:
                logger.info(f"没有找到 chat_id={self.chat_id} 的历史数据")
                return

            # 计算统计数据
            stats = self._calculate_stats(all_records)

            # 更新统计文件
            self._update_stats_file(stats)

            logger.info(f"更新了 chat_id={self.chat_id} 的历史统计数据，共 {len(all_records)} 条记录")

        except Exception as e:
            logger.error(f"更新历史统计数据失败: {e}")

    def _calculate_stats(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算统计数据"""
        if not records:
            return {}

        # 按动作类型分组
        action_groups = {}
        total_times = []
        step_time_totals = {}

        for record in records:
            action_type = record.get("action_type", "unknown")
            total_time = record.get("total_time", 0)
            step_times = record.get("step_times", {})

            if action_type not in action_groups:
                action_groups[action_type] = {"count": 0, "total_times": [], "step_times": {}}

            action_groups[action_type]["count"] += 1
            action_groups[action_type]["total_times"].append(total_time)
            total_times.append(total_time)

            # 记录步骤时间
            for step_name, step_time in step_times.items():
                if step_name not in action_groups[action_type]["step_times"]:
                    action_groups[action_type]["step_times"][step_name] = []
                action_groups[action_type]["step_times"][step_name].append(step_time)

                if step_name not in step_time_totals:
                    step_time_totals[step_name] = []
                step_time_totals[step_name].append(step_time)

        # 计算各种平均值和比例
        total_records = len(records)

        # 整体统计
        overall_stats = {
            "total_records": total_records,
            "avg_total_time": sum(total_times) / len(total_times) if total_times else 0,
            "avg_step_times": {},
        }

        # 各步骤平均时间
        for step_name, times in step_time_totals.items():
            overall_stats["avg_step_times"][step_name] = sum(times) / len(times) if times else 0

        # 按动作类型统计
        action_stats = {}
        for action_type, data in action_groups.items():
            action_stats[action_type] = {
                "count": data["count"],
                "percentage": (data["count"] / total_records) * 100,
                "avg_total_time": sum(data["total_times"]) / len(data["total_times"]) if data["total_times"] else 0,
                "avg_step_times": {},
            }

            # 该动作各步骤平均时间
            for step_name, times in data["step_times"].items():
                action_stats[action_type]["avg_step_times"][step_name] = sum(times) / len(times) if times else 0

        return {
            "chat_id": self.chat_id,
            "version": self.version,
            "last_updated": datetime.now().isoformat(),
            "overall": overall_stats,
            "by_action": action_stats,
        }

    def _update_stats_file(self, new_stats: Dict[str, Any]):
        """更新统计文件"""
        try:
            # 读取现有统计数据
            existing_stats = {}
            if self.stats_file.exists():
                with open(self.stats_file, "r", encoding="utf-8") as f:
                    existing_stats = json.load(f)

            # 更新当前chat_id和版本的统计数据
            stats_key = f"{self.chat_id}_{self.version}"
            existing_stats[stats_key] = new_stats

            # 写回文件
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(existing_stats, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"更新统计文件失败: {e}")

    def get_current_session_stats(self) -> Dict[str, Any]:
        """获取当前会话的统计数据"""
        if not self.current_session_data:
            return {}

        return self._calculate_stats(self.current_session_data)

    def finalize_session(self):
        """结束会话，进行最终统计"""
        try:
            if self.current_session_data:
                # 计算当前会话统计数据
                self._calculate_stats(self.current_session_data)

                # 合并历史数据重新计算总体统计
                all_records = self.current_session_data[:]

                # 读取历史数据
                for file_path in self.log_dir.glob(f"{self.chat_id}_*.json"):
                    if file_path == self.session_file:
                        continue

                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            records = json.load(f)
                            if isinstance(records, list):
                                all_records.extend(records)
                    except Exception as e:
                        logger.warning(f"读取历史文件 {file_path} 失败: {e}")

                # 重新计算总体统计
                total_stats = self._calculate_stats(all_records)
                self._update_stats_file(total_stats)

                logger.info(
                    f"完成会话统计，当前会话 {len(self.current_session_data)} 条记录，总共 {len(all_records)} 条记录"
                )

        except Exception as e:
            logger.error(f"结束会话统计失败: {e}")
