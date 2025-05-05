import flet as ft
import subprocess
import queue
import threading
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

# 从 flet_interest_monitor 导入，如果需要类型提示
from .flet_interest_monitor import InterestMonitorDisplay


@dataclass
class ManagedProcessState:
    """Holds the state for a single managed background process."""

    process_id: str  # Unique identifier (e.g., script path or UUID)
    script_path: str
    display_name: str
    process_handle: Optional[subprocess.Popen] = None
    pid: Optional[int] = None
    output_queue: queue.Queue = field(default_factory=queue.Queue)
    stop_event: threading.Event = field(default_factory=threading.Event)
    status: str = "stopped"  # e.g., "running", "stopped", "error"
    # Store UI references if needed later, e.g., for dedicated output views
    # output_view_controls: Optional[List[ft.Control]] = None
    output_list_view: Optional[ft.ListView] = None  # Added to hold the specific ListView for this process


class AppState:
    """Holds the shared state of the launcher application."""

    def __init__(self):
        # Process related state
        self.bot_process: Optional[subprocess.Popen] = None
        self.bot_pid: Optional[int] = None
        self.output_queue: queue.Queue = queue.Queue()
        self.stop_event: threading.Event = threading.Event()

        # UI related state
        self.output_list_view: Optional[ft.ListView] = None
        self.start_bot_button: Optional[ft.FilledButton] = None
        self.console_action_button: Optional[ft.ElevatedButton] = None
        self.is_auto_scroll_enabled: bool = True  # 默认启用自动滚动
        self.manual_viewing: bool = False  # 手动观看模式标识，用于修复自动滚动关闭时的位移问题
        self.interest_monitor_control: Optional[InterestMonitorDisplay] = None

        # Script directory (useful for paths)
        self.script_dir: str = ""  # Will be set during initialization in launcher.py

        # --- Configuration State --- #
        self.gui_config: Dict[str, Any] = {}  # Loaded from gui_config.toml
        self.adapter_paths: List[str] = []  # Specific list of adapter paths from config

        # --- Process Management State (NEW - For multi-process support) --- #
        self.managed_processes: Dict[str, ManagedProcessState] = {}

    def reset_process_state(self):
        """Resets variables related to the bot process."""
        print("[AppState] Resetting process state.", flush=True)
        self.bot_process = None
        self.bot_pid = None
        # Clear the queue? Maybe not, might lose messages if reset mid-operation
        # while not self.output_queue.empty():
        #     try: self.output_queue.get_nowait()
        #     except queue.Empty: break
        self.stop_event.clear()  # Ensure stop event is cleared

        # --- Reset corresponding NEW state (if exists) ---
        process_id = "bot.py"
        if process_id in self.managed_processes:
            # Ensure the managed state reflects the reset event/queue
            # (Since they point to the same objects for now, this is redundant but good practice)
            self.managed_processes[process_id].stop_event = self.stop_event
            self.managed_processes[process_id].output_queue = self.output_queue
            self.managed_processes[process_id].status = "stopped"  # Ensure status is reset before start
            print(f"[AppState] Reset NEW managed state event/queue pointers and status for ID: '{process_id}'.")

    def set_process(self, process: subprocess.Popen, script_path: str = "bot.py", display_name: str = "MaiCore"):
        """
        Sets the process handle and PID.
        Also updates the new managed_processes dictionary for compatibility.
        """
        # --- Update OLD state ---
        self.bot_process = process
        self.bot_pid = process.pid
        # Reset stop event for the new process run
        self.stop_event.clear()
        # NOTE: We keep the OLD output_queue and stop_event separate for now,
        # as the current reader/processor loops use them directly.
        # In the future, the reader/processor will use the queue/event
        # from the ManagedProcessState object.

        # --- Update NEW state ---
        process_id = script_path  # Use script_path as ID for now
        new_process_state = ManagedProcessState(
            process_id=process_id,
            script_path=script_path,
            display_name=display_name,
            process_handle=process,
            pid=process.pid,
            # IMPORTANT: For now, use the *old* queue/event for the bot.py entry
            # to keep existing reader/processor working without immediate changes.
            # A true multi-process implementation would give each process its own.
            output_queue=self.output_queue,
            stop_event=self.stop_event,
            status="running",
        )
        self.managed_processes[process_id] = new_process_state
        print(
            f"[AppState] Set OLD process state (PID: {self.bot_pid}) and added/updated NEW managed state for ID: '{process_id}'"
        )

    def clear_process(self):
        """
        Clears the process handle and PID.
        Also updates the status in the new managed_processes dictionary.
        """
        old_pid = self.bot_pid
        process_id = "bot.py"  # Assuming clear is for the main bot process

        # --- Clear OLD state ---
        self.bot_process = None
        self.bot_pid = None
        # Don't clear stop_event here, it should be set to signal stopping.
        # Don't clear output_queue, might still contain final messages.

        # --- Update NEW state ---
        if process_id in self.managed_processes:
            self.managed_processes[process_id].process_handle = None
            self.managed_processes[process_id].pid = None
            self.managed_processes[process_id].status = "stopped"
            # Keep queue and event references for now
            print(
                f"[AppState] Cleared OLD process state (was PID: {old_pid}) and marked NEW managed state for ID: '{process_id}' as stopped."
            )
        else:
            print(
                f"[AppState] Cleared OLD process state (was PID: {old_pid}). No corresponding NEW state found for ID: '{process_id}'."
            )
