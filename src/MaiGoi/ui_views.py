import flet as ft
from typing import Optional, TYPE_CHECKING
import psutil
import os
import sys

# Import components and state
from .flet_interest_monitor import InterestMonitorDisplay

if TYPE_CHECKING:
    from .state import AppState


# --- 添加资源路径处理函数 ---
def get_asset_path(relative_path: str) -> str:
    """
    获取资源文件的正确路径，在打包环境和源码环境下都能正常工作。

    Args:
        relative_path: 相对于项目根目录的资源路径，例如 "src/MaiGoi/assets/image.png"

    Returns:
        str: 资源文件的绝对路径
    """
    # 检查是否在打包环境中运行
    if getattr(sys, "frozen", False):
        # 打包环境
        # 获取应用程序所在目录
        base_dir = os.path.dirname(sys.executable)

        # 尝试多种可能的路径
        possible_paths = [
            # 1. 直接在根目录下
            os.path.join(base_dir, os.path.basename(relative_path)),
            # 2. 保持原始相对路径结构
            # os.path.join(base_dir, relative_path),
            # 3. 在 _internal 目录下保持原始路径结构
            os.path.join(base_dir, "_internal", relative_path),
            # 4. 从路径中去掉 "src/" 部分
            # os.path.join(base_dir, relative_path.replace("src/", "", 1)),
            # 5. 只使用最后的文件名
            # os.path.join(base_dir, os.path.basename(relative_path)),
        ]

        # 尝试所有可能的路径
        for path in possible_paths:
            if os.path.exists(path):
                print(f"[AssetPath] 打包环境: 找到资源 '{relative_path}' 位置: {path}")
                return path

        # 如果找不到任何匹配的路径，记录错误并返回原始路径
        print(f"[AssetPath] 警告: 在打包环境中找不到资源 '{relative_path}'")
        return os.path.join(base_dir, relative_path)  # 返回可能的路径，以便更容易识别错误
    else:
        # 源码环境，直接使用相对路径
        # 假设 cwd 是项目根目录
        root_dir = os.getcwd()
        path = os.path.join(root_dir, relative_path)

        # 验证路径是否存在
        if os.path.exists(path):
            return path
        else:
            print(f"[AssetPath] 警告: 在源码环境中找不到资源 '{relative_path}'")
            return relative_path  # 返回原始路径，方便调试


def create_main_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """Creates the main view ('/') of the application."""
    # --- Set Page Padding to Zero --- #
    page.padding = 0
    # page.update() # Update the page to apply the padding change - 移除这行，避免闪烁
    # ------------------------------ #

    # Get the main button from state (should be created in launcher.py main)
    start_button = app_state.start_bot_button
    if not start_button:
        print("[Main View] Error: start_bot_button not initialized in state! Creating placeholder.")
        start_button = ft.FilledButton("Error - Reload App")
        app_state.start_bot_button = start_button  # Store placeholder back just in case

    from .utils import run_script  # Dynamic import to avoid cycles

    # --- Card Styling --- #
    card_shadow = ft.BoxShadow(
        spread_radius=1,
        blur_radius=10,  # Slightly more blur for frosted effect
        color=ft.colors.with_opacity(0.2, ft.colors.BLACK87),
        offset=ft.Offset(1, 2),
    )
    # card_border = ft.border.all(1, ft.colors.with_opacity(0.5, ft.colors.SECONDARY)) # Optional: Remove border for cleaner glass look
    card_radius = ft.border_radius.all(4)  # Slightly softer edges for glass
    # card_bgcolor = ft.colors.with_opacity(0.05, ft.colors.BLUE_GREY_50) # Subtle background
    # Use a semi-transparent primary color for the frosted glass effect
    _card_bgcolor = ft.colors.with_opacity(0.65, ft.colors.PRIMARY_CONTAINER)  # Example: using theme container color

    # --- Card Creation Function --- #
    def create_action_card(
        page: ft.Page,
        icon: str,
        subtitle: str,
        text: str,
        on_click_handler,
        tooltip: str = None,
        width: int = 450,
        height: int = 150,
    ):
        # Removed icon parameter usage
        subtitle_text = subtitle
        # darker_bgcolor ='#ffffff' # Default Light mode background

        # --- Determine colors based on theme ---
        # is_dark = page.theme_mode == ft.ThemeMode.DARK
        # card_bgcolor_actual = ft.colors.BLACK if is_dark else '#ffffff' # Use BLACK for dark, white for light
        # main_text_color = ft.colors.GREY_200 if is_dark else ft.colors.BLACK # Light grey for dark, black for light
        # subtitle_color = ft.colors.GREY_500 if is_dark else ft.colors.with_opacity(0.7, ft.colors.GREY_500) # Darker grey for dark, lighter grey for light

        # --- Use Theme Colors Instead ---
        # Let Flet handle the color adaptation based on theme
        # card_bgcolor_theme = ft.colors.SURFACE_VARIANT # Or PRIMARY_CONTAINER, SURFACE etc.
        # main_text_color_theme = ft.colors.ON_SURFACE_VARIANT
        # subtitle_color_theme = ft.colors.with_opacity(0.8, ft.colors.ON_SURFACE_VARIANT) # Slightly transparent
        card_bgcolor_theme = ft.colors.SURFACE  # Use SURFACE for a generally whiter/lighter background
        main_text_color_theme = ft.colors.ON_SURFACE  # Corresponding text color
        subtitle_color_theme = ft.colors.with_opacity(0.7, ft.colors.ON_SURFACE)  # Slightly more transparent ON_SURFACE

        # --- 使用辅助函数获取Emoji图片路径 --- #
        emoji_image_path = get_asset_path("src/MaiGoi/assets/button_shape.png")  # 使用辅助函数获取正确路径

        # --- Create Text Content --- #
        text_content_column = ft.Column(
            [
                # --- Main Title Text ---
                ft.Container(
                    content=ft.Text(
                        text,
                        weight=ft.FontWeight.W_800,
                        size=50,
                        text_align=ft.TextAlign.LEFT,
                        font_family="SimSun",
                        # color=ft.colors.BLACK,
                        color=main_text_color_theme,  # Use theme color
                    ),
                    margin=ft.margin.only(top=-5),
                ),
                # --- Subtitle Text (Wrapped in Container for Margin) ---
                ft.Container(
                    content=ft.Text(
                        subtitle_text,
                        weight=ft.FontWeight.BOLD,
                        size=20,
                        # color=ft.colors.with_opacity(0.7, ft.colors.GREY_500),
                        color=subtitle_color_theme,  # Use theme color
                        text_align=ft.TextAlign.LEFT,
                        font_family="SimHei",
                    ),
                    margin=ft.margin.only(top=-20, left=10),
                ),
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

        # --- Create Emoji Image Layer --- #
        emoji_image_layer = ft.Container(
            content=ft.Image(
                src=emoji_image_path,
                fit=ft.ImageFit.COVER,  # <-- Change fit to COVER for zoom/fill effect
            ),
            alignment=ft.alignment.center,  # Center the image within the container
            # Position the container itself to overlap the right side
            right=-100,  # <-- Allow container to extend beyond the right edge slightly
            top=10,  # <-- Allow container to extend beyond the top edge slightly
            # bottom=5, # Remove bottom constraint
            width=300,  # <-- Increase width of the image container area
            height=300,  # <-- Give it a height too, slightly larger than card text area
            opacity=0.3,  # <-- Set back to semi-transparent
            # expand=True # Optionally expand if needed
            rotate=ft.transform.Rotate(angle=0.2),
            # transform=ft.transform.Scale(scale_x=-1), # <-- Remove transform from container
        )

        # --- Hover effect shadow --- #
        hover_shadow = ft.BoxShadow(
            spread_radius=2,
            blur_radius=15,  # Slightly more blur on hover
            color=ft.colors.with_opacity(0.3, ft.colors.BLACK87),  # Slightly darker shadow
            offset=ft.Offset(2, 4),
        )

        # --- on_hover handler --- #
        def handle_hover(e):
            if e.data == "true":  # Mouse enters
                e.control.scale = ft.transform.Scale(1.03)
                e.control.shadow = hover_shadow
            else:  # Mouse exits
                e.control.scale = ft.transform.Scale(1.0)
                e.control.shadow = card_shadow  # Restore original shadow
            e.control.update()

        return ft.Container(
            # Use Stack to layer text and image
            content=ft.Stack(
                [
                    # Layer 1: Text Content (aligned left implicitly by parent Row settings)
                    # Need to wrap the column in a Row again if we removed the original one,
                    # but let's try putting the column directly first if Stack handles alignment
                    # We need padding inside the stack for the text
                    ft.Container(
                        content=text_content_column,
                        padding=ft.padding.only(top=8, left=15, bottom=15, right=20),  # Apply padding here
                    ),
                    # Layer 2: Emoji Image
                    emoji_image_layer,
                ]
            ),
            height=height,
            width=width,
            border_radius=card_radius,
            # bgcolor=darker_bgcolor,
            bgcolor=card_bgcolor_theme,  # Use theme color
            # Padding is now applied to the inner container for text
            padding=0,
            margin=ft.margin.only(bottom=20),  # Margin applied outside the hover effect
            shadow=card_shadow,
            on_click=on_click_handler,
            tooltip=tooltip,
            ink=True,
            # rotate=ft.transform.Rotate(angle=0.1), # Remove rotate as it might conflict
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # Clip overflowing image within card bounds
            # rotate=ft.transform.Rotate(angle=0.1), # Apply rotation outside hover if needed
            scale=ft.transform.Scale(1.0),  # Initial scale
            animate_scale=ft.animation.Animation(200, "easeOutCubic"),  # Animate scale changes
            on_hover=handle_hover,  # Attach hover handler
        )

    # --- Main Button Action --- #
    # Need process_manager for the main button action
    start_bot_card = create_action_card(
        page=page,  # Pass page object
        icon=ft.icons.SMART_TOY_OUTLINED,
        text="主控室",
        subtitle="在此启动 Bot",
        on_click_handler=lambda _: page.go("/console"),
        tooltip="打开 Bot 控制台视图 (在此启动 Bot)",
    )
    # Note: We are not using app_state.start_bot_button directly here anymore
    # The button state update logic in process_manager might need adjustment
    # if we want this card's appearance to change (e.g., text to "返回控制台").
    # For now, it will always show "启动".

    # --- Define Popup Menu Items --- #
    menu_items = [
        # ft.PopupMenuItem(
        #     text="麦麦学习",
        #     on_click=lambda _: run_script("start_lpmm.bat", page, app_state),
        # ),
        ft.PopupMenuItem(
            text="人格生成（测试版）",
            on_click=lambda _: run_script("start_personality.bat", page, app_state),
        ),
        # Add more items here if needed in the future
    ]

    # --- Create "More..." Card Separately for Stack --- #
    # more_options_card = create_action_card(
    #     page=page,
    #     icon=ft.icons.MORE_HORIZ_OUTLINED,
    #     text="更多...",
    #     subtitle="其他工具",
    #     on_click_handler=None,  # 这里不设置点击动作，因为我们会覆盖内容
    #     tooltip="选择要运行的脚本",
    #     width=300,
    #     height=100,
    # )

    # 创建一个包含 more_options_card 和 PopupMenuButton 的 Stack
    more_options_card_stack = ft.Container(
        content=ft.Stack(
            [
                # more_options_card,  # 作为背景卡片
                # 将 PopupMenuButton 放在卡片上层
                ft.Container(
                    content=ft.PopupMenuButton(
                        items=menu_items,
                        icon=ft.icons.MORE_VERT,
                        icon_size=50,
                        icon_color=ft.colors.ORANGE,
                        tooltip="选择要运行的脚本",
                    ),
                    right=50,  # 右侧距离
                    top=20,  # 顶部距离
                ),
            ]
        ),
        height=150,  # 与普通卡片相同高度
        width=450,  # 与普通卡片相同宽度
        # 不需要设置 bgcolor 和 border_radius，因为 more_options_card 已包含这些样式
        rotate=ft.transform.Rotate(angle=0.12),  # 与其他卡片使用相同的旋转角度
    )

    # --- Main Column of Cards --- #
    main_cards_column = ft.Column(
        controls=[
            ft.Container(height=15),  # Top spacing
            # Wrap start_bot_card
            ft.Container(
                content=start_bot_card,
                margin=ft.margin.only(top=20, right=10),
                rotate=ft.transform.Rotate(angle=0.12),
            ),
            # --- Move Adapters Card Up --- #
            # Wrap Adapters card
            ft.Container(
                content=create_action_card(
                    page=page,  # Pass page object
                    icon=ft.icons.EXTENSION_OUTLINED,  # Example icon
                    text="适配器",
                    subtitle="管理适配器脚本",
                    on_click_handler=lambda _: page.go("/adapters"),
                    tooltip="管理和运行适配器脚本",
                ),
                margin=ft.margin.only(top=20, right=45),
                rotate=ft.transform.Rotate(angle=0.12),
            ),
            # Re-add the LPMM script card
            # Wrap LPMM card
            ft.Container(
                content=create_action_card(
                    page=page,  # Pass page object
                    icon=ft.icons.MODEL_TRAINING_OUTLINED,  # Icon is not used visually but kept for consistency maybe
                    text="学习",
                    subtitle="使用LPMM知识库",
                    on_click_handler=lambda _: run_script("start_lpmm.bat", page, app_state),
                    tooltip="运行学习脚本 (start_lpmm.bat)",
                ),
                margin=ft.margin.only(top=20, right=15),
                rotate=ft.transform.Rotate(angle=0.12),
            ),
            # more_options_card, # Add the new card with the popup menu (Moved to Stack)
            # --- Add Adapters and Settings Cards --- #
            # Wrap Settings card
            ft.Container(
                content=create_action_card(
                    page=page,  # Pass page object
                    icon=ft.icons.SETTINGS_OUTLINED,  # Example icon
                    text="设置",
                    subtitle="配置所有选项",
                    on_click_handler=lambda _: page.go("/settings"),
                    tooltip="配置启动器选项",
                ),
                margin=ft.margin.only(top=20, right=60),
                rotate=ft.transform.Rotate(angle=0.12),
            ),
        ],
        # alignment=ft.MainAxisAlignment.START, # Default vertical alignment is START
        horizontal_alignment=ft.CrossAxisAlignment.END,  # Align cards to the END (right)
        spacing=0,  # Let card margin handle spacing
        # expand=True, # Remove expand from the inner column if using Stack
    )

    return ft.View(
        "/",  # Main view route
        [
            ft.Stack(
                [
                    # --- Giant Orange Stripe (Background) --- #
                    ft.Container(
                        bgcolor=ft.colors.with_opacity(1, ft.colors.ORANGE_ACCENT_200),  # Orange with opacity
                        width=3000,  # Make it very wide
                        height=1000,  # Give it substantial height
                        rotate=ft.transform.Rotate(0.12),  # Apply rotation (adjust angle as needed)
                        # alignment=ft.alignment.center, # Center it in the stack
                        # Position it manually to better control placement with rotation
                        left=-200,
                        top=-500,
                        opacity=1,  # Overall opacity for the stripe
                    ),
                    ft.Container(
                        content=ft.Image(
                            src=get_asset_path("src/MaiGoi/assets/button_shape.png"),  # 使用辅助函数获取正确路径
                            fit=ft.ImageFit.CONTAIN,
                        ),
                        width=900,
                        height=1800,
                        left=35,  # 距离左侧
                        top=-420,  # 距离顶部
                        border_radius=ft.border_radius.all(10),
                        rotate=ft.transform.Rotate(-1.2),
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # Helps with rounded corners
                    ),
                    ft.Container(
                        bgcolor=ft.colors.with_opacity(1, ft.colors.ORANGE_ACCENT_200),  # Orange with opacity
                        width=1000,  # Make it very wide
                        height=1000,  # Give it substantial height
                        rotate=ft.transform.Rotate(0.12),  # Apply rotation (adjust angle as needed)
                        # alignment=ft.alignment.center, # Center it in the stack
                        # Position it manually to better control placement with rotation
                        left=280,
                        top=-561.6,
                        opacity=1,  # Overall opacity for the stripe
                    ),
                    # --- End Giant Orange Stripe ---
                    ft.Container(
                        bgcolor=ft.colors.with_opacity(1, ft.colors.PURPLE_200),  # Orange with opacity
                        width=800,  # Make it very wide
                        height=3000,  # Give it substantial height
                        rotate=ft.transform.Rotate(0.6),  # Apply rotation (adjust angle as needed)
                        # alignment=ft.alignment.center, # Center it in the stack
                        # Position it manually to better control placement with rotation
                        left=-500,
                        top=-1600,
                        opacity=1,  # Overall opacity for the stripe
                    ),
                    ft.Container(
                        content=main_cards_column,
                        top=20,  # 距离顶部
                        right=20,  # 距离右侧
                    ),
                    # --- End positioned Container ---
                    # "More..." card aligned bottom-right
                    ft.Container(
                        content=more_options_card_stack,
                        # 重新定位"更多..."按钮
                        right=10,  # 距离右侧
                        bottom=15,  # 距离底部
                    ),
                    # --- Add Large Text to Bottom Left ---
                    ft.Container(
                        content=ft.Text(
                            "MAI",
                            size=50,
                            font_family="Microsoft YaHei",
                            weight=ft.FontWeight.W_700,
                            color=ft.colors.with_opacity(1, ft.colors.WHITE10),
                        ),
                        left=32,
                        top=30,
                        rotate=ft.transform.Rotate(-0.98),
                    ),
                    ft.Container(
                        content=ft.Text(
                            "工具箱",
                            size=80,
                            font_family="Microsoft YaHei",  # 使用相同的锐利字体
                            weight=ft.FontWeight.W_700,  # 加粗
                            color=ft.colors.with_opacity(1, ft.colors.WHITE10),
                        ),
                        left=-10,
                        top=78,
                        rotate=ft.transform.Rotate(-0.98),
                    ),
                    # --- End Add Large Text ---
                ],
                expand=True,  # Make Stack fill the available space
            ),
        ],
        # padding=ft.padding.symmetric(horizontal=20), # <-- 移除水平 padding
        # scroll=ft.ScrollMode.ADAPTIVE,  # Allow scrolling if content overflows
    )


def create_console_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """Creates the console output view ('/console'), including the interest monitor."""
    # Get UI elements from state
    output_list_view = app_state.output_list_view
    from .process_manager import update_buttons_state  # Dynamic import

    # 默认开启自动滚动
    app_state.is_auto_scroll_enabled = True

    # Create ListView if it doesn't exist (as a fallback, should be created by start_bot)
    if not output_list_view:
        output_list_view = ft.ListView(expand=True, spacing=2, auto_scroll=app_state.is_auto_scroll_enabled, padding=5)
        app_state.output_list_view = output_list_view  # Store back to state
        print("[Create Console View] Fallback: Created ListView.")

    # --- Create or get InterestMonitorDisplay instance --- #
    # Ensure the same instance is used if the view is recreated
    if app_state.interest_monitor_control is None:
        print("[Create Console View] Creating InterestMonitorDisplay instance")
        app_state.interest_monitor_control = InterestMonitorDisplay()  # Store in state
    else:
        print("[Create Console View] Using existing InterestMonitorDisplay instance from state")
        # Optional: Trigger reactivation if needed
        # asyncio.create_task(app_state.interest_monitor_control.start_updates_if_needed())

    interest_monitor = app_state.interest_monitor_control

    # --- 为控制台输出和兴趣监控创建容器，以便动态调整大小 --- #
    output_container = ft.Container(
        content=output_list_view,
        expand=4,  # 在左侧 Column 内部分配比例
        border=ft.border.only(bottom=ft.border.BorderSide(1, ft.colors.OUTLINE)),
    )

    monitor_container = ft.Container(
        content=interest_monitor,
        expand=4,  # 在左侧 Column 内部分配比例
    )

    # --- 设置兴趣监控的切换回调函数 --- #
    def on_monitor_toggle(is_expanded):
        if is_expanded:
            # 监控器展开时，恢复原比例
            output_container.expand = 4
            monitor_container.expand = 4
        else:
            # 监控器隐藏时，让输出区占据更多空间
            output_container.expand = 9
            monitor_container.expand = 0

        # 更新容器以应用新布局
        output_container.update()
        monitor_container.update()

    # 为监控器设置回调函数
    interest_monitor.on_toggle = on_monitor_toggle

    # --- Auto-scroll toggle button callback (remains separate) --- #
    def toggle_auto_scroll(e):
        app_state.is_auto_scroll_enabled = not app_state.is_auto_scroll_enabled
        lv = app_state.output_list_view  # Get potentially updated list view
        if lv:
            lv.auto_scroll = app_state.is_auto_scroll_enabled

            # 当关闭自动滚动时，记录当前滚动位置
            if not app_state.is_auto_scroll_enabled:
                # 标记视图正在手动观看模式，以便在更新时保持位置
                app_state.manual_viewing = True
            else:
                # 开启自动滚动时，关闭手动观看模式
                app_state.manual_viewing = False

        # Update button appearance (assuming button reference is available)
        # e.control is the Container now
        # We need to update the Text control stored in its data attribute
        text_control = e.control.data if isinstance(e.control.data, ft.Text) else None
        if text_control:
            text_control.value = "自动滚动 开" if app_state.is_auto_scroll_enabled else "自动滚动 关"
        else:
            print("[toggle_auto_scroll] Warning: Could not find Text control in button data.")
        # The icon and tooltip are on the Container itself (though tooltip might be better on Text?)
        # e.control.icon = ft.icons.PLAY_ARROW if app_state.is_auto_scroll_enabled else ft.icons.PAUSE # Icon removed
        e.control.tooltip = "切换控制台自动滚动"  # Tooltip remains useful
        print(f"Auto-scroll {'enabled' if app_state.is_auto_scroll_enabled else 'disabled'}.", flush=True)
        # Update the container to reflect text changes
        # page.run_task(update_page_safe, page) # This updates the whole page
        e.control.update()  # Try updating only the container first

    # --- Card Styling (Copied from create_main_view for reuse) --- #
    card_shadow = ft.BoxShadow(
        spread_radius=1,
        blur_radius=10,
        color=ft.colors.with_opacity(0.2, ft.colors.BLACK87),
        offset=ft.Offset(1, 2),
    )
    card_radius = ft.border_radius.all(4)
    card_bgcolor = ft.colors.with_opacity(0.65, ft.colors.PRIMARY_CONTAINER)
    card_padding = ft.padding.symmetric(vertical=8, horizontal=12)  # Smaller padding for console buttons

    # --- Create Buttons --- #
    # Create the main action button (Start/Stop) as a styled Container
    console_action_button_text = ft.Text("...")  # Placeholder text, updated by update_buttons_state
    console_action_button = ft.Container(
        content=console_action_button_text,
        bgcolor=card_bgcolor,  # Apply style
        border_radius=card_radius,
        shadow=card_shadow,
        padding=card_padding,
        ink=True,
        # on_click is set by update_buttons_state
    )
    app_state.console_action_button = console_action_button  # Store container ref

    # Create the auto-scroll toggle button as a styled Container with Text
    auto_scroll_text_content = "自动滚动 开" if app_state.is_auto_scroll_enabled else "自动滚动 关"
    auto_scroll_text = ft.Text(auto_scroll_text_content, size=12)
    toggle_button = ft.Container(
        content=auto_scroll_text,
        tooltip="切换控制台自动滚动",
        on_click=toggle_auto_scroll,  # Attach click handler here
        bgcolor=card_bgcolor,  # Apply style
        border_radius=card_radius,
        shadow=card_shadow,
        padding=card_padding,
        ink=True,
        # Remove left margin
        margin=ft.margin.only(right=10),
    )
    # Store the text control inside the toggle button container for updating
    toggle_button.data = auto_scroll_text  # Store Text reference in data attribute

    # --- 附加信息区 Column (在 View 级别创建) ---
    info_top_section = ft.Column(
        controls=[
            ft.Text("附加信息 - 上", weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("..."),  # 上半部分占位符
        ],
        expand=True,  # 让上半部分填充可用垂直空间
        scroll=ft.ScrollMode.ADAPTIVE,
    )
    info_bottom_section = ft.Column(
        controls=[
            ft.Text("附加信息 - 下", weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("..."),  # 下半部分占位符
            # 将按钮放在底部
            # Wrap the Row in a Container to apply padding
            ft.Container(
                content=ft.Row(
                    [console_action_button, toggle_button],
                    # alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    alignment=ft.MainAxisAlignment.START,  # Align buttons to the start
                ),
                # Apply padding to the container holding the row
                padding=ft.padding.only(bottom=10),
            ),
        ],
        # height=100, # 可以给下半部分固定高度，或者让它自适应
        spacing=5,
        # Remove padding from the Column itself
        # padding=ft.padding.only(bottom=10)
    )
    info_column = ft.Column(
        controls=[
            # ft.Text("附加信息区", weight=ft.FontWeight.BOLD),
            # ft.Divider(),
            info_top_section,
            info_bottom_section,
        ],
        width=250,  # 增加宽度
        # scroll=ft.ScrollMode.ADAPTIVE, # 内部分区滚动，外部不需要
        spacing=10,  # 分区之间的间距
    )

    # --- Set Initial Button State --- #
    # Call the helper AFTER the button is created and stored in state
    is_initially_running = app_state.bot_pid is not None and psutil.pid_exists(app_state.bot_pid)
    update_buttons_state(page, app_state, is_running=is_initially_running)

    # --- 视图布局 --- #
    return ft.View(
        "/console",  # View route
        [
            ft.AppBar(title=ft.Text("Mai控制台")),
            # --- 主要内容区域改为 Row --- #
            ft.Row(
                controls=[
                    # --- 左侧 Column (可扩展) --- #
                    ft.Column(
                        controls=[
                            # 1. Console Output Area
                            output_container,  # 使用容器替代直接引用
                            # 2. Interest Monitor Area
                            monitor_container,  # 使用容器替代直接引用
                        ],
                        expand=True,  # 让左侧 Column 占据 Row 的大部分空间
                    ),
                    # --- 右侧 Column (固定宽度) --- #
                    info_column,
                ],
                expand=True,  # 让 Row 填满 AppBar 下方的空间
            ),
        ],
        padding=0,  # View padding set to 0
        # Flet automatically handles calling will_unmount on UserControls like InterestMonitorDisplay
        # when the view is removed or the app closes.
        # on_disappear=lambda _: asyncio.create_task(interest_monitor.will_unmount_async()) if interest_monitor else None
    )


# --- Adapters View --- #
def create_adapters_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """Creates the view for managing adapters (/adapters)."""
    # Import necessary functions
    from .config_manager import save_config
    from .utils import show_snackbar  # Removed run_script import

    # Import process management functions
    from .process_manager import start_managed_process, stop_managed_process
    import psutil  # To check if PID exists for status

    adapters_list_view = ft.ListView(expand=True, spacing=5)

    def update_adapters_list():
        """Refreshes the list view with current adapter paths and status-dependent buttons."""
        adapters_list_view.controls.clear()
        for index, path in enumerate(app_state.adapter_paths):
            process_id = path  # Use path as the unique ID for now
            process_state = app_state.managed_processes.get(process_id)
            is_running = False
            if (
                process_state
                and process_state.status == "running"
                and process_state.pid
                and psutil.pid_exists(process_state.pid)
            ):
                is_running = True

            action_buttons = []
            if is_running:
                # If running: View Output Button and Stop Button
                action_buttons.append(
                    ft.IconButton(
                        ft.icons.VISIBILITY_OUTLINED,
                        tooltip="查看输出",
                        data=process_id,
                        on_click=lambda e: page.go(f"/adapters/{e.control.data}"),
                        icon_color=ft.colors.BLUE_GREY,  # Neutral color
                    )
                )
                action_buttons.append(
                    ft.IconButton(
                        ft.icons.STOP_CIRCLE_OUTLINED,
                        tooltip="停止此适配器",
                        data=process_id,
                        # Call stop and then refresh the list view
                        on_click=lambda e: (
                            stop_managed_process(e.control.data, page, app_state),
                            update_adapters_list(),
                        ),
                        icon_color=ft.colors.RED_ACCENT,
                    )
                )
            else:
                # If stopped: Start Button
                action_buttons.append(
                    ft.IconButton(
                        ft.icons.PLAY_ARROW_OUTLINED,
                        tooltip="启动此适配器脚本",
                        data=path,
                        on_click=lambda e: start_adapter_process(e, page, app_state),
                        icon_color=ft.colors.GREEN,
                    )
                )

            adapters_list_view.controls.append(
                ft.Row(
                    [
                        ft.Text(path, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                        # Add action buttons based on state
                        *action_buttons,
                        # Keep the remove button
                        ft.IconButton(
                            ft.icons.DELETE_OUTLINE,
                            tooltip="移除此适配器",
                            data=index,  # Store index to know which one to remove
                            on_click=remove_adapter,
                            icon_color=ft.colors.ERROR,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )
        # Trigger update if the list view is part of the page
        if adapters_list_view.page:
            adapters_list_view.update()

    def remove_adapter(e):
        """Removes an adapter path based on the button's data (index)."""
        index_to_remove = e.control.data
        if 0 <= index_to_remove < len(app_state.adapter_paths):
            removed_path = app_state.adapter_paths.pop(index_to_remove)
            app_state.gui_config["adapters"] = app_state.adapter_paths
            if save_config(app_state.gui_config):
                update_adapters_list()
                show_snackbar(page, f"已移除: {removed_path}")
            else:
                show_snackbar(page, "保存配置失败，未能移除", error=True)
                # Revert state
                app_state.adapter_paths.insert(index_to_remove, removed_path)
                app_state.gui_config["adapters"] = app_state.adapter_paths
        else:
            show_snackbar(page, "移除时发生错误：无效索引", error=True)

    # --- Start Adapter Process Handler --- #
    def start_adapter_process(e, page: ft.Page, app_state: "AppState"):
        """Handles the click event for the start adapter button."""
        path_to_run = e.control.data
        if not path_to_run or not isinstance(path_to_run, str):
            show_snackbar(page, "运行错误：无效的适配器路径", error=True)
            return

        display_name = os.path.basename(path_to_run)  # Use filename as display name
        process_id = path_to_run  # Use path as ID
        print(f"[Adapters View] Requesting start for: {display_name} (ID: {process_id})")

        # Call the generic start function from process_manager
        # It will create the specific ListView in the state
        success, message = start_managed_process(
            script_path=path_to_run,
            display_name=display_name,
            page=page,
            app_state=app_state,
            # No target_list_view needed here, it creates its own
        )

        if success:
            show_snackbar(page, f"正在启动: {display_name}")
            update_adapters_list()  # Refresh button states
            # Navigate to the specific output view for this process
            page.go(f"/adapters/{process_id}")
        else:
            # Error message already shown by start_managed_process via snackbar
            update_adapters_list()  # Refresh button states even on failure

    # --- Initial population of the list --- #
    update_adapters_list()

    new_adapter_path_field = ft.TextField(label="新适配器路径 (.py 文件)", expand=True)

    # --- File Picker Logic --- #
    def pick_adapter_file_result(e: ft.FilePickerResultEvent):
        """Callback when the file picker dialog closes."""
        if e.files:
            selected_file = e.files[0]  # Get the first selected file
            new_adapter_path_field.value = selected_file.path
            new_adapter_path_field.update()
            show_snackbar(page, f"已选择文件: {os.path.basename(selected_file.path)}")
        else:
            show_snackbar(page, "未选择文件")

    def open_file_picker(e):
        """Opens the file picker dialog."""
        if app_state.file_picker:
            app_state.file_picker.on_result = pick_adapter_file_result
            app_state.file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["py"],  # Only allow Python files
                dialog_title="选择适配器 Python 文件",
            )
        else:
            show_snackbar(page, "错误：无法打开文件选择器", error=True)

    # Ensure the file picker's on_result is connected when the view is created
    if app_state.file_picker:
        app_state.file_picker.on_result = pick_adapter_file_result
    else:
        # This case shouldn't happen if launcher.py runs correctly
        print("[create_adapters_view] Warning: FilePicker not available during view creation.")

    def add_adapter(e):
        """Adds a new adapter path to the list and config."""
        new_path = new_adapter_path_field.value.strip()

        if not new_path:
            show_snackbar(page, "请输入适配器路径", error=True)
            return
        # Basic validation (you might want more robust checks)
        if not new_path.lower().endswith(".py"):
            show_snackbar(page, "路径应指向一个 Python (.py) 文件", error=True)
            return
        # Optional: Check if the file actually exists? Might be too strict.
        # if not os.path.exists(new_path):
        #     show_snackbar(page, f"文件未找到: {new_path}", error=True)
        #     return

        if new_path in app_state.adapter_paths:
            show_snackbar(page, "此适配器路径已存在")
            return

        app_state.adapter_paths.append(new_path)
        app_state.gui_config["adapters"] = app_state.adapter_paths

        save_successful = save_config(app_state.gui_config)

        if save_successful:
            new_adapter_path_field.value = ""  # Clear input field
            update_adapters_list()  # Update the list view
            new_adapter_path_field.update()  # Update the input field visually
            show_snackbar(page, "适配器已添加")
        else:
            show_snackbar(page, "保存配置失败", error=True)
            # Revert state if save failed
            try:  # Add try-except just in case pop fails unexpectedly
                app_state.adapter_paths.pop()
                app_state.gui_config["adapters"] = app_state.adapter_paths
            except IndexError:
                pass  # Silently ignore if list was empty during failed save

    return ft.View(
        "/adapters",
        [
            ft.AppBar(title=ft.Text("适配器管理"), bgcolor=ft.colors.SURFACE_VARIANT),
            # Use a Container with the padding property instead
            ft.Container(
                padding=ft.padding.all(10),  # Set padding property on the Container
                content=ft.Column(  # Place the original content inside the Container
                    [
                        ft.Text("已配置的适配器:"),
                        adapters_list_view,  # ListView for adapters
                        ft.Divider(),
                        ft.Row(
                            [
                                new_adapter_path_field,
                                # --- Add Browse Button --- #
                                ft.IconButton(
                                    ft.icons.FOLDER_OPEN_OUTLINED,
                                    tooltip="浏览文件...",
                                    on_click=open_file_picker,  # Call the file picker opener
                                ),
                                ft.IconButton(ft.icons.ADD_CIRCLE_OUTLINE, tooltip="添加适配器", on_click=add_adapter),
                            ]
                        ),
                    ],
                    expand=True,
                ),
            ),
        ],
    )


# --- Settings View --- #
def create_settings_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """Placeholder for settings view."""
    # This function is now implemented in ui_settings_view.py
    # This placeholder can be removed if no longer referenced anywhere else.
    # For safety, let's keep it but make it clear it's deprecated/moved.
    print("Warning: Deprecated create_settings_view called in ui_views.py. Should use ui_settings_view.py version.")
    return ft.View(
        "/settings_deprecated",
        [ft.AppBar(title=ft.Text("Settings (Deprecated)")), ft.Text("This view has moved to ui_settings_view.py")],
    )


# --- Process Output View (for Adapters etc.) --- #
def create_process_output_view(page: ft.Page, app_state: "AppState", process_id: str) -> Optional[ft.View]:
    """Creates a view to display the output of a specific managed process."""
    # Import stop function
    from .process_manager import stop_managed_process

    process_state = app_state.managed_processes.get(process_id)

    if not process_state:
        print(f"[Create Output View] Error: Process state not found for ID: {process_id}")
        # Optionally show an error view or navigate back
        # For now, return None, route_change might handle this
        return None

    # Get or create the ListView for this process
    # It should have been created and stored by start_managed_process
    if process_state.output_list_view is None:
        print(f"[Create Output View] Warning: ListView not found in state for {process_id}. Creating fallback.")
        # Create a fallback, though this indicates an issue elsewhere
        process_state.output_list_view = ft.ListView(expand=True, spacing=2, padding=5, auto_scroll=True)
        process_state.output_list_view.controls.append(
            ft.Text(
                "--- Error: Output view created unexpectedly. Process might need restart. ---",
                italic=True,
                color=ft.colors.ERROR,
            )
        )

    output_lv = process_state.output_list_view

    # --- Stop Button --- #
    stop_button = ft.ElevatedButton(
        "停止进程",
        icon=ft.icons.STOP_CIRCLE_OUTLINED,
        on_click=lambda _: stop_managed_process(process_id, page, app_state),
        bgcolor=ft.colors.with_opacity(0.6, ft.colors.RED_ACCENT_100),
        color=ft.colors.WHITE,
        tooltip=f"停止 {process_state.display_name}",
    )

    # --- Auto-scroll Toggle (Specific to this view) --- #
    # Create a local state for this view's scroll toggle
    is_this_view_auto_scroll = ft.Ref[bool]()
    is_this_view_auto_scroll.current = True  # Default to true
    output_lv.auto_scroll = is_this_view_auto_scroll.current

    def toggle_this_view_auto_scroll(e):
        is_this_view_auto_scroll.current = not is_this_view_auto_scroll.current
        output_lv.auto_scroll = is_this_view_auto_scroll.current
        e.control.text = "自动滚动 开" if is_this_view_auto_scroll.current else "自动滚动 关"
        e.control.update()
        print(f"Process '{process_id}' view auto-scroll set to: {is_this_view_auto_scroll.current}")

    auto_scroll_button = ft.OutlinedButton(
        "自动滚动 开" if is_this_view_auto_scroll.current else "自动滚动 关",
        # icon=ft.icons.SCROLLING,
        icon=ft.icons.SWAP_VERT,  # Use a valid icon for toggling
        on_click=toggle_this_view_auto_scroll,
        tooltip="切换此视图的自动滚动",
    )

    return ft.View(
        route=f"/adapters/{process_id}",  # Dynamic route
        appbar=ft.AppBar(
            title=ft.Text(f"输出: {process_state.display_name}"),
            bgcolor=ft.colors.SURFACE_VARIANT,
            actions=[
                stop_button,
                auto_scroll_button,
                ft.Container(width=5),  # Spacer
            ],
        ),
        controls=[
            output_lv  # Display the specific ListView for this process
        ],
        padding=0,
    )
