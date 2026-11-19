"""GUI entry point. The same frozen interpreter also hosts the isolated yt-dlp worker."""
import ctypes
import multiprocessing
import os
import sys


def attach_stream(name, handle_id):
    if getattr(sys, name) is not None:
        return
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.windll.kernel32
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    handle = kernel.GetStdHandle(handle_id)
    duplicate = wintypes.HANDLE()
    current = kernel.GetCurrentProcess()
    if handle and kernel.DuplicateHandle(current, handle, current, ctypes.byref(duplicate), 0, False, 2):
        fd = msvcrt.open_osfhandle(duplicate.value, os.O_WRONLY | os.O_BINARY)
        stream = os.fdopen(fd, "w", encoding="utf-8", errors="replace", buffering=1)
    else:
        stream = open(os.devnull, "w", encoding="utf-8")
    setattr(sys, name, stream)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    attach_stream("stdout", -11)
    attach_stream("stderr", -12)
    if sys.argv[1:2] == ["--yt-worker"]:
        from yt_dlp import main as worker
        worker(sys.argv[2:])
    else:
        from launch import main
        try:
            main()
        except Exception as exc:
            if "--headless" in sys.argv:
                raise
            ctypes.windll.user32.MessageBoxW(None, str(exc), "泊岸 · 无法启动", 0x10)
            sys.exit(1)
