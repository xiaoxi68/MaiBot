import flet as ft
import os
import atexit
import psutil  # Keep for initial PID checks maybe, though state should handle it
# import asyncio # <--- 如果不再需要其他异步任务，可以考虑移除

# --- Import refactored modules --- #
from src.MaiGoi.state import AppState
from src.MaiGoi.process_manager import (
    start_bot_and_show_console,
    output_processor_loop,  # Needed for restarting on navigate
    cleanup_on_exit,
    handle_disconnect,
)
from src.MaiGoi.ui_views import (
    create_main_view,
    create_console_view,
    create_adapters_view,
    create_process_output_view,
)
from src.MaiGoi.config_manager import load_config

# --- Import the new settings view --- #
from src.MaiGoi.ui_settings_view import create_settings_view

# --- Global AppState instance --- #
# This holds all the state previously scattered as globals
app_state = AppState()

# --- File Picker Result Handler Placeholder ---
# We need a placeholder function or logic to handle the result here if needed
# For now, the result will be handled within the adapters view itself.
# def handle_file_picker_result(e: ft.FilePickerResultEvent):
#     print("File picker result in launcher (should be handled in view):", e.files)

# --- atexit Cleanup Registration --- #
# Register the cleanup function from the process manager module
# It needs access to the app_state
atexit.register(cleanup_on_exit, app_state)
print("[Main Script] atexit cleanup handler from process_manager registered.", flush=True)


# --- Routing Logic --- #
def route_change(route: ft.RouteChangeEvent):
    """Handles Flet route changes, creating and appending views."""
    page = route.page
    target_route = route.route

    # --- 移除异步显示弹窗的辅助函数 ---
    # async def show_python_path_dialog():
    #     ...

    # Clear existing views before adding new ones
    page.views.clear()

    # Always add the main view
    main_view = create_main_view(page, app_state)
    page.views.append(main_view)

    # --- Handle Specific Routes --- #
    if target_route == "/console":
        # 清理：移除之前添加的 is_python_dialog_opening 标志（如果愿意）
        # app_state.is_python_dialog_opening = False # 可选清理

        console_view = create_console_view(page, app_state)
        page.views.append(console_view)

        # --- 仅设置标志 ---
        print(f"[Route Change /console] Checking python_path: '{app_state.python_path}'")
        if not app_state.python_path:
            print("[Route Change /console] python_path is empty, setting flag.")
            app_state.needs_python_path_dialog = True
            # *** 不再在这里打开弹窗 ***

        # Check process status and potentially restart processor loop if needed
        is_running = app_state.bot_pid is not None and psutil.pid_exists(app_state.bot_pid)
        print(
            f"[Route Change /console] Checking status: PID={app_state.bot_pid}, is_running={is_running}, stop_event={app_state.stop_event.is_set()}",
            flush=True,
        )

        if is_running:
            print("[Route Change /console] Process is running.", flush=True)
            # If the processor loop was stopped (e.g., by navigating away or stop button),
            # but the process is still running, restart the loop.
            if app_state.stop_event.is_set():
                print("[Route Change /console] Stop event was set, clearing and restarting processor loop.", flush=True)
                app_state.stop_event.clear()
                # Make sure output_list_view is available before starting loop
                if not app_state.output_list_view:
                    print("[Route Change /console] Warning: output_list_view is None when restarting loop. Creating.")
                    app_state.output_list_view = ft.ListView(
                        expand=True, spacing=2, auto_scroll=app_state.is_auto_scroll_enabled, padding=5
                    )
                    console_view.controls[1].controls[0].content = app_state.output_list_view  # Update content in view

                page.run_task(output_processor_loop, page, app_state)
        else:
            print("[Route Change /console] Process is not running.", flush=True)
            # Ensure console view shows the 'not running' state if needed
            if app_state.output_list_view:
                # Check if already has the message? Might add duplicates.
                # Simple approach: just add it if the list is empty or last msg isn't it.
                add_not_running_msg = True
                if app_state.output_list_view.controls:
                    last_control = app_state.output_list_view.controls[-1]
                    # Check if it's Text and value is not None before checking content
                    if (
                        isinstance(last_control, ft.Text)
                        and last_control.value is not None
                        and "Bot 进程未运行" in last_control.value
                    ):
                        add_not_running_msg = False
                if add_not_running_msg:
                    app_state.output_list_view.controls.append(ft.Text("--- Bot 进程未运行 ---", italic=True))
            else:
                # If list view doesn't exist here, create it and add the message
                print("[Route Change /console] Creating ListView to show 'not running' message.")
                app_state.output_list_view = ft.ListView(
                    expand=True, spacing=2, auto_scroll=app_state.is_auto_scroll_enabled, padding=5
                )
                app_state.output_list_view.controls.append(ft.Text("--- Bot 进程未运行 ---", italic=True))
                # Update the console view container's content
                console_view.controls[1].controls[0].content = app_state.output_list_view
    elif target_route == "/adapters":
        adapters_view = create_adapters_view(page, app_state)
        page.views.append(adapters_view)
    elif target_route == "/settings":
        # Call the new settings view function
        settings_view = create_settings_view(page, app_state)
        page.views.append(settings_view)

    # --- Handle Dynamic Adapter Output Route --- #
    # Check if the route matches the pattern /adapters/<something>
    elif target_route.startswith("/adapters/") and len(target_route.split("/")) == 3:
        parts = target_route.split("/")
        process_id = parts[2]  # Extract the process ID (which is the script path for now)
        print(f"[Route Change] Detected adapter output route for ID: {process_id}")
        adapter_output_view = create_process_output_view(page, app_state, process_id)
        if adapter_output_view:
            page.views.append(adapter_output_view)
        else:
            # If view creation failed (e.g., process state not found), show error and stay on previous view?
            # Or redirect back to /adapters? Let's go back to adapters list.
            print(f"[Route Change] Failed to create output view for {process_id}. Redirecting to /adapters.")
            # Avoid infinite loop if /adapters also fails
            if len(page.views) > 1:  # Ensure we don't pop the main view
                page.views.pop()  # Pop the failed view attempt
            # Find the adapters view if it exists, otherwise just update
            adapters_view_index = -1
            for i, view in enumerate(page.views):
                if view.route == "/adapters":
                    adapters_view_index = i
                    break
            if adapters_view_index == -1:  # Adapters view wasn't in stack? Add it.
                adapters_view = create_adapters_view(page, app_state)
                page.views.append(adapters_view)
            # Go back to the adapters list route to rebuild the view stack correctly
            page.go("/adapters")
            return  # Prevent page.update() below

    # Update the page to show the correct view(s)
    page.update()


def view_pop(e: ft.ViewPopEvent):
    """Handles view popping (e.g., back navigation)."""
    page = e.page
    # Remove the top view
    page.views.pop()
    if page.views:
        top_view = page.views[-1]
        # Go to the route of the view now at the top of the stack
        # This will trigger route_change again to rebuild the view stack correctly
        page.go(top_view.route)
    # else: print("Warning: Popped the last view.")


# --- Main Application Setup --- #
def main(page: ft.Page):
    # Load initial config and store in state
    if os.path.exists("logs/interest/interest_history.log"):
        os.remove("logs/interest/interest_history.log")
    loaded_config = load_config()
    app_state.gui_config = loaded_config
    app_state.adapter_paths = loaded_config.get("adapters", []).copy()
    app_state.bot_script_path = loaded_config.get("bot_script_path", "bot.py")  # Load bot script path

    # 加载用户自定义的 Python 路径
    if "python_path" in loaded_config and os.path.exists(loaded_config["python_path"]):
        app_state.python_path = loaded_config["python_path"]
        print(f"[Main] 从配置加载 Python 路径: {app_state.python_path}")

    print(f"[Main] Initial adapters loaded: {app_state.adapter_paths}")

    # Set script_dir in AppState early
    app_state.script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"[Main] Script directory set in state: {app_state.script_dir}", flush=True)

    # --- Setup File Picker --- #
    # Create the FilePicker instance
    # The on_result handler will be set dynamically in the view that uses it
    app_state.file_picker = ft.FilePicker()
    # Add the FilePicker to the page's overlay controls
    page.overlay.append(app_state.file_picker)
    print("[Main] FilePicker created and added to page overlay.")

    page.title = "MaiBot 启动器"
    page.window.width = 1400
    page.window.height = 1000  # Increased height slightly for monitor
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # --- Apply Theme from Config --- #
    saved_theme = app_state.gui_config.get("theme", "System").upper()
    try:
        page.theme_mode = ft.ThemeMode[saved_theme]
        print(f"[Main] Applied theme from config: {page.theme_mode}")
    except KeyError:
        print(f"[Main] Warning: Invalid theme '{saved_theme}' in config. Falling back to System.")
        page.theme_mode = ft.ThemeMode.SYSTEM

    # --- 自定义主题颜色 --- #
    # 创建深色主题，使橙色变得更暗
    dark_theme = ft.Theme(
        color_scheme_seed=ft.colors.ORANGE,
        primary_color=ft.colors.ORANGE_700,  # 使用更暗的橙色
        color_scheme=ft.ColorScheme(
            primary=ft.colors.ORANGE_700,
            primary_container=ft.colors.ORANGE_800,
        ),
    )

    # 创建亮色主题
    light_theme = ft.Theme(
        color_scheme_seed=ft.colors.ORANGE,
    )

    # 设置自定义主题
    page.theme = light_theme
    page.dark_theme = dark_theme

    page.padding = 0  # <-- 将页面 padding 设置为 0

    # --- Create the main 'Start Bot' button and store in state --- #
    # This button needs to exist before the first route_change call
    app_state.start_bot_button = ft.FilledButton(
        "启动 MaiBot 主程序 (bot.py)",
        icon=ft.icons.SMART_TOY_OUTLINED,
        # The click handler now calls the function from process_manager
        on_click=lambda _: start_bot_and_show_console(page, app_state),
        expand=True,
        tooltip="启动主程序并在新视图中显示控制台输出",
    )
    print("[Main] Start Bot Button created and stored in state.", flush=True)

    # --- Routing Setup --- #
    page.on_route_change = route_change
    page.on_view_pop = view_pop

    # --- Disconnect Handler --- #
    # Pass app_state to the disconnect handler
    page.on_disconnect = lambda e: handle_disconnect(page, app_state, e)
    print("[Main] Registered page.on_disconnect handler.", flush=True)

    # Prevent immediate close to allow cleanup
    page.window_prevent_close = True

    # --- Hide Native Title Bar --- #
    # page.window_title_bar_hidden = True
    # page.window.frameless = True

    # --- Initial Navigation --- #
    # Trigger the initial route change to build the first view
    page.go(page.route if page.route else "/")


# --- Run Flet App --- #
if __name__ == "__main__":
    # No need to initialize globals here anymore, AppState handles it.
    ft.app(target=main)
    # This print will appear *after* the Flet window closes,
    # but *before* the atexit handler runs.
    print("[Main Script] Flet app exited. atexit handler should run next.", flush=True)

# --- Removed Code Sections (Previously Globals and Functions) ---
# (Keep this comment block or similar for reference if desired)
# Removed: bot_process, bot_pid, output_queue, stop_event, interest_monitor_control,
#          output_list_view, start_bot_button (now in AppState),
#          is_auto_scroll_enabled (now in AppState)
# Removed: ansi_converter
# Removed: cleanup_on_exit (moved to process_manager)
# Removed: update_page_safe (moved to utils)
# Removed: show_snackbar (moved to utils)
# Removed: run_script (moved to utils)
# Removed: handle_disconnect (moved to process_manager)
# Removed: stop_bot_process (moved to process_manager)
# Removed: read_process_output (moved to process_manager)
# Removed: output_processor_loop (moved to process_manager)
# Removed: start_bot_and_show_console (moved to process_manager)
# Removed: create_console_view (moved to ui_views)
# (Main view creation logic also moved to ui_views within create_main_view)
