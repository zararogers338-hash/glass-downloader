"""Window lifetime for the self-contained Windows build."""
import asyncio
import ctypes
from ctypes import wintypes
import os
import subprocess
from .catalog import ROOT


def raise_window(pid):
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

    @callback_type
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return False
        return True

    user32.EnumWindows(visit, 0)


class DesktopSession:
    def __init__(self):
        self.window = None
        self.url = ""
        self.has_work = lambda: False

    def activate(self):
        if self.window and self.window.poll() is None:
            raise_window(self.window.pid)
            return
        self.window = subprocess.Popen(
            [str(ROOT / "desktop" / "glass-downloader.exe")],
            env={**os.environ, "GLASS_START_URL": self.url},
        )

    async def run(self, url):
        self.url = url
        self.activate()
        while True:
            await asyncio.sleep(0.4)
            code = self.window.poll()
            if code is None:
                continue
            if code:
                raise RuntimeError("桌面窗口启动或运行失败，请检查 Microsoft Edge WebView2 Runtime。")
            if not self.has_work():
                return
