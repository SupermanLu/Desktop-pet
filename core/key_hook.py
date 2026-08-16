# -*- coding: utf-8 -*-
"""全局快捷键模块（Win32 RegisterHotKey + 独立消息泵线程）。

不依赖 Qt 原生事件过滤器，也不绑定到某个具体窗口句柄：
- 独立线程创建"消息专用窗口"(HWND_MESSAGE)，热键注册到该窗口
- 该线程自己跑 GetMessage 消息循环，收到 WM_HOTKEY 后发 Qt 信号回主线程
- 消息专用窗口在整个应用生命周期内有效，避免桌宠窗口隐藏/重建导致热键失效

快捷键（Ctrl+Alt+字母）：
  Q → 呼出/隐藏桌宠    L → 打开聊天
  Z → 防打扰开关        I → AI 直达菜单
"""
import ctypes
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, QThread, Signal

# --- Win32 常量 ---
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000   # 按住不自动连发
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HWND_MESSAGE = -3

# 虚拟键码: A-Z
_VK = {chr(0x41 + i): 0x41 + i for i in range(26)}

# 默认快捷键映射: 功能 key → 字母（仅 4 个）
# 注：C/A 在本机被占用（A 多为微信截图），改用 L/I
DEFAULT_MAP = {
    "toggle_pet": "Q",
    "chat": "L",
    "aiweb": "I",
    "dnm": "Z",
}

# 功能 key → 可读名称
FUNC_NAMES = {
    "toggle_pet": "呼出/隐藏桌宠",
    "chat": "打开聊天",
    "aiweb": "AI 直达菜单",
    "dnm": "防打扰开关",
}

_user32 = ctypes.windll.user32
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                   wintypes.UINT, wintypes.UINT]
_user32.UnregisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = ctypes.c_longlong
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM]
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.DestroyWindow.argtypes = [wintypes.HWND]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT),
                ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


# ---- 消息专用窗口回调（hwnd → worker 查表，收到 WM_HOTKEY 发信号） ----
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM)
_workers = {}
_WNDCLASS_NAME = "TraeDeskPetHotkeyWindow"


def _wnd_proc(hwnd, u_msg, w_param, l_param):
    if u_msg == WM_HOTKEY:
        worker = _workers.get(hwnd)
        if worker is not None:
            worker.triggered.emit(w_param & 0xFFFF)
        return 0
    return _user32.DefWindowProcW(hwnd, u_msg, w_param, l_param)


_WND_PROC_CB = _WNDPROC(_wnd_proc)


class _HotkeyWorker(QThread):
    """独立线程：建消息专用窗口 → 注册热键 → GetMessage 循环。"""

    triggered = Signal(int)   # 收到热键：发射 vk 键码
    ready = Signal(list)      # 注册完成：发射失败的 func_key 列表

    def __init__(self, mapping: dict, parent=None):
        super().__init__(parent)
        # mapping: {func_key: letter}
        self._rev = {}
        for func_key, letter in mapping.items():
            vk = _VK.get(str(letter).upper())
            if vk is not None:
                self._rev[vk] = func_key
        self._lock = threading.Lock()
        self._hwnd = None

    def key_for(self, vk: int):
        return self._rev.get(vk)

    def run(self):
        hwnd = self._create_msg_window()
        with self._lock:
            self._hwnd = hwnd
        if not hwnd:
            self.ready.emit(list(self._rev.values()))
            return
        _workers[hwnd] = self
        failed = []
        for vk in self._rev:
            if not _user32.RegisterHotKey(
                    hwnd, vk, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, vk):
                failed.append(self._rev[vk])
        self.ready.emit(failed)

        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        # 清理
        for vk in self._rev:
            _user32.UnregisterHotKey(hwnd, vk)
        _workers.pop(hwnd, None)
        _user32.DestroyWindow(hwnd)
        self._unregister_class()

    def stop(self):
        """投递 WM_QUIT 让消息循环退出。"""
        with self._lock:
            hwnd = self._hwnd
        if hwnd:
            _user32.PostMessageW(hwnd, WM_QUIT, 0, 0)

    # ---- Win32 消息专用窗口 ----
    def _create_msg_window(self):
        _user32.RegisterClassW.restype = wintypes.ATOM
        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(_WND_PROC_CB, ctypes.c_void_p)
        wc.lpszClassName = _WNDCLASS_NAME
        wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
        if not _user32.RegisterClassW(ctypes.byref(wc)):
            # 已注册过则直接继续（同进程单实例）
            if ctypes.windll.kernel32.GetLastError() != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                return 0
        _user32.CreateWindowExW.restype = wintypes.HWND
        _user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPVOID]
        return _user32.CreateWindowExW(
            0, _WNDCLASS_NAME, "hk", 0, 0, 0, 0, 0,
            ctypes.cast(HWND_MESSAGE, wintypes.HWND),
            None, wc.hInstance, None)

    def _unregister_class(self):
        _user32.UnregisterClassW(_WNDCLASS_NAME,
                                 ctypes.windll.kernel32.GetModuleHandleW(None))


class GlobalHotkey(QObject):
    """对外接口：start() 启动热键线程，hotkey_triggered 收到功能 key。"""

    hotkey_triggered = Signal(str)   # 功能 key
    ready = Signal(list)             # 注册完成：失败的功能 key 列表

    def __init__(self, mapping: dict | None = None, parent=None):
        super().__init__(parent)
        mapping = mapping or DEFAULT_MAP
        self._worker = _HotkeyWorker(mapping)
        self._worker.triggered.connect(self._on_vk)
        self._worker.ready.connect(self.ready)

    def start(self):
        self._worker.start()

    def stop(self):
        self._worker.stop()

    def _on_vk(self, vk: int):
        key = self._worker.key_for(vk)
        if key:
            self.hotkey_triggered.emit(key)
