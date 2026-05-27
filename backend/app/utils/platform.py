import os
import platform


def lower_process_priority() -> None:
    """Best-effort priority reduction for long-running worker processes."""
    system = platform.system().lower()
    if system == "windows":
        lower_windows_process_priority()
        return

    nice = getattr(os, "nice", None)
    if nice is None:
        return
    try:
        nice(5)
    except OSError:
        return


def lower_windows_process_priority() -> None:
    try:
        import ctypes
    except ImportError:
        return

    below_normal_priority_class = 0x00004000
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.GetCurrentProcess()
        kernel32.SetPriorityClass(handle, below_normal_priority_class)
    except (AttributeError, OSError):
        return
