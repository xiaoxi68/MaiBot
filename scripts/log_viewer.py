import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, filedialog
import json
from pathlib import Path
import threading
import queue
import time
import toml
from datetime import datetime


class LogFormatter:
    """日志格式化器，同步logger.py的格式"""

    def __init__(self, config, custom_module_colors=None, custom_level_colors=None):
        self.config = config

        # 日志级别颜色
        self.level_colors = {
            "debug": "#FFA500",  # 橙色
            "info": "#0000FF",  # 蓝色
            "success": "#008000",  # 绿色
            "warning": "#FFFF00",  # 黄色
            "error": "#FF0000",  # 红色
            "critical": "#800080",  # 紫色
        }

        # 模块颜色映射 - 同步logger.py中的MODULE_COLORS
        self.module_colors = {
            "api": "#00FF00",  # 亮绿色
            "emoji": "#00FF00",  # 亮绿色
            "chat": "#0080FF",  # 亮蓝色
            "config": "#FFFF00",  # 亮黄色
            "common": "#FF00FF",  # 亮紫色
            "tools": "#00FFFF",  # 亮青色
            "lpmm": "#00FFFF",  # 亮青色
            "plugin_system": "#FF0080",  # 亮红色
            "experimental": "#FFFFFF",  # 亮白色
            "person_info": "#008000",  # 绿色
            "individuality": "#000080",  # 蓝色
            "manager": "#800080",  # 紫色
            "llm_models": "#008080",  # 青色
            "plugins": "#800000",  # 红色
            "plugin_api": "#808000",  # 黄色
            "remote": "#8000FF",  # 紫蓝色
        }

        # 应用自定义颜色
        if custom_module_colors:
            self.module_colors.update(custom_module_colors)
        if custom_level_colors:
            self.level_colors.update(custom_level_colors)

        # 根据配置决定颜色启用状态
        color_text = self.config.get("color_text", "full")
        if color_text == "none":
            self.enable_colors = False
            self.enable_module_colors = False
            self.enable_level_colors = False
        elif color_text == "title":
            self.enable_colors = True
            self.enable_module_colors = True
            self.enable_level_colors = False
        elif color_text == "full":
            self.enable_colors = True
            self.enable_module_colors = True
            self.enable_level_colors = True
        else:
            self.enable_colors = True
            self.enable_module_colors = True
            self.enable_level_colors = False

    def format_log_entry(self, log_entry):
        """格式化日志条目，返回格式化后的文本和样式标签"""
        # 获取基本信息
        timestamp = log_entry.get("timestamp", "")
        level = log_entry.get("level", "info")
        logger_name = log_entry.get("logger_name", "")
        event = log_entry.get("event", "")

        # 格式化时间戳
        formatted_timestamp = self.format_timestamp(timestamp)

        # 构建输出部分
        parts = []
        tags = []

        # 日志级别样式配置
        log_level_style = self.config.get("log_level_style", "lite")

        # 时间戳
        if formatted_timestamp:
            if log_level_style == "lite" and self.enable_level_colors:
                # lite模式下时间戳按级别着色
                parts.append(formatted_timestamp)
                tags.append(f"level_{level}")
            else:
                parts.append(formatted_timestamp)
                tags.append("timestamp")

        # 日志级别显示
        if log_level_style == "full":
            # 显示完整级别名
            level_text = f"[{level.upper():>8}]"
            parts.append(level_text)
            if self.enable_level_colors:
                tags.append(f"level_{level}")
            else:
                tags.append("level")
        elif log_level_style == "compact":
            # 只显示首字母
            level_text = f"[{level.upper()[0]:>8}]"
            parts.append(level_text)
            if self.enable_level_colors:
                tags.append(f"level_{level}")
            else:
                tags.append("level")
        # lite模式不显示级别

        # 模块名称
        if logger_name:
            module_text = f"[{logger_name}]"
            parts.append(module_text)
            if self.enable_module_colors:
                tags.append(f"module_{logger_name}")
            else:
                tags.append("module")

        # 消息内容
        if isinstance(event, str):
            parts.append(event)
        elif isinstance(event, dict):
            try:
                parts.append(json.dumps(event, ensure_ascii=False, indent=None))
            except (TypeError, ValueError):
                parts.append(str(event))
        else:
            parts.append(str(event))
        tags.append("message")

        # 处理其他字段
        extras = []
        for key, value in log_entry.items():
            if key not in ("timestamp", "level", "logger_name", "event"):
                if isinstance(value, (dict, list)):
                    try:
                        value_str = json.dumps(value, ensure_ascii=False, indent=None)
                    except (TypeError, ValueError):
                        value_str = str(value)
                else:
                    value_str = str(value)
                extras.append(f"{key}={value_str}")

        if extras:
            parts.append(" ".join(extras))
            tags.append("extras")

        return parts, tags

    def format_timestamp(self, timestamp):
        """格式化时间戳"""
        if not timestamp:
            return ""

        try:
            # 尝试解析ISO格式时间戳
            if "T" in timestamp:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                # 假设已经是格式化的字符串
                return timestamp

            # 根据配置格式化
            date_style = self.config.get("date_style", "m-d H:i:s")
            format_map = {
                "Y": "%Y",  # 4位年份
                "m": "%m",  # 月份（01-12）
                "d": "%d",  # 日期（01-31）
                "H": "%H",  # 小时（00-23）
                "i": "%M",  # 分钟（00-59）
                "s": "%S",  # 秒数（00-59）
            }

            python_format = date_style
            for php_char, python_char in format_map.items():
                python_format = python_format.replace(php_char, python_char)

            return dt.strftime(python_format)
        except Exception:
            return timestamp


class LogViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("MaiBot日志查看器")
        self.root.geometry("1200x800")

        # 加载配置
        self.load_config()

        # 初始化日志格式化器
        self.formatter = LogFormatter(self.log_config, self.custom_module_colors, self.custom_level_colors)

        # 创建主框架
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建菜单栏
        self.create_menu()

        # 创建控制面板
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.pack(fill=tk.X, pady=(0, 5))

        # 模块选择框架
        self.module_frame = ttk.LabelFrame(self.control_frame, text="模块")
        self.module_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 创建模块选择滚动区域
        self.module_canvas = tk.Canvas(self.module_frame, height=80)
        self.module_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 创建模块选择内部框架
        self.module_inner_frame = ttk.Frame(self.module_canvas)
        self.module_canvas.create_window((0, 0), window=self.module_inner_frame, anchor="nw")

        # 创建右侧控制区域（级别和搜索）
        self.right_control_frame = ttk.Frame(self.control_frame)
        self.right_control_frame.pack(side=tk.RIGHT, padx=5)

        # 映射编辑按钮
        mapping_btn = ttk.Button(self.right_control_frame, text="模块映射", command=self.edit_module_mapping)
        mapping_btn.pack(side=tk.TOP, fill=tk.X, pady=1)

        # 日志级别选择
        level_frame = ttk.Frame(self.right_control_frame)
        level_frame.pack(side=tk.TOP, fill=tk.X, pady=1)
        ttk.Label(level_frame, text="级别:").pack(side=tk.LEFT, padx=2)
        self.level_var = tk.StringVar(value="全部")
        self.level_combo = ttk.Combobox(level_frame, textvariable=self.level_var, width=8)
        self.level_combo["values"] = ["全部", "debug", "info", "warning", "error", "critical"]
        self.level_combo.pack(side=tk.LEFT, padx=2)

        # 搜索框
        search_frame = ttk.Frame(self.right_control_frame)
        search_frame.pack(side=tk.TOP, fill=tk.X, pady=1)
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=15)
        self.search_entry.pack(side=tk.LEFT, padx=2)

        # 创建日志显示区域
        self.log_frame = ttk.Frame(self.main_frame)
        self.log_frame.pack(fill=tk.BOTH, expand=True)

        # 创建文本框和滚动条
        self.scrollbar = ttk.Scrollbar(self.log_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(
            self.log_frame,
            wrap=tk.WORD,
            yscrollcommand=self.scrollbar.set,
            background="#1e1e1e",
            foreground="#ffffff",
            insertbackground="#ffffff",
            selectbackground="#404040",
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.log_text.yview)

        # 配置文本标签样式
        self.configure_text_tags()

        # 模块名映射
        self.module_name_mapping = {
            "api": "API接口",
            "async_task_manager": "异步任务管理器",
            "background_tasks": "后台任务",
            "base_tool": "基础工具",
            "chat_stream": "聊天流",
            "component_registry": "组件注册器",
            "config": "配置",
            "database_model": "数据库模型",
            "emoji": "表情",
            "heartflow": "心流",
            "local_storage": "本地存储",
            "lpmm": "LPMM",
            "maibot_statistic": "MaiBot统计",
            "main_message": "主消息",
            "main": "主程序",
            "memory": "内存",
            "mood": "情绪",
            "plugin_manager": "插件管理器",
            "remote": "远程",
            "willing": "意愿",
        }

        # 加载自定义映射
        self.load_module_mapping()

        # 创建日志队列和缓存
        self.log_queue = queue.Queue()
        self.log_cache = []

        # 选中的模块集合
        self.selected_modules = set()

        # 初始化模块列表
        self.modules = set()
        self.update_module_list()

        # 绑定事件
        self.level_combo.bind("<<ComboboxSelected>>", self.filter_logs)
        self.search_var.trace("w", self.filter_logs)

        # 启动日志监控线程
        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_log_file)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        # 启动日志更新线程
        self.update_thread = threading.Thread(target=self.update_logs)
        self.update_thread.daemon = True
        self.update_thread.start()

    def load_config(self):
        """加载配置文件"""
        # 默认配置
        self.default_config = {
            "log": {"date_style": "m-d H:i:s", "log_level_style": "lite", "color_text": "full", "log_level": "INFO"},
            "viewer": {
                "theme": "dark",
                "font_size": 10,
                "max_lines": 1000,
                "auto_scroll": True,
                "show_milliseconds": False,
                "window": {"width": 1200, "height": 800, "remember_position": True},
            },
        }

        # 从bot_config.toml加载日志配置
        config_path = Path("config/bot_config.toml")
        self.log_config = self.default_config["log"].copy()
        self.viewer_config = self.default_config["viewer"].copy()

        try:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    bot_config = toml.load(f)
                    if "log" in bot_config:
                        self.log_config.update(bot_config["log"])
        except Exception as e:
            print(f"加载bot配置失败: {e}")

        # 从viewer配置文件加载查看器配置
        viewer_config_path = Path("config/log_viewer_config.toml")
        self.custom_module_colors = {}
        self.custom_level_colors = {}

        try:
            if viewer_config_path.exists():
                with open(viewer_config_path, "r", encoding="utf-8") as f:
                    viewer_config = toml.load(f)
                    if "viewer" in viewer_config:
                        self.viewer_config.update(viewer_config["viewer"])

                        # 加载自定义模块颜色
                        if "module_colors" in viewer_config["viewer"]:
                            self.custom_module_colors = viewer_config["viewer"]["module_colors"]

                        # 加载自定义级别颜色
                        if "level_colors" in viewer_config["viewer"]:
                            self.custom_level_colors = viewer_config["viewer"]["level_colors"]

                    if "log" in viewer_config:
                        self.log_config.update(viewer_config["log"])
        except Exception as e:
            print(f"加载查看器配置失败: {e}")

        # 应用窗口配置
        window_config = self.viewer_config.get("window", {})
        window_width = window_config.get("width", 1200)
        window_height = window_config.get("height", 800)
        self.root.geometry(f"{window_width}x{window_height}")

    def save_viewer_config(self):
        """保存查看器配置"""
        # 准备完整的配置数据
        viewer_config_copy = self.viewer_config.copy()

        # 保存自定义颜色（只保存与默认值不同的颜色）
        if self.custom_module_colors:
            viewer_config_copy["module_colors"] = self.custom_module_colors
        if self.custom_level_colors:
            viewer_config_copy["level_colors"] = self.custom_level_colors

        config_data = {"log": self.log_config, "viewer": viewer_config_copy}

        config_path = Path("config/log_viewer_config.toml")
        config_path.parent.mkdir(exist_ok=True)

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                toml.dump(config_data, f)
        except Exception as e:
            print(f"保存查看器配置失败: {e}")

    def create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 配置菜单
        config_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="配置", menu=config_menu)
        config_menu.add_command(label="日志格式设置", command=self.show_format_settings)
        config_menu.add_command(label="颜色设置", command=self.show_color_settings)
        config_menu.add_command(label="查看器设置", command=self.show_viewer_settings)
        config_menu.add_separator()
        config_menu.add_command(label="重新加载配置", command=self.reload_config)

        # 工具菜单
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="工具", menu=tools_menu)
        tools_menu.add_command(label="清空日志显示", command=self.clear_log_display)
        tools_menu.add_command(label="导出当前日志", command=self.export_logs)

    def show_format_settings(self):
        """显示格式设置窗口"""
        format_window = tk.Toplevel(self.root)
        format_window.title("日志格式设置")
        format_window.geometry("400x300")

        frame = ttk.Frame(format_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 日期格式
        ttk.Label(frame, text="日期格式:").pack(anchor="w", pady=2)
        date_style_var = tk.StringVar(value=self.log_config.get("date_style", "m-d H:i:s"))
        date_entry = ttk.Entry(frame, textvariable=date_style_var, width=30)
        date_entry.pack(anchor="w", pady=2)
        ttk.Label(frame, text="格式说明: Y=年份, m=月份, d=日期, H=小时, i=分钟, s=秒", font=("", 8)).pack(
            anchor="w", pady=2
        )

        # 日志级别样式
        ttk.Label(frame, text="日志级别样式:").pack(anchor="w", pady=(10, 2))
        level_style_var = tk.StringVar(value=self.log_config.get("log_level_style", "lite"))
        level_frame = ttk.Frame(frame)
        level_frame.pack(anchor="w", pady=2)

        ttk.Radiobutton(level_frame, text="简洁(lite)", variable=level_style_var, value="lite").pack(
            side="left", padx=(0, 10)
        )
        ttk.Radiobutton(level_frame, text="紧凑(compact)", variable=level_style_var, value="compact").pack(
            side="left", padx=(0, 10)
        )
        ttk.Radiobutton(level_frame, text="完整(full)", variable=level_style_var, value="full").pack(
            side="left", padx=(0, 10)
        )

        # 颜色文本设置
        ttk.Label(frame, text="文本颜色设置:").pack(anchor="w", pady=(10, 2))
        color_text_var = tk.StringVar(value=self.log_config.get("color_text", "full"))
        color_frame = ttk.Frame(frame)
        color_frame.pack(anchor="w", pady=2)

        ttk.Radiobutton(color_frame, text="无颜色(none)", variable=color_text_var, value="none").pack(
            side="left", padx=(0, 10)
        )
        ttk.Radiobutton(color_frame, text="仅标题(title)", variable=color_text_var, value="title").pack(
            side="left", padx=(0, 10)
        )
        ttk.Radiobutton(color_frame, text="全部(full)", variable=color_text_var, value="full").pack(
            side="left", padx=(0, 10)
        )

        # 按钮
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=(20, 0))

        def apply_format():
            self.log_config["date_style"] = date_style_var.get()
            self.log_config["log_level_style"] = level_style_var.get()
            self.log_config["color_text"] = color_text_var.get()

            # 重新初始化格式化器
            self.formatter = LogFormatter(self.log_config, self.custom_module_colors, self.custom_level_colors)
            self.configure_text_tags()

            # 保存配置
            self.save_viewer_config()

            # 重新过滤日志以应用新格式
            self.filter_logs()

            format_window.destroy()

        ttk.Button(button_frame, text="应用", command=apply_format).pack(side="right", padx=(5, 0))
        ttk.Button(button_frame, text="取消", command=format_window.destroy).pack(side="right")

    def show_viewer_settings(self):
        """显示查看器设置窗口"""
        viewer_window = tk.Toplevel(self.root)
        viewer_window.title("查看器设置")
        viewer_window.geometry("350x250")

        frame = ttk.Frame(viewer_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 主题设置
        ttk.Label(frame, text="主题:").pack(anchor="w", pady=2)
        theme_var = tk.StringVar(value=self.viewer_config.get("theme", "dark"))
        theme_frame = ttk.Frame(frame)
        theme_frame.pack(anchor="w", pady=2)
        ttk.Radiobutton(theme_frame, text="深色", variable=theme_var, value="dark").pack(side="left", padx=(0, 10))
        ttk.Radiobutton(theme_frame, text="浅色", variable=theme_var, value="light").pack(side="left")

        # 字体大小
        ttk.Label(frame, text="字体大小:").pack(anchor="w", pady=(10, 2))
        font_size_var = tk.IntVar(value=self.viewer_config.get("font_size", 10))
        font_size_spin = ttk.Spinbox(frame, from_=8, to=20, textvariable=font_size_var, width=10)
        font_size_spin.pack(anchor="w", pady=2)

        # 最大行数
        ttk.Label(frame, text="最大显示行数:").pack(anchor="w", pady=(10, 2))
        max_lines_var = tk.IntVar(value=self.viewer_config.get("max_lines", 1000))
        max_lines_spin = ttk.Spinbox(frame, from_=100, to=10000, increment=100, textvariable=max_lines_var, width=10)
        max_lines_spin.pack(anchor="w", pady=2)

        # 自动滚动
        auto_scroll_var = tk.BooleanVar(value=self.viewer_config.get("auto_scroll", True))
        ttk.Checkbutton(frame, text="自动滚动到底部", variable=auto_scroll_var).pack(anchor="w", pady=(10, 2))

        # 按钮
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=(20, 0))

        def apply_viewer_settings():
            self.viewer_config["theme"] = theme_var.get()
            self.viewer_config["font_size"] = font_size_var.get()
            self.viewer_config["max_lines"] = max_lines_var.get()
            self.viewer_config["auto_scroll"] = auto_scroll_var.get()

            # 应用主题
            self.apply_theme()

            # 保存配置
            self.save_viewer_config()

            viewer_window.destroy()

        ttk.Button(button_frame, text="应用", command=apply_viewer_settings).pack(side="right", padx=(5, 0))
        ttk.Button(button_frame, text="取消", command=viewer_window.destroy).pack(side="right")

    def apply_theme(self):
        """应用主题设置"""
        theme = self.viewer_config.get("theme", "dark")
        font_size = self.viewer_config.get("font_size", 10)

        if theme == "dark":
            bg_color = "#1e1e1e"
            fg_color = "#ffffff"
            select_bg = "#404040"
        else:
            bg_color = "#ffffff"
            fg_color = "#000000"
            select_bg = "#c0c0c0"

        self.log_text.config(
            background=bg_color, foreground=fg_color, selectbackground=select_bg, font=("Consolas", font_size)
        )

        # 重新配置标签样式
        self.configure_text_tags()

    def configure_text_tags(self):
        """配置文本标签样式"""
        # 清除现有标签
        for tag in self.log_text.tag_names():
            if tag != "sel":
                self.log_text.tag_delete(tag)

        # 基础标签
        self.log_text.tag_configure("timestamp", foreground="#808080")
        self.log_text.tag_configure("level", foreground="#808080")
        self.log_text.tag_configure("module", foreground="#808080")
        self.log_text.tag_configure("message", foreground=self.log_text.cget("foreground"))
        self.log_text.tag_configure("extras", foreground="#808080")

        # 日志级别颜色标签
        for level, color in self.formatter.level_colors.items():
            self.log_text.tag_configure(f"level_{level}", foreground=color)

        # 模块颜色标签
        for module, color in self.formatter.module_colors.items():
            self.log_text.tag_configure(f"module_{module}", foreground=color)

    def reload_config(self):
        """重新加载配置"""
        self.load_config()
        self.formatter = LogFormatter(self.log_config, self.custom_module_colors, self.custom_level_colors)
        self.configure_text_tags()
        self.apply_theme()
        self.filter_logs()

    def clear_log_display(self):
        """清空日志显示"""
        self.log_text.delete(1.0, tk.END)

    def export_logs(self):
        """导出当前显示的日志"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(self.log_text.get(1.0, tk.END))
                messagebox.showinfo("导出成功", f"日志已导出到: {filename}")
            except Exception as e:
                messagebox.showerror("导出失败", f"导出日志时出错: {e}")

    def load_module_mapping(self):
        """加载自定义模块映射"""
        mapping_file = Path("config/module_mapping.json")
        if mapping_file.exists():
            try:
                with open(mapping_file, "r", encoding="utf-8") as f:
                    custom_mapping = json.load(f)
                    self.module_name_mapping.update(custom_mapping)
            except Exception as e:
                print(f"加载模块映射失败: {e}")

    def save_module_mapping(self):
        """保存自定义模块映射"""
        mapping_file = Path("config/module_mapping.json")
        mapping_file.parent.mkdir(exist_ok=True)
        try:
            with open(mapping_file, "w", encoding="utf-8") as f:
                json.dump(self.module_name_mapping, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存模块映射失败: {e}")

    def show_color_settings(self):
        """显示颜色设置窗口"""
        color_window = tk.Toplevel(self.root)
        color_window.title("颜色设置")
        color_window.geometry("300x400")

        # 创建滚动框架
        frame = ttk.Frame(color_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建滚动条
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 创建颜色设置列表
        canvas = tk.Canvas(frame, yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=canvas.yview)

        # 创建内部框架
        inner_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        # 添加日志级别颜色设置
        ttk.Label(inner_frame, text="日志级别颜色", font=("", 10, "bold")).pack(anchor="w", padx=5, pady=5)
        for level in ["info", "warning", "error"]:
            frame = ttk.Frame(inner_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(frame, text=level).pack(side=tk.LEFT)
            color_btn = ttk.Button(
                frame, text="选择颜色", command=lambda level_name=level: self.choose_color(level_name)
            )
            color_btn.pack(side=tk.RIGHT)
            # 显示当前颜色
            color_label = ttk.Label(frame, text="■", foreground=self.formatter.level_colors[level])
            color_label.pack(side=tk.RIGHT, padx=5)

        # 添加模块颜色设置
        ttk.Label(inner_frame, text="\n模块颜色", font=("", 10, "bold")).pack(anchor="w", padx=5, pady=5)
        for module in sorted(self.modules):
            frame = ttk.Frame(inner_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(frame, text=module).pack(side=tk.LEFT)
            color_btn = ttk.Button(frame, text="选择颜色", command=lambda m=module: self.choose_module_color(m))
            color_btn.pack(side=tk.RIGHT)
            # 显示当前颜色
            color = self.formatter.module_colors.get(module, "black")
            color_label = ttk.Label(frame, text="■", foreground=color)
            color_label.pack(side=tk.RIGHT, padx=5)

        # 更新画布滚动区域
        inner_frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

        # 添加确定按钮
        ttk.Button(color_window, text="确定", command=color_window.destroy).pack(pady=5)

    def choose_color(self, level):
        """选择日志级别颜色"""
        color = colorchooser.askcolor(color=self.formatter.level_colors[level])[1]
        if color:
            self.formatter.level_colors[level] = color
            self.custom_level_colors[level] = color  # 保存到自定义颜色
            self.configure_text_tags()
            self.save_viewer_config()  # 自动保存配置
            self.filter_logs()

    def choose_module_color(self, module):
        """选择模块颜色"""
        color = colorchooser.askcolor(color=self.formatter.module_colors.get(module, "black"))[1]
        if color:
            self.formatter.module_colors[module] = color
            self.custom_module_colors[module] = color  # 保存到自定义颜色
            self.configure_text_tags()
            self.save_viewer_config()  # 自动保存配置
            self.filter_logs()

    def update_module_list(self):
        """更新模块列表"""
        log_file = Path("logs/app.log.jsonl")
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        log_entry = json.loads(line)
                        if "logger_name" in log_entry:
                            self.modules.add(log_entry["logger_name"])
                    except json.JSONDecodeError:
                        continue

        # 清空现有选项
        for widget in self.module_inner_frame.winfo_children():
            widget.destroy()

        # 计算总模块数（包括"全部"）
        total_modules = len(self.modules) + 1
        max_cols = min(4, max(2, total_modules))  # 减少最大列数，避免超出边界

        # 配置网格列权重，让每列平均分配空间
        for i in range(max_cols):
            self.module_inner_frame.grid_columnconfigure(i, weight=1, uniform="module_col")

        # 创建一个多行布局
        current_row = 0
        current_col = 0

        # 添加"全部"选项
        all_frame = ttk.Frame(self.module_inner_frame)
        all_frame.grid(row=current_row, column=current_col, padx=3, pady=2, sticky="ew")

        all_var = tk.BooleanVar(value="全部" in self.selected_modules)
        all_check = ttk.Checkbutton(
            all_frame, text="全部", variable=all_var, command=lambda: self.toggle_module("全部", all_var)
        )
        all_check.pack(side=tk.LEFT)

        # 使用颜色标签替代按钮
        all_color = self.formatter.module_colors.get("全部", "black")
        all_color_label = ttk.Label(all_frame, text="■", foreground=all_color, width=2, cursor="hand2")
        all_color_label.pack(side=tk.LEFT, padx=2)
        all_color_label.bind("<Button-1>", lambda e: self.choose_module_color("全部"))

        current_col += 1

        # 添加其他模块选项
        for module in sorted(self.modules):
            if current_col >= max_cols:
                current_row += 1
                current_col = 0

            frame = ttk.Frame(self.module_inner_frame)
            frame.grid(row=current_row, column=current_col, padx=3, pady=2, sticky="ew")

            var = tk.BooleanVar(value=module in self.selected_modules)

            # 使用中文映射名称显示
            display_name = self.get_display_name(module)
            if len(display_name) > 12:
                display_name = display_name[:10] + "..."

            check = ttk.Checkbutton(
                frame, text=display_name, variable=var, command=lambda m=module, v=var: self.toggle_module(m, v)
            )
            check.pack(side=tk.LEFT)

            # 添加工具提示显示完整名称和英文名
            full_tooltip = f"{self.get_display_name(module)}"
            if module != self.get_display_name(module):
                full_tooltip += f"\n({module})"
            self.create_tooltip(check, full_tooltip)

            # 使用颜色标签替代按钮
            color = self.formatter.module_colors.get(module, "black")
            color_label = ttk.Label(frame, text="■", foreground=color, width=2, cursor="hand2")
            color_label.pack(side=tk.LEFT, padx=2)
            color_label.bind("<Button-1>", lambda e, m=module: self.choose_module_color(m))

            current_col += 1

        # 更新画布滚动区域
        self.module_inner_frame.update_idletasks()
        self.module_canvas.config(scrollregion=self.module_canvas.bbox("all"))

        # 添加垂直滚动条
        if not hasattr(self, "module_scrollbar"):
            self.module_scrollbar = ttk.Scrollbar(
                self.module_frame, orient=tk.VERTICAL, command=self.module_canvas.yview
            )
            self.module_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.module_canvas.config(yscrollcommand=self.module_scrollbar.set)

    def create_tooltip(self, widget, text):
        """为控件创建工具提示"""

        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
            label = ttk.Label(tooltip, text=text, background="lightyellow", relief="solid", borderwidth=1)
            label.pack()
            widget.tooltip = tooltip

        def on_leave(event):
            if hasattr(widget, "tooltip"):
                widget.tooltip.destroy()
                del widget.tooltip

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def toggle_module(self, module, var):
        """切换模块选择状态"""
        if module == "全部":
            if var.get():
                self.selected_modules = {"全部"}
            else:
                self.selected_modules.clear()
        else:
            if var.get():
                self.selected_modules.add(module)
                if "全部" in self.selected_modules:
                    self.selected_modules.remove("全部")
            else:
                self.selected_modules.discard(module)

        self.filter_logs()

    def monitor_log_file(self):
        """监控日志文件变化"""
        log_file = Path("logs/app.log.jsonl")
        last_position = 0

        while self.running:
            if log_file.exists():
                try:
                    # 使用共享读取模式，避免文件锁定
                    with open(log_file, "r", encoding="utf-8", buffering=1) as f:
                        f.seek(last_position)
                        new_lines = f.readlines()
                        last_position = f.tell()

                        for line in new_lines:
                            try:
                                log_entry = json.loads(line)
                                self.log_queue.put(log_entry)
                                self.log_cache.append(log_entry)

                                # 检查是否有新模块
                                if "logger_name" in log_entry:
                                    logger_name = log_entry["logger_name"]
                                    if logger_name not in self.modules:
                                        self.modules.add(logger_name)
                                        # 在主线程中更新模块列表UI
                                        self.root.after(0, self.update_module_list)

                            except json.JSONDecodeError:
                                continue
                except (FileNotFoundError, PermissionError) as e:
                    # 文件被占用或不存在时，等待更长时间
                    print(f"日志文件访问受限: {e}")
                    time.sleep(1)
                    continue
                except Exception as e:
                    print(f"读取日志文件时出错: {e}")

            time.sleep(0.1)

    def update_logs(self):
        """更新日志显示"""
        while self.running:
            try:
                log_entry = self.log_queue.get(timeout=0.1)
                self.process_log_entry(log_entry)
            except queue.Empty:
                continue

    def process_log_entry(self, log_entry):
        """处理日志条目"""
        # 检查过滤条件
        if not self.should_show_log(log_entry):
            return

        # 使用格式化器格式化日志
        parts, tags = self.formatter.format_log_entry(log_entry)

        # 在主线程中更新UI
        self.root.after(0, lambda: self.add_formatted_log_line(parts, tags, log_entry))

    def add_formatted_log_line(self, parts, tags, log_entry):
        """添加格式化的日志行到文本框"""
        # 控制最大行数
        max_lines = self.viewer_config.get("max_lines", 1000)
        current_lines = int(self.log_text.index("end-1c").split(".")[0])

        if current_lines > max_lines:
            # 删除前面的行
            lines_to_delete = current_lines - max_lines + 100  # 一次删除多一些，减少频繁操作
            self.log_text.delete(1.0, f"{lines_to_delete}.0")

        # 插入格式化的文本
        for i, part in enumerate(parts):
            if i < len(tags):
                tag = tags[i]
                # 根据内容类型选择合适的标签
                if tag.startswith("level_"):
                    if self.formatter.enable_level_colors:
                        self.log_text.insert(tk.END, part, tag)
                    else:
                        self.log_text.insert(tk.END, part, "level")
                elif tag.startswith("module_"):
                    if self.formatter.enable_module_colors:
                        self.log_text.insert(tk.END, part, tag)
                    else:
                        self.log_text.insert(tk.END, part, "module")
                else:
                    self.log_text.insert(tk.END, part, tag)
            else:
                self.log_text.insert(tk.END, part)

            # 在部分之间添加空格（除了最后一个）
            if i < len(parts) - 1:
                self.log_text.insert(tk.END, " ")

        self.log_text.insert(tk.END, "\n")

        # 自动滚动
        if self.viewer_config.get("auto_scroll", True):
            if self.log_text.yview()[1] >= 0.99:
                self.log_text.see(tk.END)

    def should_show_log(self, log_entry):
        """检查日志是否应该显示"""
        # 检查模块过滤
        if self.selected_modules:
            if "全部" not in self.selected_modules:
                if log_entry.get("logger_name") not in self.selected_modules:
                    return False

        # 检查级别过滤
        if self.level_var.get() != "全部":
            if log_entry.get("level") != self.level_var.get():
                return False

        # 检查搜索过滤
        search_text = self.search_var.get().lower()
        if search_text:
            event = str(log_entry.get("event", "")).lower()
            logger_name = str(log_entry.get("logger_name", "")).lower()
            if search_text not in event and search_text not in logger_name:
                return False

        return True

    def filter_logs(self, *args):
        """过滤日志"""
        # 保存当前滚动位置
        scroll_position = self.log_text.yview()

        # 清空显示
        self.log_text.delete(1.0, tk.END)

        # 重新显示所有符合条件的日志
        for log_entry in self.log_cache:
            if self.should_show_log(log_entry):
                parts, tags = self.formatter.format_log_entry(log_entry)
                self.add_formatted_log_line(parts, tags, log_entry)

        # 恢复滚动位置（如果不是自动滚动模式）
        if not self.viewer_config.get("auto_scroll", True):
            self.log_text.yview_moveto(scroll_position[0])

    def get_display_name(self, module_name):
        """获取模块的显示名称"""
        return self.module_name_mapping.get(module_name, module_name)

    def edit_module_mapping(self):
        """编辑模块映射"""
        mapping_window = tk.Toplevel(self.root)
        mapping_window.title("编辑模块映射")
        mapping_window.geometry("500x600")

        # 创建滚动框架
        frame = ttk.Frame(mapping_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建滚动条
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 创建映射编辑列表
        canvas = tk.Canvas(frame, yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=canvas.yview)

        # 创建内部框架
        inner_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        # 添加标题
        ttk.Label(inner_frame, text="模块映射编辑", font=("", 12, "bold")).pack(anchor="w", padx=5, pady=5)
        ttk.Label(inner_frame, text="英文名 -> 中文名", font=("", 10)).pack(anchor="w", padx=5, pady=2)

        # 映射编辑字典
        mapping_vars = {}

        # 添加现有模块的映射编辑
        all_modules = sorted(self.modules)
        for module in all_modules:
            frame_row = ttk.Frame(inner_frame)
            frame_row.pack(fill=tk.X, padx=5, pady=2)

            ttk.Label(frame_row, text=module, width=20).pack(side=tk.LEFT, padx=5)
            ttk.Label(frame_row, text="->").pack(side=tk.LEFT, padx=5)

            var = tk.StringVar(value=self.module_name_mapping.get(module, module))
            mapping_vars[module] = var
            entry = ttk.Entry(frame_row, textvariable=var, width=25)
            entry.pack(side=tk.LEFT, padx=5)

        # 更新画布滚动区域
        inner_frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

        def save_mappings():
            # 更新映射
            for module, var in mapping_vars.items():
                new_name = var.get().strip()
                if new_name and new_name != module:
                    self.module_name_mapping[module] = new_name
                elif module in self.module_name_mapping and not new_name:
                    del self.module_name_mapping[module]

            # 保存到文件
            self.save_module_mapping()
            # 更新模块列表显示
            self.update_module_list()
            mapping_window.destroy()

        # 添加按钮
        button_frame = ttk.Frame(mapping_window)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(button_frame, text="保存", command=save_mappings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="取消", command=mapping_window.destroy).pack(side=tk.RIGHT, padx=5)


def main():
    root = tk.Tk()
    LogViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
