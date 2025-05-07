from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Tuple, List

from src.common.logger import get_module_logger
from src.manager.async_task_manager import AsyncTask

from ...common.database import db
from src.manager.local_store_manager import local_storage

logger = get_module_logger("maibot_statistic")

# 统计数据的键
TOTAL_REQ_CNT = "total_requests"
TOTAL_COST = "total_cost"
REQ_CNT_BY_TYPE = "requests_by_type"
REQ_CNT_BY_USER = "requests_by_user"
REQ_CNT_BY_MODEL = "requests_by_model"
IN_TOK_BY_TYPE = "in_tokens_by_type"
IN_TOK_BY_USER = "in_tokens_by_user"
IN_TOK_BY_MODEL = "in_tokens_by_model"
OUT_TOK_BY_TYPE = "out_tokens_by_type"
OUT_TOK_BY_USER = "out_tokens_by_user"
OUT_TOK_BY_MODEL = "out_tokens_by_model"
TOTAL_TOK_BY_TYPE = "tokens_by_type"
TOTAL_TOK_BY_USER = "tokens_by_user"
TOTAL_TOK_BY_MODEL = "tokens_by_model"
COST_BY_TYPE = "costs_by_type"
COST_BY_USER = "costs_by_user"
COST_BY_MODEL = "costs_by_model"
ONLINE_TIME = "online_time"
TOTAL_MSG_CNT = "total_messages"
MSG_CNT_BY_CHAT = "messages_by_chat"


class OnlineTimeRecordTask(AsyncTask):
    """在线时间记录任务"""

    def __init__(self):
        super().__init__(task_name="Online Time Record Task", run_interval=60)

        self.record_id: str | None = None
        """记录ID"""

        self._init_database()  # 初始化数据库

    @staticmethod
    def _init_database():
        """初始化数据库"""
        if "online_time" not in db.list_collection_names():
            # 初始化数据库（在线时长）
            db.create_collection("online_time")
            # 创建索引
            if ("end_timestamp", 1) not in db.online_time.list_indexes():
                db.online_time.create_index([("end_timestamp", 1)])

    async def run(self):
        try:
            if self.record_id:
                # 如果有记录，则更新结束时间
                db.online_time.update_one(
                    {"_id": self.record_id},
                    {
                        "$set": {
                            "end_timestamp": datetime.now() + timedelta(minutes=1),
                        }
                    },
                )
            else:
                # 如果没有记录，检查一分钟以内是否已有记录
                current_time = datetime.now()
                recent_record = db.online_time.find_one(
                    {"end_timestamp": {"$gte": current_time - timedelta(minutes=1)}}
                )

                if not recent_record:
                    # 若没有记录，则插入新的在线时间记录
                    self.record_id = db.online_time.insert_one(
                        {
                            "start_timestamp": current_time,
                            "end_timestamp": current_time + timedelta(minutes=1),
                        }
                    ).inserted_id
                else:
                    # 如果有记录，则更新结束时间
                    self.record_id = recent_record["_id"]
                    db.online_time.update_one(
                        {"_id": self.record_id},
                        {
                            "$set": {
                                "end_timestamp": current_time + timedelta(minutes=1),
                            }
                        },
                    )
        except Exception:
            logger.exception("在线时间记录失败")


class StatisticOutputTask(AsyncTask):
    """统计输出任务"""

    SEP_LINE = "-" * 84

    def __init__(self, record_file_path: str = "llm_statistics.txt"):
        # 延迟300秒启动，运行间隔300秒
        super().__init__(task_name="Statistics Data Output Task", wait_before_start=300, run_interval=300)

        self.name_mapping: Dict[str, Tuple[str, float]] = {}
        """
            联系人/群聊名称映射 {聊天ID: (联系人/群聊名称, 记录时间（timestamp）)}
            注：设计记录时间的目的是方便更新名称，使联系人/群聊名称保持最新
        """

        self.record_file_path: str = record_file_path
        """
        记录文件路径
        """

        now = datetime.now()
        self.stat_period: List[Tuple[str, datetime, str]] = [
            ("all_time", datetime(2000, 1, 1), "自部署以来的"),
            ("last_7_days", now - timedelta(days=7), "最近7天的"),
            ("last_24_hours", now - timedelta(days=1), "最近24小时的"),
            ("last_hour", now - timedelta(hours=1), "最近1小时的"),
        ]
        """
        统计时间段
        """

    def _statistic_console_output(self, stats: Dict[str, Any]):
        """
        输出统计数据到控制台
        """
        # 输出最近一小时的统计数据

        output = [
            self.SEP_LINE,
            f"  最近1小时的统计数据  (详细信息见文件：{self.record_file_path})",
            self.SEP_LINE,
            self._format_total_stat(stats["last_hour"]),
            "",
            self._format_model_classified_stat(stats["last_hour"]),
            "",
            self._format_chat_stat(stats["last_hour"]),
            self.SEP_LINE,
            "",
        ]

        logger.info("\n" + "\n".join(output))

    def _statistic_file_output(self, stats: Dict[str, Any]):
        """
        输出统计数据到文件
        """
        output = [f"MaiBot运行统计报告  (生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')})", ""]

        def _format_stat_data(title: str, stats_: Dict[str, Any]) -> str:
            """
            格式化统计数据
            """
            return "\n".join(
                [
                    self.SEP_LINE,
                    f"  {title}",
                    self.SEP_LINE,
                    self._format_total_stat(stats_),
                    "",
                    self._format_model_classified_stat(stats_),
                    "",
                    self._format_req_type_classified_stat(stats_),
                    "",
                    self._format_user_classified_stat(stats_),
                    "",
                    self._format_chat_stat(stats_),
                    "",
                ]
            )

        for period_key, period_start_time, period_desc in self.stat_period:
            if period_key in stats:
                # 统计数据存在
                output.append(
                    _format_stat_data(
                        f"{period_desc}统计数据  (自{period_start_time.strftime('%Y-%m-%d %H:%M:%S')}开始)",
                        stats[period_key],
                    )
                )

        with open(self.record_file_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(output))

    async def run(self):
        try:
            # 收集统计数据
            stats = self._collect_all_statistics()

            # 输出统计数据到控制台
            self._statistic_console_output(stats)
            # 输出统计数据到文件
            self._statistic_file_output(stats)
        except Exception as e:
            logger.exception(f"输出统计数据过程中发生异常，错误信息：{e}")

    # -- 以下为统计数据收集方法 --

    @staticmethod
    def _collect_model_request_for_period(collect_period: List[Tuple[str, datetime, str]]) -> Dict[str, Any]:
        """
        收集指定时间段的LLM请求统计数据

        :param collect_period: 统计时间段
        """
        if len(collect_period) <= 0:
            return {}
        else:
            # 排序-按照时间段开始时间降序排列（最晚的时间段在前）
            collect_period.sort(key=lambda x: x[1], reverse=True)

        stats = {
            period_key: {
                # 总LLM请求数
                TOTAL_REQ_CNT: 0,
                # 请求次数统计
                REQ_CNT_BY_TYPE: defaultdict(int),
                REQ_CNT_BY_USER: defaultdict(int),
                REQ_CNT_BY_MODEL: defaultdict(int),
                # 输入Token数
                IN_TOK_BY_TYPE: defaultdict(int),
                IN_TOK_BY_USER: defaultdict(int),
                IN_TOK_BY_MODEL: defaultdict(int),
                # 输出Token数
                OUT_TOK_BY_TYPE: defaultdict(int),
                OUT_TOK_BY_USER: defaultdict(int),
                OUT_TOK_BY_MODEL: defaultdict(int),
                # 总Token数
                TOTAL_TOK_BY_TYPE: defaultdict(int),
                TOTAL_TOK_BY_USER: defaultdict(int),
                TOTAL_TOK_BY_MODEL: defaultdict(int),
                # 总开销
                TOTAL_COST: 0.0,
                # 请求开销统计
                COST_BY_TYPE: defaultdict(float),
                COST_BY_USER: defaultdict(float),
                COST_BY_MODEL: defaultdict(float),
            }
            for period_key, _, _ in collect_period
        }

        # 以最早的时间戳为起始时间获取记录
        for record in db.llm_usage.find({"timestamp": {"$gte": collect_period[-1][1]}}):
            record_timestamp = record.get("timestamp")
            for idx, (_, period_start, _) in enumerate(collect_period):
                if record_timestamp >= period_start:
                    # 如果记录时间在当前时间段内，则它一定在更早的时间段内
                    # 因此，我们可以直接跳过更早的时间段的判断，直接更新当前以及更早时间段的统计数据
                    for period_key, _, _ in collect_period[idx:]:
                        stats[period_key][TOTAL_REQ_CNT] += 1

                        request_type = record.get("request_type", "unknown")  # 请求类型
                        user_id = str(record.get("user_id", "unknown"))  # 用户ID
                        model_name = record.get("model_name", "unknown")  # 模型名称

                        stats[period_key][REQ_CNT_BY_TYPE][request_type] += 1
                        stats[period_key][REQ_CNT_BY_USER][user_id] += 1
                        stats[period_key][REQ_CNT_BY_MODEL][model_name] += 1

                        prompt_tokens = record.get("prompt_tokens", 0)  # 输入Token数
                        completion_tokens = record.get("completion_tokens", 0)  # 输出Token数
                        total_tokens = prompt_tokens + completion_tokens  # Token总数 = 输入Token数 + 输出Token数

                        stats[period_key][IN_TOK_BY_TYPE][request_type] += prompt_tokens
                        stats[period_key][IN_TOK_BY_USER][user_id] += prompt_tokens
                        stats[period_key][IN_TOK_BY_MODEL][model_name] += prompt_tokens

                        stats[period_key][OUT_TOK_BY_TYPE][request_type] += completion_tokens
                        stats[period_key][OUT_TOK_BY_USER][user_id] += completion_tokens
                        stats[period_key][OUT_TOK_BY_MODEL][model_name] += completion_tokens

                        stats[period_key][TOTAL_TOK_BY_TYPE][request_type] += total_tokens
                        stats[period_key][TOTAL_TOK_BY_USER][user_id] += total_tokens
                        stats[period_key][TOTAL_TOK_BY_MODEL][model_name] += total_tokens

                        cost = record.get("cost", 0.0)
                        stats[period_key][TOTAL_COST] += cost
                        stats[period_key][COST_BY_TYPE][request_type] += cost
                        stats[period_key][COST_BY_USER][user_id] += cost
                        stats[period_key][COST_BY_MODEL][model_name] += cost
                    break  # 取消更早时间段的判断

        return stats

    @staticmethod
    def _collect_online_time_for_period(collect_period: List[Tuple[str, datetime, str]]) -> Dict[str, Any]:
        """
        收集指定时间段的在线时间统计数据

        :param collect_period: 统计时间段
        """
        if len(collect_period) <= 0:
            return {}
        else:
            # 排序-按照时间段开始时间降序排列（最晚的时间段在前）
            collect_period.sort(key=lambda x: x[1], reverse=True)

        stats = {
            period_key: {
                # 在线时间统计
                ONLINE_TIME: 0.0,
            }
            for period_key, _, _ in collect_period
        }

        # 统计在线时间
        for record in db.online_time.find({"end_timestamp": {"$gte": collect_period[-1][1]}}):
            end_timestamp: datetime = record.get("end_timestamp")
            for idx, (_, period_start, _) in enumerate(collect_period):
                if end_timestamp >= period_start:
                    # 如果记录时间在当前时间段内，则它一定在更早的时间段内
                    # 因此，我们可以直接跳过更早的时间段的判断，直接更新当前以及更早时间段的统计数据
                    for period_key, _period_start, _ in collect_period[idx:]:
                        start_timestamp: datetime = record.get("start_timestamp")
                        if start_timestamp < _period_start:
                            # 如果开始时间在查询边界之前，则使用开始时间
                            stats[period_key][ONLINE_TIME] += (end_timestamp - _period_start).total_seconds() / 60
                        else:
                            # 否则，使用开始时间
                            stats[period_key][ONLINE_TIME] += (end_timestamp - start_timestamp).total_seconds() / 60
                    break  # 取消更早时间段的判断

        return stats

    def _collect_message_count_for_period(self, collect_period: List[Tuple[str, datetime, str]]) -> Dict[str, Any]:
        """
        收集指定时间段的消息统计数据

        :param collect_period: 统计时间段
        """
        if len(collect_period) <= 0:
            return {}
        else:
            # 排序-按照时间段开始时间降序排列（最晚的时间段在前）
            collect_period.sort(key=lambda x: x[1], reverse=True)

        stats = {
            period_key: {
                # 消息统计
                TOTAL_MSG_CNT: 0,
                MSG_CNT_BY_CHAT: defaultdict(int),
            }
            for period_key, _, _ in collect_period
        }

        # 统计消息量
        for message in db.messages.find({"time": {"$gte": collect_period[-1][1].timestamp()}}):
            chat_info = message.get("chat_info", None)  # 聊天信息
            user_info = message.get("user_info", None)  # 用户信息（消息发送人）
            message_time = message.get("time", 0)  # 消息时间

            group_info = chat_info.get("group_info") if chat_info else None  # 尝试获取群聊信息
            if group_info is not None:
                # 若有群聊信息
                chat_id = f"g{group_info.get('group_id')}"
                chat_name = group_info.get("group_name", f"群{group_info.get('group_id')}")
            elif user_info:
                # 若没有群聊信息，则尝试获取用户信息
                chat_id = f"u{user_info['user_id']}"
                chat_name = user_info["user_nickname"]
            else:
                continue  # 如果没有群组信息也没有用户信息，则跳过

            if chat_id in self.name_mapping:
                if chat_name != self.name_mapping[chat_id][0] and message_time > self.name_mapping[chat_id][1]:
                    # 如果用户名称不同，且新消息时间晚于之前记录的时间，则更新用户名称
                    self.name_mapping[chat_id] = (chat_name, message_time)
            else:
                self.name_mapping[chat_id] = (chat_name, message_time)

            for idx, (_, period_start, _) in enumerate(collect_period):
                if message_time >= period_start.timestamp():
                    # 如果记录时间在当前时间段内，则它一定在更早的时间段内
                    # 因此，我们可以直接跳过更早的时间段的判断，直接更新当前以及更早时间段的统计数据
                    for period_key, _, _ in collect_period[idx:]:
                        stats[period_key][TOTAL_MSG_CNT] += 1
                        stats[period_key][MSG_CNT_BY_CHAT][chat_id] += 1
                    break

        return stats

    def _collect_all_statistics(self) -> Dict[str, Dict[str, Any]]:
        """
        收集各时间段的统计数据
        """

        now = datetime.now()

        last_all_time_stat = None

        stat = {period[0]: {} for period in self.stat_period}

        if "last_full_statistics_timestamp" in local_storage and "last_full_statistics" in local_storage:
            # 若存有上次完整统计的时间戳，则使用该时间戳作为"所有时间"的起始时间，进行增量统计
            last_full_stat_ts: float = local_storage["last_full_statistics_timestamp"]
            last_all_time_stat = local_storage["last_full_statistics"]
            self.stat_period = [item for item in self.stat_period if item[0] != "all_time"]  # 删除"所有时间"的统计时段
            self.stat_period.append(("all_time", datetime.fromtimestamp(last_full_stat_ts), "自部署以来的"))

        model_req_stat = self._collect_model_request_for_period(self.stat_period)
        online_time_stat = self._collect_online_time_for_period(self.stat_period)
        message_count_stat = self._collect_message_count_for_period(self.stat_period)

        # 统计数据合并
        # 合并三类统计数据
        for period_key, _, _ in self.stat_period:
            stat[period_key].update(model_req_stat[period_key])
            stat[period_key].update(online_time_stat[period_key])
            stat[period_key].update(message_count_stat[period_key])

        if last_all_time_stat:
            # 若存在上次完整统计数据，则将其与当前统计数据合并
            for key, val in last_all_time_stat.items():
                if isinstance(val, dict):
                    # 是字典类型，则进行合并
                    for sub_key, sub_val in val.items():
                        stat["all_time"][key][sub_key] += sub_val
                else:
                    # 直接合并
                    stat["all_time"][key] += val

        # 更新上次完整统计数据的时间戳
        local_storage["last_full_statistics_timestamp"] = now.timestamp()
        # 更新上次完整统计数据
        local_storage["last_full_statistics"] = stat["all_time"]

        return stat

    # -- 以下为统计数据格式化方法 --

    @staticmethod
    def _format_total_stat(stats: Dict[str, Any]) -> str:
        """
        格式化总统计数据
        """
        output = [
            f"总在线时间: {stats[ONLINE_TIME]:.1f}分钟",
            f"总消息数: {stats[TOTAL_MSG_CNT]}",
            f"总请求数: {stats[TOTAL_REQ_CNT]}",
            f"总花费: {stats[TOTAL_COST]:.4f}¥",
            "",
        ]

        return "\n".join(output)

    @staticmethod
    def _format_model_classified_stat(stats: Dict[str, Any]) -> str:
        """
        格式化按模型分类的统计数据
        """
        if stats[TOTAL_REQ_CNT] > 0:
            data_fmt = "{:<32}  {:>10}  {:>12}  {:>12}  {:>12}  {:>9.4f}¥"

            output = [
                "按模型分类统计:",
                " 模型名称                          调用次数    输入Token     输出Token     Token总量     累计花费",
            ]
            for model_name, count in sorted(stats[REQ_CNT_BY_MODEL].items()):
                name = model_name[:29] + "..." if len(model_name) > 32 else model_name
                in_tokens = stats[IN_TOK_BY_MODEL][model_name]
                out_tokens = stats[OUT_TOK_BY_MODEL][model_name]
                tokens = stats[TOTAL_TOK_BY_MODEL][model_name]
                cost = stats[COST_BY_MODEL][model_name]
                output.append(data_fmt.format(name, count, in_tokens, out_tokens, tokens, cost))

            output.append("")
            return "\n".join(output)
        else:
            return ""

    @staticmethod
    def _format_req_type_classified_stat(stats: Dict[str, Any]) -> str:
        """
        格式化按请求类型分类的统计数据
        """
        if stats[TOTAL_REQ_CNT] > 0:
            # 按请求类型统计
            data_fmt = "{:<32}  {:>10}  {:>12}  {:>12}  {:>12}  {:>9.4f}¥"

            output = [
                "按请求类型分类统计:",
                " 请求类型                          调用次数    输入Token     输出Token     Token总量     累计花费",
            ]
            for req_type, count in sorted(stats[REQ_CNT_BY_TYPE].items()):
                name = req_type[:29] + "..." if len(req_type) > 32 else req_type
                in_tokens = stats[IN_TOK_BY_TYPE][req_type]
                out_tokens = stats[OUT_TOK_BY_TYPE][req_type]
                tokens = stats[TOTAL_TOK_BY_TYPE][req_type]
                cost = stats[COST_BY_TYPE][req_type]
                output.append(data_fmt.format(name, count, in_tokens, out_tokens, tokens, cost))

            output.append("")
            return "\n".join(output)
        else:
            return ""

    @staticmethod
    def _format_user_classified_stat(stats: Dict[str, Any]) -> str:
        """
        格式化按用户分类的统计数据
        """
        if stats[TOTAL_REQ_CNT] > 0:
            # 修正用户统计列宽
            data_fmt = "{:<32}  {:>10}  {:>12}  {:>12}  {:>12}  {:>9.4f}¥"

            output = [
                "按用户分类统计:",
                " 用户名称                          调用次数    输入Token     输出Token     Token总量     累计花费",
            ]
            for user_id, count in sorted(stats[REQ_CNT_BY_USER].items()):
                in_tokens = stats[IN_TOK_BY_USER][user_id]
                out_tokens = stats[OUT_TOK_BY_USER][user_id]
                tokens = stats[TOTAL_TOK_BY_USER][user_id]
                cost = stats[COST_BY_USER][user_id]
                output.append(
                    data_fmt.format(
                        user_id[:22],  # 不再添加省略号，保持原始ID
                        count,
                        in_tokens,
                        out_tokens,
                        tokens,
                        cost,
                    )
                )

            output.append("")
            return "\n".join(output)
        else:
            return ""

    def _format_chat_stat(self, stats: Dict[str, Any]) -> str:
        """
        格式化聊天统计数据
        """
        if stats[TOTAL_MSG_CNT] > 0:
            output = ["聊天消息统计:", " 联系人/群组名称                  消息数量"]
            for chat_id, count in sorted(stats[MSG_CNT_BY_CHAT].items()):
                output.append(f"{self.name_mapping[chat_id][0][:32]:<32}  {count:>10}")

            output.append("")
            return "\n".join(output)
        else:
            return ""
