import tkinter as tk
from tkinter import ttk, colorchooser
import json
from pathlib import Path
import threading
import queue
import time

class LogViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("MaiBot日志查看器")
        self.root.geometry("1200x800")
        
        # 创建主框架
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
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
        self.module_canvas.create_window((0, 0), window=self.module_inner_frame, anchor='nw')
        
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
        self.level_combo['values'] = ['全部', 'info', 'warning', 'error']
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
        
        self.log_text = tk.Text(self.log_frame, wrap=tk.WORD, yscrollcommand=self.scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.log_text.yview)
        
        # 设置默认标签颜色
        self.colors = {
            'info': 'black',
            'warning': 'orange',
            'error': 'red'
        }
        self.module_colors = {}
        
        # 模块名映射
        self.module_name_mapping = {
            'api': 'API接口',
            'async_task_manager': '异步任务管理器',
            'background_tasks': '后台任务',
            'base_tool': '基础工具',
            'chat_stream': '聊天流',
            'component_registry': '组件注册器',
            'config': '配置',
            'database_model': '数据库模型',
            'emoji': '表情',
            'heartflow': '心流',
            'local_storage': '本地存储',
            'lpmm': 'LPMM',
            'maibot_statistic': 'MaiBot统计',
            'main_message': '主消息',
            'main': '主程序',
            'memory': '内存',
            'mood': '情绪',
            'plugin_manager': '插件管理器',
            'remote': '远程',
            'willing': '意愿',
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
        self.level_combo.bind('<<ComboboxSelected>>', self.filter_logs)
        self.search_var.trace('w', self.filter_logs)
        
        # 启动日志监控线程
        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_log_file)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        # 启动日志更新线程
        self.update_thread = threading.Thread(target=self.update_logs)
        self.update_thread.daemon = True
        self.update_thread.start()

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
        canvas.create_window((0, 0), window=inner_frame, anchor='nw')
        
        # 添加日志级别颜色设置
        ttk.Label(inner_frame, text="日志级别颜色", font=('', 10, 'bold')).pack(anchor='w', padx=5, pady=5)
        for level in ['info', 'warning', 'error']:
            frame = ttk.Frame(inner_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(frame, text=level).pack(side=tk.LEFT)
            color_btn = ttk.Button(frame, text="选择颜色", 
                                 command=lambda l=level: self.choose_color(l))
            color_btn.pack(side=tk.RIGHT)
            # 显示当前颜色
            color_label = ttk.Label(frame, text="■", foreground=self.colors[level])
            color_label.pack(side=tk.RIGHT, padx=5)
        
        # 添加模块颜色设置
        ttk.Label(inner_frame, text="\n模块颜色", font=('', 10, 'bold')).pack(anchor='w', padx=5, pady=5)
        for module in sorted(self.modules):
            frame = ttk.Frame(inner_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(frame, text=module).pack(side=tk.LEFT)
            color_btn = ttk.Button(frame, text="选择颜色", 
                                 command=lambda m=module: self.choose_module_color(m))
            color_btn.pack(side=tk.RIGHT)
            # 显示当前颜色
            color = self.module_colors.get(module, 'black')
            color_label = ttk.Label(frame, text="■", foreground=color)
            color_label.pack(side=tk.RIGHT, padx=5)
        
        # 更新画布滚动区域
        inner_frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))
        
        # 添加确定按钮
        ttk.Button(color_window, text="确定", command=color_window.destroy).pack(pady=5)

    def choose_color(self, level):
        """选择日志级别颜色"""
        color = colorchooser.askcolor(color=self.colors[level])[1]
        if color:
            self.colors[level] = color
            self.log_text.tag_configure(level, foreground=color)
            self.filter_logs()

    def choose_module_color(self, module):
        """选择模块颜色"""
        color = colorchooser.askcolor(color=self.module_colors.get(module, 'black'))[1]
        if color:
            self.module_colors[module] = color
            self.log_text.tag_configure(f"module_{module}", foreground=color)
            # 更新模块列表中的颜色显示
            self.update_module_color_display(module, color)
            self.filter_logs()

    def update_module_color_display(self, module, color):
        """更新模块列表中的颜色显示"""
        # 遍历模块框架中的所有子控件，找到对应模块的颜色标签并更新
        for widget in self.module_inner_frame.winfo_children():
            if isinstance(widget, ttk.Frame):
                # 检查这个框架是否包含目标模块
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Checkbutton):
                        if child.cget('text') == module:
                            # 找到了对应的模块，更新其颜色标签
                            for sibling in widget.winfo_children():
                                if isinstance(sibling, ttk.Label) and sibling.cget('text') == '■':
                                    sibling.config(foreground=color)
                                    return

    def update_module_list(self):
        """更新模块列表"""
        log_file = Path("logs/app.log.jsonl")
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line)
                        if 'logger_name' in log_entry:
                            self.modules.add(log_entry['logger_name'])
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
        all_frame.grid(row=current_row, column=current_col, padx=3, pady=2, sticky='ew')
        
        all_var = tk.BooleanVar(value='全部' in self.selected_modules)
        all_check = ttk.Checkbutton(all_frame, text="全部", variable=all_var, 
                                  command=lambda: self.toggle_module('全部', all_var))
        all_check.pack(side=tk.LEFT)
        
        # 使用颜色标签替代按钮
        all_color = self.module_colors.get('全部', 'black')
        all_color_label = ttk.Label(all_frame, text="■", foreground=all_color, width=2, cursor="hand2")
        all_color_label.pack(side=tk.LEFT, padx=2)
        all_color_label.bind('<Button-1>', lambda e: self.choose_module_color('全部'))
        
        current_col += 1
        
        # 添加其他模块选项
        for module in sorted(self.modules):
            if current_col >= max_cols:
                current_row += 1
                current_col = 0
                
            frame = ttk.Frame(self.module_inner_frame)
            frame.grid(row=current_row, column=current_col, padx=3, pady=2, sticky='ew')
            
            var = tk.BooleanVar(value=module in self.selected_modules)
            
            # 使用中文映射名称显示
            display_name = self.get_display_name(module)
            if len(display_name) > 12:
                display_name = display_name[:10] + "..."
                
            check = ttk.Checkbutton(frame, text=display_name, variable=var,
                                  command=lambda m=module, v=var: self.toggle_module(m, v))
            check.pack(side=tk.LEFT)
            
            # 添加工具提示显示完整名称和英文名
            full_tooltip = f"{self.get_display_name(module)}"
            if module != self.get_display_name(module):
                full_tooltip += f"\n({module})"
            self.create_tooltip(check, full_tooltip)
            
            # 使用颜色标签替代按钮
            color = self.module_colors.get(module, 'black')
            color_label = ttk.Label(frame, text="■", foreground=color, width=2, cursor="hand2")
            color_label.pack(side=tk.LEFT, padx=2)
            color_label.bind('<Button-1>', lambda e, m=module: self.choose_module_color(m))
            
            current_col += 1
        
        # 更新画布滚动区域
        self.module_inner_frame.update_idletasks()
        self.module_canvas.config(scrollregion=self.module_canvas.bbox("all"))
        
        # 添加垂直滚动条
        if not hasattr(self, 'module_scrollbar'):
            self.module_scrollbar = ttk.Scrollbar(self.module_frame, orient=tk.VERTICAL,
                                                command=self.module_canvas.yview)
            self.module_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.module_canvas.config(yscrollcommand=self.module_scrollbar.set)

    def create_tooltip(self, widget, text):
        """为控件创建工具提示"""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = ttk.Label(tooltip, text=text, background="lightyellow", relief="solid", borderwidth=1)
            label.pack()
            widget.tooltip = tooltip
            
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
                
        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)

    def toggle_module(self, module, var):
        """切换模块选择状态"""
        if module == '全部':
            if var.get():
                self.selected_modules = {'全部'}
            else:
                self.selected_modules.clear()
        else:
            if var.get():
                self.selected_modules.add(module)
                if '全部' in self.selected_modules:
                    self.selected_modules.remove('全部')
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
                    with open(log_file, 'r', encoding='utf-8') as f:
                        f.seek(last_position)
                        new_lines = f.readlines()
                        last_position = f.tell()
                        
                        for line in new_lines:
                            try:
                                log_entry = json.loads(line)
                                self.log_queue.put(log_entry)
                                self.log_cache.append(log_entry)
                                
                                # 检查是否有新模块
                                if 'logger_name' in log_entry:
                                    logger_name = log_entry['logger_name']
                                    if logger_name not in self.modules:
                                        self.modules.add(logger_name)
                                        # 在主线程中更新模块列表UI
                                        self.root.after(0, self.update_module_list)
                                        
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    print(f"Error reading log file: {e}")
            
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
        
        # 格式化日志
        timestamp = log_entry.get('timestamp', '')
        level = log_entry.get('level', 'info')
        logger_name = log_entry.get('logger_name', '')
        event = log_entry.get('event', '')
        
        log_line = f"{timestamp} [{level}] {logger_name}: {event}\n"
        
        # 在主线程中更新UI
        self.root.after(0, lambda: self.add_log_line(log_line, level, logger_name))

    def add_log_line(self, line, level, logger_name):
        """添加日志行到文本框"""
        self.log_text.insert(tk.END, line, (level, f"module_{logger_name}"))
        # 只有在用户没有手动滚动时才自动滚动到底部
        if self.log_text.yview()[1] >= 0.99:
            self.log_text.see(tk.END)

    def should_show_log(self, log_entry):
        """检查日志是否应该显示"""
        # 检查模块过滤
        if self.selected_modules:
            if '全部' not in self.selected_modules:
                if log_entry.get('logger_name') not in self.selected_modules:
                    return False
        
        # 检查级别过滤
        if self.level_var.get() != '全部':
            if log_entry.get('level') != self.level_var.get():
                return False
        
        # 检查搜索过滤
        search_text = self.search_var.get().lower()
        if search_text:
            event = str(log_entry.get('event', '')).lower()
            logger_name = str(log_entry.get('logger_name', '')).lower()
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
                timestamp = log_entry.get('timestamp', '')
                level = log_entry.get('level', 'info')
                logger_name = log_entry.get('logger_name', '')
                event = log_entry.get('event', '')
                log_line = f"{timestamp} [{level}] {logger_name}: {event}\n"
                self.log_text.insert(tk.END, log_line, (level, f"module_{logger_name}"))
        
        # 恢复滚动位置
        self.log_text.yview_moveto(scroll_position[0])

    def get_display_name(self, module_name):
        """获取模块的显示名称"""
        return self.module_name_mapping.get(module_name, module_name)

    def load_module_mapping(self):
        """加载自定义模块映射"""
        mapping_file = Path("config/module_mapping.json")
        if mapping_file.exists():
            try:
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    custom_mapping = json.load(f)
                    self.module_name_mapping.update(custom_mapping)
            except Exception as e:
                print(f"加载模块映射失败: {e}")

    def save_module_mapping(self):
        """保存自定义模块映射"""
        mapping_file = Path("config/module_mapping.json")
        mapping_file.parent.mkdir(exist_ok=True)
        try:
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(self.module_name_mapping, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存模块映射失败: {e}")

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
        canvas.create_window((0, 0), window=inner_frame, anchor='nw')
        
        # 添加标题
        ttk.Label(inner_frame, text="模块映射编辑", font=('', 12, 'bold')).pack(anchor='w', padx=5, pady=5)
        ttk.Label(inner_frame, text="英文名 -> 中文名", font=('', 10)).pack(anchor='w', padx=5, pady=2)
        
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
    app = LogViewer(root)
    root.mainloop()

if __name__ == "__main__":
    main() 