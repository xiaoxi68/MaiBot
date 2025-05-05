import flet as ft
import tomlkit
from typing import Dict, Any, List, Optional, Union
from pathlib import Path


def load_template_with_comments(template_filename: str = "bot_config_template.toml"):
    """
    加载指定的模板文件，保留所有注释。

    Args:
        template_filename: 要加载的模板文件名 (相对于 template/ 目录)。

    Returns:
        包含注释的TOML文档对象，如果失败则返回空文档。
    """
    try:
        # 首先尝试从相对路径加载 (相对于项目根目录)
        # 假设此脚本位于 src/MaiGoi/
        base_path = Path(__file__).parent.parent.parent
        template_path = base_path / "template" / template_filename

        if template_path.exists():
            print(f"找到模板文件: {template_path}")
            with open(template_path, "r", encoding="utf-8") as f:
                return tomlkit.parse(f.read())
        else:
            print(f"警告: 模板文件不存在: {template_path}")
            return tomlkit.document()
    except Exception as e:
        print(f"加载模板文件 '{template_filename}' 出错: {e}")
        return tomlkit.document()


def get_comment_for_key(template_doc, key_path: str) -> str:
    """
    获取指定键路径的注释 (修正版)

    Args:
        template_doc: 包含注释的TOML文档
        key_path: 点分隔的键路径，例如 "bot.qq"

    Returns:
        该键对应的注释字符串，如果没有则返回空字符串
    """
    if not template_doc:
        return ""

    try:
        parts = key_path.split(".")
        current_item = template_doc

        # 逐级导航到目标项或其父表
        for i, part in enumerate(parts):
            if part not in current_item:
                print(f"警告: 路径部分 '{part}' 在 {'.'.join(parts[:i])} 中未找到")
                return ""  # 路径不存在

            # 如果是最后一个部分，我们找到了目标项
            if i == len(parts) - 1:
                target_item = current_item[part]

                # --- 尝试从 trivia 获取注释 ---
                if hasattr(target_item, "trivia") and hasattr(target_item.trivia, "comment"):
                    comment_lines = target_item.trivia.comment.split("\n")
                    # 去除每行的 '#' 和首尾空格
                    cleaned_comment = "\n".join([line.strip().lstrip("#").strip() for line in comment_lines])
                    if cleaned_comment:
                        return cleaned_comment

                # --- 如果是顶级表，也检查容器自身的 trivia ---
                # (tomlkit 对于顶级表的注释存储方式可能略有不同)
                if isinstance(target_item, (tomlkit.items.Table, tomlkit.container.Container)) and len(parts) == 1:
                    if hasattr(target_item, "trivia") and hasattr(target_item.trivia, "comment"):
                        comment_lines = target_item.trivia.comment.split("\n")
                        cleaned_comment = "\n".join([line.strip().lstrip("#").strip() for line in comment_lines])
                        if cleaned_comment:
                            return cleaned_comment

                # 如果 trivia 中没有，尝试一些旧版或不常用的属性 (风险较高)
                # if hasattr(target_item, '_comment'): # 不推荐
                #    return str(target_item._comment).strip(" #")

                # 如果以上都找不到，返回空
                return ""

            # 继续导航到下一级
            current_item = current_item[part]
            # 如果中间路径不是表/字典，则无法继续
            if not isinstance(current_item, (dict, tomlkit.items.Table, tomlkit.container.Container)):
                print(f"警告: 路径部分 '{part}' 指向的不是表结构，无法继续导航")
                return ""

        return ""  # 理论上不应执行到这里，除非 key_path 为空

    except Exception as e:
        # 打印更详细的错误信息，包括路径和异常类型
        print(f"获取注释时发生意外错误 (路径: {key_path}): {type(e).__name__} - {e}")
        # print(traceback.format_exc()) # 可选：打印完整堆栈跟踪
        return ""


class TomlFormGenerator:
    """用于将TOML配置生成Flet表单控件的类。"""

    def __init__(
        self,
        page: ft.Page,
        config_data: Dict[str, Any],
        parent_container: ft.Column,
        template_filename: str = "bot_config_template.toml",
    ):
        """
        初始化表单生成器。

        Args:
            page: Flet Page 对象 (用于强制刷新)
            config_data: TOML配置数据（嵌套字典）
            parent_container: 要添加控件的父容器
            template_filename: 要使用的模板文件名 (相对于 template/ 目录)
        """
        self.page = page  # <-- 保存 Page 对象
        self.config_data = config_data  # 保存对原始数据的引用（重要！）
        self.parent_container = parent_container
        self.controls_map = {}  # 映射 full_path 到 Flet 控件
        self.expanded_sections = set()  # 记录展开的部分

        # 加载指定的模板文档
        self.template_doc = load_template_with_comments(template_filename)

        if not self.template_doc.value:
            print(f"警告：加载的模板 '{template_filename}' 为空，注释功能将不可用。")

    def build_form(self):
        """构建整个表单。"""
        self.parent_container.controls.clear()
        self.controls_map.clear()  # 清空控件映射
        # 使用 self.config_data 构建表单
        self._process_toml_section(self.config_data, self.parent_container)

    def _get_comment(self, key_path: str) -> str:
        """获取指定键路径的注释，并确保结果是字符串"""
        try:
            comment = get_comment_for_key(self.template_doc, key_path)
            # 确保返回值是字符串
            if comment and isinstance(comment, str):
                return comment
        except Exception as e:
            print(f"获取注释出错: {key_path}, {e}")
        return ""  # 如果出现任何问题，返回空字符串

    def _process_toml_section(
        self,
        section_data: Dict[str, Any],
        container: Union[ft.Column, ft.Container],
        section_path: str = "",
        indent: int = 0,
    ):
        """
        递归处理TOML配置的一个部分。

        Args:
            section_data: 要处理的配置部分
            container: 放置控件的容器（可以是Column或Container）
            section_path: 当前部分的路径（用于跟踪嵌套层级）
            indent: 当前缩进级别
        """
        # 确保container是有controls属性的对象
        if isinstance(container, ft.Container):
            if container.content and hasattr(container.content, "controls"):
                container = container.content
            else:
                # 如果Container没有有效的content，创建一个Column
                container.content = ft.Column([])
                container = container.content

        if not hasattr(container, "controls"):
            raise ValueError(f"传递给_process_toml_section的容器必须有controls属性，got: {type(container)}")

        # 先处理所有子部分（嵌套表）
        subsections = {}
        simple_items = {}

        # 分离子部分和简单值
        for key, value in section_data.items():
            if isinstance(value, (dict, tomlkit.items.Table)):
                subsections[key] = value
            else:
                simple_items[key] = value

        # 处理简单值
        for key, value in simple_items.items():
            full_path = f"{section_path}.{key}" if section_path else key
            control = self._create_control_for_value(key, value, full_path)
            if control:
                if indent > 0:  # 添加缩进
                    row = ft.Row(
                        [
                            ft.Container(width=indent * 20),  # 每级缩进20像素
                            control,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    )
                    container.controls.append(row)
                else:
                    container.controls.append(control)

        # 处理子部分
        for key, value in subsections.items():
            full_path = f"{section_path}.{key}" if section_path else key

            # 创建一个可展开/折叠的部分
            is_expanded = full_path in self.expanded_sections

            # 获取此部分的注释（安全获取）
            section_comment = self._get_comment(full_path)

            # 创建子部分的标题行
            section_title_elems = [
                ft.Container(width=indent * 20) if indent > 0 else ft.Container(width=0),
                ft.IconButton(
                    icon=ft.icons.ARROW_DROP_DOWN if is_expanded else ft.icons.ARROW_RIGHT,
                    on_click=lambda e, path=full_path: self._toggle_section(e, path),
                ),
                ft.Text(key, weight=ft.FontWeight.BOLD, size=16),
            ]

            # 如果有注释，添加一个Info图标并设置tooltip
            if section_comment and len(section_comment) > 0:
                try:
                    section_title_elems.append(
                        ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=section_comment, icon_size=16)
                    )
                except Exception as e:
                    print(f"创建信息图标时出错: {full_path}, {e}")

            section_title = ft.Row(
                section_title_elems,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

            container.controls.append(section_title)

            # 创建子部分的容器
            subsection_column = ft.Column([])
            subsection_container = ft.Container(content=subsection_column, visible=is_expanded)
            container.controls.append(subsection_container)

            # 递归处理子部分
            if is_expanded:
                self._process_toml_section(value, subsection_column, full_path, indent + 1)

    def _toggle_section(self, e, section_path):
        """切换部分的展开/折叠状态。"""
        # 使用一个简化和更稳定的方法来处理toggle
        print(f"切换部分: {section_path}")

        # 在点击的行的下一个容器中查找
        parent_row = e.control.parent
        if not parent_row or not isinstance(parent_row, ft.Row):
            print(f"错误: 无法找到父行: {e.control.parent}")
            return

        parent_container = parent_row.parent
        if not parent_container or not hasattr(parent_container, "controls"):
            print(f"错误: 无法找到父容器: {parent_row.parent}")
            return

        # 找到当前行在父容器中的索引
        try:
            row_index = parent_container.controls.index(parent_row)
        except ValueError:
            print(f"错误: 在父容器中找不到行: {parent_row}")
            return

        # 检查下一个控件是否是子部分容器
        if row_index + 1 >= len(parent_container.controls):
            print(f"错误: 行索引超出范围: {row_index + 1} >= {len(parent_container.controls)}")
            return

        subsection_container = parent_container.controls[row_index + 1]
        print(f"找到子部分容器: {type(subsection_container).__name__}")

        # 切换展开/折叠状态
        if section_path in self.expanded_sections:
            # 折叠
            e.control.icon = ft.icons.ARROW_RIGHT
            self.expanded_sections.remove(section_path)
            subsection_container.visible = False
            # parent_container.update() # <-- 改为 page.update()
        else:
            # 展开
            e.control.icon = ft.icons.ARROW_DROP_DOWN
            self.expanded_sections.add(section_path)
            subsection_container.visible = True

            # 如果容器刚刚变为可见，且内容为空，则加载内容
            if subsection_container.visible:
                # 获取子部分的内容列
                subsection_content = None
                if isinstance(subsection_container, ft.Container) and subsection_container.content:
                    subsection_content = subsection_container.content
                else:
                    subsection_content = subsection_container

                # 如果内容是Column且为空，则加载内容
                if isinstance(subsection_content, ft.Column) and len(subsection_content.controls) == 0:
                    # 获取配置数据
                    parts = section_path.split(".")
                    current = self.config_data
                    for part in parts:
                        if part and part in current:
                            current = current[part]
                        else:
                            print(f"警告: 配置路径不存在: {part} in {section_path}")
                            # parent_container.update() # <-- 改为 page.update()
                            self.page.update()  # <-- 在这里也强制页面更新
                            return

                    # 递归处理子部分
                    if isinstance(current, (dict, tomlkit.items.Table)):
                        indent = len(parts)  # 使用路径部分数量作为缩进级别
                        try:
                            # 处理内容但不立即更新UI
                            self._process_toml_section(current, subsection_content, section_path, indent)
                            # 只在完成内容处理后更新一次UI
                            # parent_container.update() # <-- 改为 page.update()
                        except Exception as ex:
                            print(f"处理子部分时出错: {ex}")
                    else:
                        print(f"警告: 配置数据不是字典类型: {type(current).__name__}")
                        # parent_container.update() # <-- 改为 page.update()
            # else:
            # 如果只是切换可见性，简单更新父容器
            # parent_container.update() # <-- 改为 page.update()

        # 强制更新整个页面
        if self.page:
            try:
                self.page.update()  # <-- 在函数末尾强制页面更新
            except Exception as page_update_e:
                print(f"强制页面更新失败: {page_update_e}")
        else:
            print("警告: _toggle_section 中无法访问 Page 对象进行更新")

    def _create_control_for_value(self, key: str, value: Any, full_path: str) -> Optional[ft.Control]:
        """
        根据值的类型创建适当的控件。

        Args:
            key: 配置键
            value: 配置值
            full_path: 配置项的完整路径

        Returns:
            对应类型的Flet控件
        """
        # 获取注释（安全获取）
        comment = self._get_comment(full_path)
        comment_valid = isinstance(comment, str) and len(comment) > 0

        # 根据类型创建不同的控件
        if isinstance(value, bool):
            return self._create_boolean_control(key, value, full_path, comment if comment_valid else "")
        elif isinstance(value, (int, float)):
            return self._create_number_control(key, value, full_path, comment if comment_valid else "")
        elif isinstance(value, str):
            return self._create_string_control(key, value, full_path, comment if comment_valid else "")
        elif isinstance(value, list):
            return self._create_list_control(key, value, full_path, comment if comment_valid else "")
        elif isinstance(value, set):
            # 特殊处理集合类型（groups部分经常使用）
            print(f"处理集合类型: {key} = {value}")
            try:
                return self._create_set_control(key, value, full_path, comment if comment_valid else "")
            except Exception as e:
                print(f"创建集合控件时出错: {e}")
                # 如果创建失败，返回只读文本
                return ft.Text(f"{key}: {value} (集合类型，处理失败)", italic=True)
        else:
            # 其他类型默认显示为只读文本
            control = ft.Text(f"{key}: {value} (类型不支持编辑: {type(value).__name__})", italic=True)

            # 如果有有效的注释，添加图标
            if comment_valid:
                try:
                    # 在只读文本旁加上注释图标
                    return ft.Row([control, ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=comment, icon_size=16)])
                except Exception:
                    pass  # 如果添加图标失败，仍返回原始控件

            return control

    def _update_config_value(self, path: str, new_value: Any):
        """递归地更新 self.config_data 中嵌套字典的值。"""
        keys = path.split(".")
        d = self.config_data
        try:
            for key in keys[:-1]:
                d = d[key]
            # 确保最后一个键存在并且可以赋值
            if keys[-1] in d:
                # 类型转换 (尝试)
                original_value = d[keys[-1]]
                try:
                    if isinstance(original_value, bool):
                        new_value = str(new_value).lower() in ("true", "1", "yes")
                    elif isinstance(original_value, int):
                        new_value = int(new_value)
                    elif isinstance(original_value, float):
                        new_value = float(new_value)
                    # Add other type checks if needed (e.g., list, set)
                except (ValueError, TypeError) as e:
                    print(
                        f"类型转换错误 ({path}): 输入 '{new_value}' ({type(new_value)}), 期望类型 {type(original_value)}. 错误: {e}"
                    )
                    # 保留原始类型或回退？暂时保留新值，让用户修正
                    # new_value = original_value # 或者可以选择回退
                    pass  # Keep new_value as is for now

                d[keys[-1]] = new_value
                print(f"配置已更新: {path} = {new_value}")
            else:
                print(f"警告: 尝试更新不存在的键: {path}")
        except KeyError:
            print(f"错误: 更新配置时找不到路径: {path}")
        except TypeError:
            print(f"错误: 尝试在非字典对象中更新键: {path}")
        except Exception as e:
            print(f"更新配置时发生未知错误 ({path}): {e}")

        # 注意：这里不需要调用 page.update()，因为这是内部数据更新
        # 调用保存按钮时，会使用更新后的 self.config_data

    def _create_boolean_control(self, key: str, value: bool, path: str, comment: str = "") -> ft.Control:
        """创建布尔值的开关控件。"""

        def on_change(e):
            self._update_config_value(path, e.control.value)

        switch = ft.Switch(label=key, value=value, on_change=on_change)

        # 如果有注释，添加一个Info图标
        if comment and len(comment) > 0:
            try:
                return ft.Row([switch, ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=comment, icon_size=16)])
            except Exception as e:
                print(f"创建布尔控件的注释图标时出错: {path}, {e}")

        return switch

    def _create_number_control(self, key: str, value: Union[int, float], path: str, comment: str = "") -> ft.Control:
        """创建数字输入控件。"""

        def on_change(e):
            try:
                # 尝试转换为原始类型
                if isinstance(value, int):
                    converted = int(e.control.value)
                else:
                    converted = float(e.control.value)
                self._update_config_value(path, converted)
            except (ValueError, TypeError):
                pass  # 忽略无效输入

        text_field = ft.TextField(
            label=key,
            value=str(value),
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9.-]"),
            on_change=on_change,
        )

        # 如果有注释，添加一个信息图标
        if comment and len(comment) > 0:
            try:
                return ft.Row([text_field, ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=comment, icon_size=16)])
            except Exception as e:
                print(f"创建数字控件的注释图标时出错: {path}, {e}")

        return text_field

    def _create_string_control(self, key: str, value: str, path: str, comment: str = "") -> ft.Control:
        """创建字符串输入控件。"""

        def on_change(e):
            self._update_config_value(path, e.control.value)

        # 若字符串较长，使用多行文本
        multiline = len(value) > 30 or "\n" in value

        text_field = ft.TextField(
            label=key,
            value=value,
            multiline=multiline,
            min_lines=1,
            max_lines=5 if multiline else 1,
            on_change=on_change,
        )

        # 如果有注释，添加一个Info图标
        if comment and len(comment) > 0:
            try:
                return ft.Row([text_field, ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=comment, icon_size=16)])
            except Exception as e:
                print(f"创建字符串控件的注释图标时出错: {path}, {e}")

        return text_field

    def _create_list_control(self, key: str, value: List[Any], path: str, comment: str = "") -> ft.Control:
        """创建列表控件。"""
        # 创建一个可编辑的列表控件
        # 首先创建一个Column存放列表项目和控制按钮
        title_row = ft.Row(
            [
                ft.Text(f"{key}:", weight=ft.FontWeight.BOLD),
            ]
        )

        # 如果有注释，添加一个Info图标
        if comment and len(comment) > 0:
            try:
                title_row.controls.append(ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=comment, icon_size=16))
            except Exception as e:
                print(f"创建列表控件的注释图标时出错: {path}, {e}")

        column = ft.Column([title_row])

        # 创建一个内部Column用于存放列表项
        items_column = ft.Column([], spacing=5, scroll=ft.ScrollMode.AUTO)

        # 创建添加新项目的函数
        def add_item(e=None, default_value=None, is_initial=False):
            # 确定新项目的类型（基于现有项目或默认为字符串）
            item_type = str
            if value and len(value) > 0:
                if isinstance(value[0], int):
                    item_type = int
                elif isinstance(value[0], float):
                    item_type = float
                elif isinstance(value[0], bool):
                    item_type = bool

            # 创建新项目的默认值
            if default_value is None:
                if item_type is int:
                    default_value = 0
                elif item_type is float:
                    default_value = 0.0
                elif item_type is bool:
                    default_value = False
                else:
                    default_value = ""

            # 创建当前索引
            index = len(items_column.controls)

            # 创建删除项目的函数
            def delete_item(e):
                # 删除此项目
                items_column.controls.remove(item_row)
                # 更新列表中的值
                update_list_value()
                # 确保UI更新
                items_column.update()
                # 更新整个表单
                column.update()

            # 创建项目控件（根据类型）
            if item_type is bool:
                item_control = ft.Switch(value=default_value)
            elif item_type in (int, float):
                item_control = ft.TextField(
                    value=str(default_value),
                    input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9.-]"),
                    width=200,
                )
            else:  # 字符串
                item_control = ft.TextField(value=default_value, width=200)

            # 添加控件的更改事件
            def on_item_change(e):
                # 获取新值
                new_val = e.control.value
                # 转换类型
                if item_type is int:
                    try:
                        new_val = int(new_val)
                    except ValueError:
                        new_val = 0
                elif item_type is float:
                    try:
                        new_val = float(new_val)
                    except ValueError:
                        new_val = 0.0
                elif item_type is bool:
                    new_val = bool(new_val)
                # 更新列表中的值
                update_list_value()

            # 添加更改事件
            if item_type is bool:
                item_control.on_change = on_item_change
            else:
                item_control.on_change = on_item_change

            # 创建行包含项目控件和删除按钮
            item_row = ft.Row(
                [ft.Text(f"[{index}]"), item_control, ft.IconButton(icon=ft.icons.DELETE, on_click=delete_item)],
                alignment=ft.MainAxisAlignment.START,
            )

            # 将行添加到列表中
            items_column.controls.append(item_row)

            # 只有在用户交互时更新UI，初始加载时不更新
            if not is_initial and e is not None:
                # 更新UI - 确保整个控件都更新
                try:
                    items_column.update()
                    column.update()
                except Exception as update_e:
                    print(f"更新列表控件时出错: {path}, {update_e}")

            return item_control

        # 创建更新列表值的函数
        def update_list_value():
            new_list = []
            for item_row in items_column.controls:
                if len(item_row.controls) < 2:
                    continue  # 跳过格式不正确的行

                item_control = item_row.controls[1]  # 获取TextField或Switch

                # 根据控件类型获取值
                if isinstance(item_control, ft.Switch):
                    new_list.append(item_control.value)
                elif isinstance(item_control, ft.TextField):
                    # 根据原始列表中的类型转换值
                    if value and len(value) > 0:
                        if isinstance(value[0], int):
                            try:
                                new_list.append(int(item_control.value))
                            except ValueError:
                                new_list.append(0)
                        elif isinstance(value[0], float):
                            try:
                                new_list.append(float(item_control.value))
                            except ValueError:
                                new_list.append(0.0)
                        else:
                            new_list.append(item_control.value)
                    else:
                        new_list.append(item_control.value)

            # 更新TOML配置
            try:
                self._update_config_value(path, new_list)
            except Exception as e:
                print(f"更新列表值时出错: {path}, {e}")

        # 添加现有项目，使用is_initial=True标记为初始化
        for item in value:
            add_item(default_value=item, is_initial=True)

        # 添加按钮行
        button_row = ft.Row(
            [ft.ElevatedButton("添加项目", icon=ft.icons.ADD, on_click=add_item)], alignment=ft.MainAxisAlignment.START
        )

        # 将组件添加到主Column
        column.controls.append(items_column)
        column.controls.append(button_row)

        # 将整个列表控件包装在一个Card中，让它看起来更独立
        # Card不支持padding参数，使用Container包裹
        return ft.Card(content=ft.Container(content=column, padding=10))

    def _create_set_control(self, key: str, value: set, path: str, comment: str = "") -> ft.Control:
        """创建集合控件。"""
        # 创建一个可编辑的列表控件
        # 首先创建一个Column存放列表项目和控制按钮
        title_row = ft.Row(
            [
                ft.Text(f"{key} (集合):", weight=ft.FontWeight.BOLD),
            ]
        )

        # 如果有注释，添加一个Info图标
        if comment and len(comment) > 0:
            try:
                title_row.controls.append(ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=comment, icon_size=16))
            except Exception as e:
                print(f"创建集合控件的注释图标时出错: {path}, {e}")

        column = ft.Column([title_row])

        # 创建一个内部Column用于存放集合项
        items_column = ft.Column([], spacing=5, scroll=ft.ScrollMode.AUTO)

        # 创建一个用于输入的文本框
        new_item_field = ft.TextField(label="添加新项目", hint_text="输入值后按Enter添加", width=300)

        # 创建一个列表存储当前集合值
        current_values = list(value)

        # 创建添加新项目的函数
        def add_item(e=None, item_value=None, is_initial=False):
            if e and hasattr(e, "control") and e.control == new_item_field:
                # 从文本框获取值
                item_value = new_item_field.value.strip()
                if not item_value:
                    return
                new_item_field.value = ""  # 清空输入框
                if not is_initial:  # 只有在用户交互时更新
                    try:
                        new_item_field.update()
                    except Exception as update_e:
                        print(f"更新文本框时出错: {path}, {update_e}")

            if item_value is None or item_value == "":
                return

            # 判断值的类型（假设集合中所有元素类型一致）
            item_type = str
            if current_values and len(current_values) > 0:
                if isinstance(current_values[0], int):
                    item_type = int
                elif isinstance(current_values[0], float):
                    item_type = float
                elif isinstance(current_values[0], bool):
                    item_type = bool

            # 转换类型
            if item_type is int:
                try:
                    item_value = int(item_value)
                except ValueError:
                    return  # 如果无法转换则忽略
            elif item_type is float:
                try:
                    item_value = float(item_value)
                except ValueError:
                    return  # 如果无法转换则忽略
            elif item_type is bool:
                if item_value.lower() in ("true", "yes", "1", "y"):
                    item_value = True
                elif item_value.lower() in ("false", "no", "0", "n"):
                    item_value = False
                else:
                    return  # 无效的布尔值

            # 检查是否已存在（集合特性）
            if item_value in current_values:
                return  # 如果已存在则忽略

            # 添加到当前值列表
            current_values.append(item_value)

            # 创建删除项目的函数
            def delete_item(e):
                # 删除此项目
                current_values.remove(item_value)
                items_column.controls.remove(item_row)
                # 更新集合中的值
                update_set_value()
                # 确保UI更新
                try:
                    items_column.update()
                    column.update()  # 更新整个表单
                except Exception as update_e:
                    print(f"更新集合UI时出错: {path}, {update_e}")

            # 创建行包含项目文本和删除按钮
            item_row = ft.Row(
                [ft.Text(str(item_value)), ft.IconButton(icon=ft.icons.DELETE, on_click=delete_item)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )

            # 将行添加到列表中
            items_column.controls.append(item_row)

            # 只有在用户交互时更新UI，初始加载时不更新
            if not is_initial and e is not None:
                # 更新UI
                try:
                    items_column.update()
                    column.update()  # 确保整个表单都更新
                except Exception as update_e:
                    print(f"更新集合UI时出错: {path}, {update_e}")

            # 更新集合值
            update_set_value()

        # 创建更新集合值的函数
        def update_set_value():
            # 从current_values创建一个新集合
            try:
                new_set = set(current_values)
                # 更新TOML配置
                self._update_config_value(path, new_set)
            except Exception as e:
                print(f"更新集合值时出错: {path}, {e}")

        # 添加键盘事件处理
        def on_key_press(e):
            if e.key == "Enter":
                add_item(e)

        new_item_field.on_submit = add_item

        # 添加现有项目，使用is_initial=True标记为初始化
        for item in value:
            add_item(item_value=item, is_initial=True)

        # 添加输入框
        input_row = ft.Row(
            [
                new_item_field,
                ft.IconButton(
                    icon=ft.icons.ADD, on_click=lambda e: add_item(e, item_value=new_item_field.value.strip())
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
        )

        # 将组件添加到主Column
        column.controls.append(items_column)
        column.controls.append(input_row)

        # 将整个集合控件包装在一个Card中，让它看起来更独立
        # Card不支持padding参数，使用Container包裹
        return ft.Card(content=ft.Container(content=column, padding=10))


def load_bot_config_template(app_state) -> Dict[str, Any]:
    """
    加载bot_config_template.toml文件作为参考。

    Returns:
        带有注释的TOML文档
    """
    template_path = Path(app_state.script_dir) / "template/bot_config_template.toml"
    if template_path.exists():
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return tomlkit.parse(f.read())  # 使用parse而不是load以保留注释
        except Exception as e:
            print(f"加载模板配置文件失败: {e}")
    return tomlkit.document()


def get_bot_config_path(app_state) -> Path:
    """
    获取配置文件路径
    """
    config_path = Path(app_state.script_dir) / "config/bot_config.toml"
    return config_path


def load_bot_config(app_state) -> Dict[str, Any]:
    """
    加载bot_config.toml文件

    如果文件不存在，会尝试从模板创建
    """
    config_path = get_bot_config_path(app_state)

    # 如果配置文件不存在，尝试从模板创建
    if not config_path.exists():
        template_config = load_bot_config_template(app_state)
        if template_config:
            print(f"配置文件不存在，尝试从模板创建: {config_path}")
            try:
                # 确保目录存在
                config_path.parent.mkdir(parents=True, exist_ok=True)
                # 保存模板内容到配置文件
                with open(config_path, "w", encoding="utf-8") as f:
                    tomlkit.dump(template_config, f)
                print(f"成功从模板创建配置文件: {config_path}")
                return template_config
            except Exception as e:
                print(f"从模板创建配置文件失败: {e}")
                return {}
        return {}

    # 加载配置文件
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return tomlkit.load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return {}


def create_toml_form(
    page: ft.Page,
    config_data: Dict[str, Any],
    container: ft.Column,
    template_filename: str = "bot_config_template.toml",
):
    """
    创建并构建TOML表单。

    Args:
        page: Flet Page 对象
        config_data: TOML配置数据
        container: 放置表单的父容器
        template_filename: 要使用的模板文件名
    Returns:
        创建的 TomlFormGenerator 实例
    """
    generator = TomlFormGenerator(page, config_data, container, template_filename)
    generator.build_form()
    return generator  # Return the generator instance
