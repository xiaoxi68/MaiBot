import flet as ft
import os
import sys
import subprocess
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .state import AppState  # Avoid circular import for type hinting


async def update_page_safe(page: Optional[ft.Page]):
    """Safely call page.update() if the page object is valid."""
    if page:
        try:
            await page.update()
        except Exception:
            # Reduce noise, perhaps only print if debug is enabled later
            # print(f"Error during safe page update: {e}")
            pass  # Silently ignore update errors, especially during shutdown


def show_snackbar(page: Optional[ft.Page], message: str, error: bool = False):
    """Helper function to display a SnackBar."""
    if not page:
        print(f"[Snackbar - No Page] {'Error' if error else 'Info'}: {message}")
        return
    try:
        page.snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor=ft.colors.ERROR if error else None,
            open=True,
        )
        page.update()
    except Exception as e:
        print(f"Error showing snackbar: {e}")


def run_script(script_path: str, page: Optional["ft.Page"], app_state: Optional["AppState"], is_python: bool = False):
    """Runs a script file (.bat or .py) in a new process/window."""
    if not app_state or not app_state.script_dir:
        print("[run_script] Error: AppState or script_dir not available.", flush=True)
        if page:
            show_snackbar(page, "错误：无法确定脚本目录", error=True)
        return

    # Construct the full path to the script
    full_script_path = os.path.join(app_state.script_dir, script_path)
    print(f"[run_script] Attempting to run: {full_script_path}", flush=True)

    try:
        if not os.path.exists(full_script_path):
            print(f"[run_script] Error: Script file not found: {full_script_path}", flush=True)
            if page:
                show_snackbar(page, f"错误：脚本文件未找到\\n{script_path}", error=True)
            return

        # --- Platform-specific execution --- #
        if sys.platform == "win32":
            if script_path.lower().endswith(".bat"):
                print("[run_script] Using 'start cmd /k' for .bat on Windows.", flush=True)
                # Use start cmd /k to keep the window open after script finishes
                subprocess.Popen(f'start cmd /k "{full_script_path}"', shell=True, cwd=app_state.script_dir)
            elif script_path.lower().endswith(".py"):
                print("[run_script] Using Python executable for .py on Windows.", flush=True)
                # Run Python script using the current interpreter in a new console window
                # Using sys.executable ensures the correct Python environment is used.
                # 'start' is a cmd command, so shell=True is needed.
                # We don't use /k here, the Python process itself will keep the window open if needed (e.g., input()).
                subprocess.Popen(
                    f'start "Running {script_path}" "{sys.executable}" "{full_script_path}"',
                    shell=True,
                    cwd=app_state.script_dir,
                )
            else:
                print(
                    f"[run_script] Attempting generic 'start' for unknown file type on Windows: {script_path}",
                    flush=True,
                )
                # Try generic start for other file types, might open associated program
                subprocess.Popen(f'start "{full_script_path}"', shell=True, cwd=app_state.script_dir)
        else:  # Linux/macOS
            if script_path.lower().endswith(".py"):
                print("[run_script] Using Python executable for .py on non-Windows.", flush=True)
                # On Unix-like systems, we typically need a terminal emulator to see output.
                # This example uses xterm, adjust if needed for other terminals (gnome-terminal, etc.)
                # The '-e' flag is common for executing a command.
                try:
                    subprocess.Popen(["xterm", "-e", sys.executable, full_script_path], cwd=app_state.script_dir)
                except FileNotFoundError:
                    print(
                        "[run_script] xterm not found. Trying to run Python directly (output might be lost).",
                        flush=True,
                    )
                    try:
                        subprocess.Popen([sys.executable, full_script_path], cwd=app_state.script_dir)
                    except Exception as e_direct:
                        print(f"[run_script] Error running Python script directly: {e_direct}", flush=True)
                        if page:
                            show_snackbar(page, f"运行脚本时出错: {e_direct}", error=True)
                        return
            elif os.access(full_script_path, os.X_OK):  # Check if it's executable
                print("[run_script] Running executable script directly on non-Windows.", flush=True)
                # Similar terminal issue might apply here if it's a console app
                try:
                    subprocess.Popen([full_script_path], cwd=app_state.script_dir)
                except Exception as e_exec:
                    print(f"[run_script] Error running executable script: {e_exec}", flush=True)
                    if page:
                        show_snackbar(page, f"运行脚本时出错: {e_exec}", error=True)
                    return
            else:
                print(
                    f"[run_script] Don't know how to run non-executable, non-python script on non-Windows: {script_path}",
                    flush=True,
                )
                if page:
                    show_snackbar(page, f"无法运行此类型的文件: {script_path}", error=True)
                return

        if page:
            show_snackbar(page, f"正在尝试运行脚本: {script_path}")

    except Exception as e:
        print(f"[run_script] Unexpected error running script '{script_path}': {e}", flush=True)
        if page:
            show_snackbar(page, f"运行脚本时发生意外错误: {e}", error=True)
