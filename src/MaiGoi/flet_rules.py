"""
Flet UI开发的规则和最佳实践

这个文件记录了在使用Flet开发UI界面时发现的重要规则和最佳实践，
可以帮助避免常见错误并提高代码质量。
"""

# ===== Container相关规则 =====

"""
规则1: Container没有controls属性
Container只有content属性，不能直接访问controls。必须通过container.content访问内容。

错误示例:
container.controls.append(...)  # 错误! Container没有controls属性

正确示例:
container.content = ft.Column([])  # 先设置content为一个有controls属性的控件
container.content.controls.append(...)  # 然后通过content访问controls
"""

"""
规则2: Card没有padding属性
Card控件不直接支持padding，必须用Container包装来添加padding。

错误示例:
ft.Card(padding=10, content=...)  # 错误! Card没有padding属性

正确示例:
ft.Card(
    content=ft.Container(
        content=...,
        padding=10
    )
)
"""

# ===== UI更新规则 =====

"""
规则3: 控件必须先添加到页面才能调用update()
调用控件的update()方法前，确保该控件已经添加到页面中，否则会报错。

错误示例:
new_column = ft.Column([])
new_column.update()  # 错误! 控件还未添加到页面

正确示例:
# 区分初始加载和用户交互
def add_item(e=None, is_initial=False):
    # 创建新控件...
    items_column.controls.append(new_control)
    
    # 只在用户交互时更新UI
    if not is_initial and e is not None:
        items_column.update()
"""

"""
规则4: 嵌套结构展开/折叠时的更新策略
处理嵌套数据结构(如字典)的展开/折叠时，要小心控制update()的调用时机。

最佳实践:
1. 在生成UI结构时不要调用update()
2. 在用户交互(如点击展开按钮)后再调用update()
3. 始终从父容器调用update()，而不是每个子控件都调用
4. 添加异常处理，防止动态生成控件时的错误导致整个UI崩溃
"""

# ===== 数据类型处理规则 =====

"""
规则5: 特殊处理集合类型(set)
Python中的set类型在UI表示时需要特殊处理，将其转换为可编辑的表单控件。

最佳实践:
1. 为set类型实现专门的UI控件(如_create_set_control)
2. 添加错误处理，即使创建控件失败也要提供备选显示方式
3. 小心处理类型转换，确保UI中的数据变更能正确应用到set类型

示例:
if isinstance(value, set):
    try:
        return create_set_control(value)
    except Exception:
        return ft.Text(f"{value} (不可编辑)", italic=True)
"""

"""
规则6: 动态UI组件的初始化与更新分离
创建动态UI组件时，将初始化和更新逻辑分开处理。

最佳实践:
1. 初始化时只创建控件，不调用update()
2. 使用标志(如is_initial)区分初始加载和用户交互
3. 只在用户交互时调用update()
4. 更新数据模型和更新UI分开处理

示例:
# 添加现有项目，使用is_initial=True标记为初始化
for item in values:
    add_item(item, is_initial=True)
    
# 用户添加新项目时，不使用is_initial参数
add_button.on_click = lambda e: add_item(new_value)
"""

# ===== 其他实用规则 =====

"""
规则7: 始终使用正确的padding格式
Flet中padding必须使用正确的格式，不能直接传入数字。

错误示例:
ft.Padding(padding=10, content=...)  # 错误

正确示例:
ft.Padding(padding=ft.padding.all(10), content=...)
ft.Container(padding=ft.padding.all(10), content=...)
"""

"""
规则8: 控件引用路径注意层级关系
访问嵌套控件时注意层级关系，特别是当使用Container包装其他控件时。

错误示例:
# 如果card的内容是Container且Container的内容是Column
button = card.controls[-1]  # 错误! Card没有controls属性

正确示例:
# 正确的访问路径
button = card.content.content.controls[-1]
"""

# ===== 自定义控件规则 (Flet v0.21.0+) =====

"""
规则9: 弃用 UserControl，直接继承基础控件
Flet v0.21.0 及更高版本已弃用 `ft.UserControl`。
创建自定义控件时，应直接继承自 Flet 的基础控件，如 `ft.Column`, `ft.Row`, `ft.Card`, `ft.Text` 等。

修改步骤:
1. 更改类定义: `class MyControl(ft.Column):` 替换 `class MyControl(ft.UserControl):`
2. 将 `build()` 方法中的 UI 构建逻辑移至 `__init__` 方法。
3. 在 `__init__` 中调用 `super().__init__(...)` 并传递基础控件所需的参数。
4. 在 `__init__` 中直接将子控件添加到 `self.controls`。
5. 移除 `build()` 方法。

错误示例 (已弃用):
class OldCustom(ft.UserControl):
    def build(self):
        return ft.Text("Old way")

正确示例 (继承 ft.Column):
class NewCustom(ft.Column):
    def __init__(self):
        super().__init__(spacing=5)
        self.controls.append(ft.Text("New way"))
"""
