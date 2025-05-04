import flet as ft
import asyncio
import os
import json
import time
import traceback
import random
from datetime import datetime
from collections import deque

# --- 配置 (可以从 launcher.py 传入或在此处定义) ---
LOG_FILE_PATH = os.path.join("logs", "interest", "interest_history.log")
REFRESH_INTERVAL_SECONDS = 1  # 刷新间隔（秒）
MAX_HISTORY_POINTS = 1000  # 图表数据点 (Tkinter version uses 1000)
MAX_STREAMS_TO_DISPLAY = 15  # 最多显示的流数量 (Tkinter version uses 15)
MAX_QUEUE_SIZE = 30  # 历史想法队列最大长度 (Tkinter version uses 30)
CHART_HEIGHT = 250  # 图表区域高度


# --- 辅助函数 ---
def format_timestamp(ts):
    """辅助函数：格式化时间戳，处理 None 或无效值"""
    if ts is None:
        return "N/A"
    try:
        # 假设 ts 是 float 类型的时间戳
        dt_object = datetime.fromtimestamp(float(ts))
        return dt_object.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return "Invalid Time"


def get_random_flet_color():
    """生成一个随机的 Flet 颜色字符串。"""
    r = random.randint(50, 200)
    g = random.randint(50, 200)
    b = random.randint(50, 200)
    return f"#{r:02x}{g:02x}{b:02x}"


class InterestMonitorDisplay(ft.Column):
    """一个 Flet 控件，用于显示兴趣监控图表和信息。"""

    def __init__(self):
        super().__init__(
            expand=True,
        )
        # --- 状态变量 ---
        self.log_reader_task = None
        self.stream_history = {}  # {stream_id: deque([(ts, interest), ...])}
        self.probability_history = {}  # {stream_id: deque([(ts, probability), ...])}
        self.stream_display_names = {}  # {stream_id: display_name}
        self.stream_colors = {}  # {stream_id: color_string}
        self.selected_stream_id_for_details = None
        self.last_log_read_time = 0  # 上次读取日志的时间戳

        # --- 新增：存储其他参数 ---
        # 顶层信息 (直接使用 Text 控件引用)
        self.global_mai_state_text = ft.Text("状态: N/A", size=11)
        self.global_main_mind_text = ft.Text(
            "想法: N/A", size=11, overflow=ft.TextOverflow.ELLIPSIS, tooltip="完整想法请查看历史记录"
        )
        self.global_subflow_count_text = ft.Text("子流数: 0", size=11)
        # 子流最新状态 (key: stream_id)
        self.stream_sub_minds = {}
        self.stream_chat_states = {}
        self.stream_threshold_status = {}
        self.stream_last_active = {}
        # self.stream_last_interaction = {} # Tkinter 有但日志似乎没有?

        # 新增：历史想法队列
        self.main_mind_history = deque(maxlen=MAX_QUEUE_SIZE)
        self.last_main_mind_timestamp = 0

        # --- UI 控件引用 ---
        self.status_text = ft.Text("正在初始化监控器...", size=10, color=ft.colors.SECONDARY)

        # --- 全局信息 Row ---
        self.global_info_row = ft.Row(
            controls=[
                self.global_mai_state_text,
                self.global_main_mind_text,
                self.global_subflow_count_text,
            ],
            spacing=15,
            wrap=False,  # 防止换行
        )

        # --- 图表控件 ---
        self.main_chart = ft.LineChart(height=CHART_HEIGHT, expand=True)
        # --- 新增：图例 Column ---
        self.legend_column = ft.Column(
            controls=[],
            width=150,  # 给图例固定宽度
            scroll=ft.ScrollMode.ADAPTIVE,  # 如果图例过多则滚动
            spacing=2,
        )

        self.stream_dropdown = ft.Dropdown(
            label="选择流查看详情", options=[], width=300, on_change=self.on_stream_selected
        )
        self.detail_chart_interest = ft.LineChart(height=CHART_HEIGHT)
        self.detail_chart_probability = ft.LineChart(height=CHART_HEIGHT)

        # --- 单个流详情文本控件 (Column) ---
        self.detail_texts = ft.Column(
            [
                # --- 添加新的 Text 控件来显示详情 ---
                ft.Text("想法: N/A", size=11, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),  # index 0: sub_mind
                ft.Text("状态: N/A", size=11),  # index 1: chat_state
                ft.Text("阈值以上: N/A", size=11),  # index 2: threshold
                ft.Text("最后活跃: N/A", size=11),  # index 3: last_active
                # ft.Text("最后交互: N/A", size=11), # 如果需要的话
            ],
            spacing=2,
        )

        # --- 历史想法 ListView ---
        self.mind_history_listview = ft.ListView(expand=True, spacing=5, padding=5)

        # --- 构建整体布局 ---
        # 创建 Tabs 控件 (现在是 Column 的直接子控件)
        self.tabs_control = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="所有流兴趣度",
                    content=ft.Row(
                        controls=[
                            self.main_chart,  # 图表在左侧
                            self.legend_column,  # 图例在右侧
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        expand=True,  # 让 Row 扩展
                    ),
                ),
                ft.Tab(
                    text="单个流详情",
                    content=ft.Column(
                        [
                            self.stream_dropdown,
                            ft.Divider(height=5, color=ft.colors.TRANSPARENT),
                            self.detail_texts,  # 显示文本信息的 Column
                            ft.Divider(height=10, color=ft.colors.TRANSPARENT),
                            ft.Row(
                                [
                                    ft.Column(
                                        [ft.Text("兴趣度", weight=ft.FontWeight.BOLD), self.detail_chart_interest],
                                        expand=1,
                                    ),
                                    ft.Column(
                                        [ft.Text("HFC概率", weight=ft.FontWeight.BOLD), self.detail_chart_probability],
                                        expand=1,
                                    ),
                                ],
                            ),
                        ],
                        scroll=ft.ScrollMode.ADAPTIVE,  # 自适应滚动
                    ),
                ),
                # --- 添加历史想法 Tab ---
                ft.Tab(
                    text="麦麦历史想法",
                    content=self.mind_history_listview,  # 直接使用 ListView
                ),
            ],
            expand=True,  # 让 Tabs 在父 Column 中扩展
        )

        self.controls = [
            self.status_text,
            self.global_info_row,  # 添加全局信息行
            # --- Tabs 直接放在 Column 里 --- #
            self.tabs_control,
        ]

        print("[InterestMonitor] 初始化完成")

    def did_mount(self):
        print("[InterestMonitor] 控件已挂载，启动日志读取任务")
        if self.page:
            # --- 首次加载历史想法 (可以在这里或 log_reader_loop 首次运行时加载) ---
            # self.page.run_task(self.load_and_process_log, initial_load=True) # 传递标志?
            self.log_reader_task = self.page.run_task(self.log_reader_loop)
            # self.page.run_task(self.update_charts) # update_charts 会在 loop 中调用
        else:
            print("[InterestMonitor] 错误: 无法访问 self.page 来启动后台任务")

    def will_unmount(self):
        print("[InterestMonitor] 控件将卸载，取消日志读取任务")
        if self.log_reader_task:
            self.log_reader_task.cancel()
            print("[InterestMonitor] 日志读取任务已取消 (will_unmount)")

    async def log_reader_loop(self):
        while True:
            try:
                mind_history_updated = await self.load_and_process_log()
                await self.update_charts()
                if mind_history_updated:
                    await self.refresh_mind_listview()
            except asyncio.CancelledError:
                print("[InterestMonitor] 日志读取循环被取消")
                break
            except Exception as e:
                print(f"[InterestMonitor] 日志读取循环出错: {e}")
                traceback.print_exc()
                self.update_status(f"日志读取错误: {e}", ft.colors.ERROR)

            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

    async def load_and_process_log(self):
        """读取并处理日志文件的新增内容。返回是否有新的 Main Mind 记录。"""
        mind_history_updated = False  # 跟踪是否有新的 Main Mind
        if not os.path.exists(LOG_FILE_PATH):
            self.update_status("日志文件未找到", ft.colors.WARNING)
            return mind_history_updated

        try:
            file_mod_time = os.path.getmtime(LOG_FILE_PATH)
            if file_mod_time <= self.last_log_read_time:
                return mind_history_updated

            print(f"[InterestMonitor] 检测到日志文件更新 (修改时间: {file_mod_time}), 正在读取...", flush=True)

            new_stream_history = {}
            new_probability_history = {}
            new_stream_display_names = {}
            # 清理旧的子流状态，因为每次都重新读取文件
            self.stream_sub_minds.clear()
            self.stream_chat_states.clear()
            self.stream_threshold_status.clear()
            self.stream_last_active.clear()
            # self.stream_last_interaction.clear()

            read_count = 0
            error_count = 0
            # 注意：Flet 版本目前没有实现时间过滤，会读取整个文件

            with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    read_count += 1
                    try:
                        log_entry = json.loads(line.strip())
                        if not isinstance(log_entry, dict):
                            continue

                        entry_timestamp = log_entry.get("timestamp")
                        if entry_timestamp is None:
                            continue

                        # --- 处理主兴趣流 --- #
                        stream_id = log_entry.get("stream_id")
                        interest = log_entry.get("interest")
                        probability = log_entry.get("probability")  # 新增：获取概率

                        if stream_id is not None and interest is not None:
                            try:
                                interest_float = float(interest)
                                if stream_id not in new_stream_history:
                                    new_stream_history[stream_id] = []
                                # 避免重复添加相同时间戳的数据点
                                if (
                                    not new_stream_history[stream_id]
                                    or new_stream_history[stream_id][-1][0] < entry_timestamp
                                ):
                                    new_stream_history[stream_id].append((entry_timestamp, interest_float))
                            except (ValueError, TypeError):
                                pass  # 忽略无法转换的值

                        # --- 处理概率 --- #
                        if stream_id is not None and probability is not None:
                            try:
                                prob_float = float(probability)
                                if stream_id not in new_probability_history:
                                    new_probability_history[stream_id] = []
                                if (
                                    not new_probability_history[stream_id]
                                    or new_probability_history[stream_id][-1][0] < entry_timestamp
                                ):
                                    new_probability_history[stream_id].append((entry_timestamp, prob_float))
                            except (ValueError, TypeError):
                                pass  # 忽略无法转换的值

                        # --- 处理子流 (subflows) --- #
                        subflows = log_entry.get("subflows")
                        if not isinstance(subflows, list):
                            continue

                        for subflow_entry in subflows:
                            stream_id = subflow_entry.get("stream_id")
                            interest = subflow_entry.get("interest")
                            group_name = subflow_entry.get("group_name", stream_id)
                            # 新增: 获取子流概率
                            probability = subflow_entry.get("probability")

                            if stream_id is None or interest is None:
                                continue
                            try:
                                interest_float = float(interest)
                            except (ValueError, TypeError):
                                continue

                            if stream_id not in new_stream_history:
                                new_stream_history[stream_id] = []
                                self.stream_details[stream_id] = {"group_name": group_name}  # 存储详情
                            # 避免重复添加相同时间戳的数据点
                            if (
                                not new_stream_history[stream_id]
                                or new_stream_history[stream_id][-1][0] < entry_timestamp
                            ):
                                new_stream_history[stream_id].append((entry_timestamp, interest_float))

                            # --- 处理子流概率 --- #
                            if probability is not None:
                                try:
                                    prob_float = float(probability)
                                    if stream_id not in new_probability_history:
                                        new_probability_history[stream_id] = []
                                    if (
                                        not new_probability_history[stream_id]
                                        or new_probability_history[stream_id][-1][0] < entry_timestamp
                                    ):
                                        new_probability_history[stream_id].append((entry_timestamp, prob_float))
                                except (ValueError, TypeError):
                                    pass  # 忽略无法转换的值

                            # --- 存储其他子流详情 (最新的会覆盖旧的) ---
                            self.stream_sub_minds[stream_id] = subflow_entry.get("sub_mind", "N/A")
                            self.stream_chat_states[stream_id] = subflow_entry.get("sub_chat_state", "N/A")
                            self.stream_threshold_status[stream_id] = subflow_entry.get("is_above_threshold", False)
                            self.stream_last_active[stream_id] = subflow_entry.get("chat_state_changed_time")
                            # self.stream_last_interaction[stream_id] = ... # 如果日志中有

                    except json.JSONDecodeError:
                        error_count += 1
                        continue
                    except Exception as line_err:
                        print(f"处理日志行时出错: {line_err}")  # 打印行级错误
                        error_count += 1
                        continue

            # 更新状态
            self.stream_history = new_stream_history
            self.probability_history = new_probability_history
            self.stream_display_names = new_stream_display_names
            self.last_log_read_time = file_mod_time

            status_msg = f"日志读取于 {datetime.now().strftime('%H:%M:%S')}. 行数: {read_count}."
            if error_count > 0:
                status_msg += f" 跳过 {error_count} 无效行."
                self.update_status(status_msg, ft.colors.ORANGE)
            else:
                self.update_status(status_msg, ft.colors.GREEN)

            # 更新全局信息控件 (如果 page 存在)
            if self.page:
                # TODO: Update global info based on latest log entry? Or aggregate?
                # For now, let's update with the last processed entry's data if available
                if log_entry:  # Check if log_entry was populated
                    self.global_mai_state_text.value = f"状态: {log_entry.get('mai_state', 'N/A')}"
                    self.global_main_mind_text.value = f"想法: {log_entry.get('main_mind', 'N/A')}"
                    self.global_main_mind_text.tooltip = log_entry.get("main_mind", "N/A")
                    self.global_subflow_count_text.value = f"子流数: {log_entry.get('subflow_count', '0')}"
                    self.global_info_row.update()  # Update the row

                # --- 处理 Main Mind 历史 ---
                if "main_mind" in log_entry and entry_timestamp > self.last_main_mind_timestamp:
                    self.main_mind_history.append(log_entry)
                    self.last_main_mind_timestamp = entry_timestamp
                    mind_history_updated = True

                self.global_info_row.update()  # 直接调用 update()

            # 更新下拉列表选项
            await self.update_dropdown_options()

            return mind_history_updated  # 返回是否有新 mind 记录

        except IOError as e:
            print(f"读取日志文件时发生 IO 错误: {e}")
            self.update_status(f"日志 IO 错误: {e}", ft.colors.ERROR)
        except Exception as e:
            print(f"处理日志时发生意外错误: {e}")
            traceback.print_exc()
            self.update_status(f"处理日志时出错: {e}", ft.colors.ERROR)

        return mind_history_updated

    async def refresh_mind_listview(self):
        """刷新历史想法列表视图。"""
        if not self.page:
            return  # 无法更新

        self.mind_history_listview.controls.clear()
        for entry in self.main_mind_history:
            ts = entry.get("timestamp", 0)
            dt_str = format_timestamp(ts)
            main_mind = entry.get("main_mind", "")
            mai_state = entry.get("mai_state", "")
            subflow_count = entry.get("subflow_count", "")
            # 使用 Markdown 加粗时间，简化显示
            text_content = f"**[{dt_str}]** 状态:{mai_state} 子流:{subflow_count}\n{main_mind}"
            self.mind_history_listview.controls.append(
                ft.Markdown(text_content, selectable=True, extension_set=ft.MarkdownExtensionSet.COMMON_MARK)
            )

        # print(f"[InterestMonitor] 刷新历史想法列表，共 {len(self.mind_history_listview.controls)} 条")
        self.mind_history_listview.update()  # 更新 ListView
        # 滚动到底部 (如果需要)
        # await asyncio.sleep(0.1) # 短暂延迟确保控件更新
        # self.mind_history_listview.scroll_to(offset=-1, duration=300) # 滚动到底部
        # 注意：scroll_to 可能需要在 page 上下文或特定条件下才有效

    async def update_charts(self):
        all_series = []
        legend_items = []  # 存储图例控件
        active_streams_sorted = sorted(
            self.stream_history.items(), key=lambda item: item[1][-1][1] if item[1] else -1, reverse=True
        )[:MAX_STREAMS_TO_DISPLAY]

        min_ts, max_ts = self.get_time_range(self.stream_history)

        for stream_id, history in active_streams_sorted:
            if not history:
                continue
            try:
                mpl_dates = [ts for ts, _ in history]
                interests = [interest for _, interest in history]
                if not mpl_dates:
                    continue

                data_points = [ft.LineChartDataPoint(x=ts, y=interest) for ts, interest in zip(mpl_dates, interests)]
                all_series.append(
                    ft.LineChartData(
                        data_points=data_points,
                        color=self.stream_colors.get(stream_id, ft.colors.BLACK),
                        stroke_width=2,
                    )
                )
                # --- 创建图例项 ---
                legend_color = self.stream_colors.get(stream_id, ft.colors.BLACK)
                display_name = self.stream_display_names.get(stream_id, stream_id)
                legend_items.append(
                    ft.Row(
                        controls=[
                            ft.Container(width=10, height=10, bgcolor=legend_color, border_radius=2),
                            ft.Text(display_name, size=10, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=5,
                        alignment=ft.MainAxisAlignment.START,
                    )
                )
            except Exception as plot_err:
                print(f"绘制主图表/图例时跳过 Stream {stream_id}: {plot_err}")
                continue

        # --- 更新主图表 ---
        self.main_chart.data_series = all_series
        self.main_chart.min_y = 0
        self.main_chart.max_y = 10
        self.main_chart.min_x = min_ts
        self.main_chart.max_x = max_ts

        # --- 更新图例 ---
        self.legend_column.controls = legend_items

        await self.update_detail_charts(self.selected_stream_id_for_details)

        if self.page:
            # 更新整个控件，包含图表和图例的更新
            self.update()

    async def update_detail_charts(self, stream_id):
        interest_series = []
        probability_series = []
        min_ts_detail, max_ts_detail = None, None

        # --- 兴趣度图 ---
        if stream_id and stream_id in self.stream_history and self.stream_history[stream_id]:
            min_ts_detail, max_ts_detail = self.get_time_range({stream_id: self.stream_history[stream_id]})
            try:
                mpl_dates = [ts for ts, _ in self.stream_history[stream_id]]
                interests = [interest for _, interest in self.stream_history[stream_id]]
                if mpl_dates:
                    interest_data_points = [
                        ft.LineChartDataPoint(x=ts, y=interest) for ts, interest in zip(mpl_dates, interests)
                    ]
                    interest_series.append(
                        ft.LineChartData(
                            data_points=interest_data_points,
                            color=self.stream_colors.get(stream_id, ft.colors.BLUE),
                            stroke_width=2,
                        )
                    )
            except Exception as plot_err:
                print(f"绘制详情兴趣图时出错 Stream {stream_id}: {plot_err}")

        # --- 概率图 ---
        if stream_id and stream_id in self.probability_history and self.probability_history[stream_id]:
            try:
                prob_dates = [ts for ts, _ in self.probability_history[stream_id]]
                probabilities = [prob for _, prob in self.probability_history[stream_id]]
                if prob_dates:
                    if min_ts_detail is None:  # 如果兴趣图没有数据，单独计算时间范围
                        min_ts_detail, max_ts_detail = self.get_time_range(
                            {stream_id: self.probability_history[stream_id]}, is_prob=True
                        )
                    else:  # 合并时间范围
                        min_prob_ts, max_prob_ts = self.get_time_range(
                            {stream_id: self.probability_history[stream_id]}, is_prob=True
                        )
                        if min_prob_ts is not None:
                            min_ts_detail = min(min_ts_detail, min_prob_ts)
                        if max_prob_ts is not None:
                            max_ts_detail = max(max_ts_detail, max_prob_ts)

                    probability_data_points = [
                        ft.LineChartDataPoint(x=ts, y=prob) for ts, prob in zip(prob_dates, probabilities)
                    ]
                    probability_series.append(
                        ft.LineChartData(
                            data_points=probability_data_points,
                            color=self.stream_colors.get(stream_id, ft.colors.GREEN),
                            stroke_width=2,
                        )
                    )
            except Exception as plot_err:
                print(f"绘制详情概率图时出错 Stream {stream_id}: {plot_err}")

        self.detail_chart_interest.data_series = interest_series
        self.detail_chart_interest.min_y = 0
        self.detail_chart_interest.max_y = 10
        self.detail_chart_interest.min_x = min_ts_detail
        self.detail_chart_interest.max_x = max_ts_detail

        self.detail_chart_probability.data_series = probability_series
        self.detail_chart_probability.min_y = 0
        self.detail_chart_probability.max_y = 1.05
        self.detail_chart_probability.min_x = min_ts_detail
        self.detail_chart_probability.max_x = max_ts_detail

        await self.update_detail_texts(stream_id)

    async def update_dropdown_options(self):
        current_value = self.stream_dropdown.value
        options = []
        valid_stream_ids = set()
        sorted_items = sorted(self.stream_display_names.items(), key=lambda item: item[1])
        for stream_id, display_name in sorted_items:
            if stream_id in self.stream_history and self.stream_history[stream_id]:
                # 使用 f"DisplayName (StreamID)" 格式?
                option_text = f"{display_name}"
                options.append(ft.dropdown.Option(key=stream_id, text=option_text))
                valid_stream_ids.add(stream_id)

        self.stream_dropdown.options = options
        # Flet Dropdown 的 value 似乎是用 key (stream_id) 来匹配的
        if current_value not in valid_stream_ids:
            # 如果之前的 stream_id 不再有效，尝试选择第一个，否则清空
            new_value = options[0].key if options else None
            if self.stream_dropdown.value != new_value:  # 避免不必要的更新循环
                self.stream_dropdown.value = new_value
                self.selected_stream_id_for_details = new_value
                await self.update_detail_charts(new_value)

        if self.page and self.stream_dropdown.page:  # 确保控件已挂载再更新
            self.stream_dropdown.update()

    async def on_stream_selected(self, e):
        selected_id = e.control.value  # value 应该是 stream_id (key)
        print(f"[InterestMonitor] 选择了 Stream ID: {selected_id}")
        if self.selected_stream_id_for_details != selected_id:
            self.selected_stream_id_for_details = selected_id
            await self.update_detail_charts(selected_id)
            # Dropdown 更新是自动的，但图表和文本需要手动触发父容器更新
            if self.page:
                self.update()

    async def update_detail_texts(self, stream_id):
        if not self.detail_texts or not hasattr(self.detail_texts, "controls") or len(self.detail_texts.controls) < 4:
            print("[InterestMonitor] 错误：detail_texts 未正确初始化或控件不足")
            return

        if stream_id:
            sub_mind = self.stream_sub_minds.get(stream_id, "N/A")
            chat_state = self.stream_chat_states.get(stream_id, "N/A")
            threshold = self.stream_threshold_status.get(stream_id, False)
            last_active_ts = self.stream_last_active.get(stream_id)

            self.detail_texts.controls[0].value = f"想法: {sub_mind}"
            self.detail_texts.controls[0].tooltip = sub_mind  # 添加 tooltip
            self.detail_texts.controls[1].value = f"状态: {chat_state}"
            self.detail_texts.controls[2].value = f"阈值以上: {'是' if threshold else '否'}"
            self.detail_texts.controls[3].value = f"最后活跃: {format_timestamp(last_active_ts)}"
            # self.detail_texts.controls[4].value = ... # 如果有更多详情
        else:
            self.detail_texts.controls[0].value = "想法: N/A"
            self.detail_texts.controls[0].tooltip = "N/A"
            self.detail_texts.controls[1].value = "状态: N/A"
            self.detail_texts.controls[2].value = "阈值以上: N/A"
            self.detail_texts.controls[3].value = "最后活跃: N/A"
            # self.detail_texts.controls[4].value = "N/A"

        if self.page and self.detail_texts.page:  # 确保控件已挂载再更新
            self.detail_texts.update()

    def update_status(self, message: str, color: str = ft.colors.SECONDARY):
        max_len = 150
        display_message = (message[:max_len] + "...") if len(message) > max_len else message
        self.status_text.value = display_message
        self.status_text.color = color
        if self.page and self.status_text.page:
            self.status_text.update()

    def get_time_range(self, history_dict, is_prob=False):
        all_ts = []
        target_history_key = self.probability_history if is_prob else self.stream_history
        for stream_id, _history in history_dict.items():
            # 使用正确的历史记录字典
            actual_history = target_history_key.get(stream_id)
            if actual_history:
                all_ts.extend([ts for ts, _ in actual_history])

        if not all_ts:
            now = time.time()
            return now - 3600, now

        min_ts = min(all_ts)
        max_ts = max(all_ts)
        padding = (max_ts - min_ts) * 0.05 if max_ts > min_ts else 10
        return min_ts - padding, max_ts + padding


# --- 测试部分保持不变 ---
if __name__ == "__main__":
    # ... (创建测试日志文件代码不变) ...
    if not os.path.exists("logs/interest"):
        os.makedirs("logs/interest")
    test_log_path = LOG_FILE_PATH
    with open(test_log_path, "w", encoding="utf-8") as f:
        # ... (写入测试数据不变) ...
        ts = time.time()
        f.write(
            json.dumps(
                {
                    "timestamp": ts - 60,
                    "mai_state": "Idle",
                    "main_mind": "Start",
                    "subflow_count": 2,
                    "subflows": [
                        {
                            "stream_id": "user1",
                            "group_name": "用户A",
                            "interest_level": 5,
                            "start_hfc_probability": 0.1,
                            "sub_mind": "Thinking about A",
                            "sub_chat_state": "Active",
                            "is_above_threshold": False,
                            "chat_state_changed_time": ts - 65,
                        },
                        {
                            "stream_id": "user2",
                            "group_name": "用户B",
                            "interest_level": 3,
                            "start_hfc_probability": 0.05,
                            "sub_mind": "Thinking about B",
                            "sub_chat_state": "Idle",
                            "is_above_threshold": False,
                            "chat_state_changed_time": ts - 70,
                        },
                    ],
                }
            )
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "timestamp": ts - 30,
                    "mai_state": "Processing",
                    "main_mind": "Thinking",
                    "subflow_count": 2,
                    "subflows": [
                        {
                            "stream_id": "user1",
                            "group_name": "用户A",
                            "interest_level": 6,
                            "start_hfc_probability": 0.2,
                            "sub_mind": "Processing A's request",
                            "sub_chat_state": "Active",
                            "is_above_threshold": True,
                            "chat_state_changed_time": ts - 65,
                        },
                        {
                            "stream_id": "user2",
                            "group_name": "用户B",
                            "interest_level": 4,
                            "start_hfc_probability": 0.1,
                            "sub_mind": "Waiting for B",
                            "sub_chat_state": "Idle",
                            "is_above_threshold": False,
                            "chat_state_changed_time": ts - 70,
                        },
                    ],
                }
            )
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "timestamp": ts,
                    "mai_state": "Responding",
                    "main_mind": "Responding to A",
                    "subflow_count": 2,
                    "subflows": [
                        {
                            "stream_id": "user1",
                            "group_name": "用户A",
                            "interest_level": 7,
                            "start_hfc_probability": 0.3,
                            "sub_mind": "Generating response A",
                            "sub_chat_state": "Active",
                            "is_above_threshold": True,
                            "chat_state_changed_time": ts - 65,
                        },
                        {
                            "stream_id": "user2",
                            "group_name": "用户B",
                            "interest_level": 3,
                            "start_hfc_probability": 0.08,
                            "sub_mind": "Still waiting B",
                            "sub_chat_state": "Idle",
                            "is_above_threshold": False,
                            "chat_state_changed_time": ts - 70,
                        },
                    ],
                }
            )
            + "\n"
        )

    async def main(page: ft.Page):
        page.title = "Interest Monitor 测试"
        page.vertical_alignment = ft.MainAxisAlignment.START
        # --- 让窗口适应内容 ---
        page.window_width = 800  # 增加宽度
        page.window_height = 650  # 增加高度
        page.padding = 10  # 统一内边距

        monitor = InterestMonitorDisplay()
        # --- 添加外层容器并设置属性 ---
        container = ft.Container(
            content=monitor,
            expand=True,  # 让容器扩展
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=ft.border_radius.all(5),
            padding=10,
            margin=ft.margin.only(top=10),
        )
        page.add(container)  # 将容器添加到页面

    ft.app(target=main)
