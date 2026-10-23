"""Scope automatic shortcuts to file surfaces and explicit browser selections.

No hooks, injected code, game-specific detection or background process enumeration.
Only foreground and mouse-down source windows are queried with limited access.
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import ntpath
import os
import sys
import time

FILE_MANAGERS = frozenset({'totalcmd.exe', 'totalcmd64.exe', 'doublecmd.exe',
                          'dopus.exe', 'freecommander.exe', 'freecommander64.exe', 'files.exe'})
BROWSERS = frozenset({'msedge.exe', 'chrome.exe', 'firefox.exe', 'brave.exe',
                      'vivaldi.exe', 'opera.exe', 'librewolf.exe', 'waterfox.exe', 'floorp.exe'})
SHELL_CLASSES = frozenset({'CabinetWClass', 'ExploreWClass', 'Progman', 'WorkerW', 'SHELLDLL_DefView', 'SysListView32'})


@dataclass(frozen=True)
class ActivationContext:
    token: tuple = (0, 0)
    drag: bool = False
    selection: bool = False


def classify_window(hwnd, pid, executable, window_class, own_pid=None, fullscreen=False):
    if not hwnd or not pid:
        return ActivationContext()
    name = ntpath.basename(executable).casefold()
    own = pid == (os.getpid() if own_pid is None else own_pid)
    shell = name == 'explorer.exe' and window_class in SHELL_CLASSES
    drag = own or shell or name in FILE_MANAGERS
    # Browser mouse shortcuts do not open a wheel. Only a separate key press
    # after selecting a link may request UI Automation; fullscreen is excluded.
    selection = own or (not fullscreen and name in BROWSERS)
    return ActivationContext((int(hwnd), int(pid)), drag, selection)


class ActivationGuard:
    def __init__(self):
        self._token = None
        self._until = 0
        self._context = ActivationContext()
        self._api = None
        self._mouse_down=False
        self._drag_origin=None

    def _windows_api(self):
        if self._api is not None:
            return self._api
        user = ctypes.WinDLL('user32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        user.GetForegroundWindow.argtypes = []; user.GetForegroundWindow.restype = wintypes.HWND
        user.GetCursorPos.argtypes=[ctypes.POINTER(wintypes.POINT)];user.GetCursorPos.restype=wintypes.BOOL
        user.WindowFromPoint.argtypes=[wintypes.POINT];user.WindowFromPoint.restype=wintypes.HWND
        user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
        user.IsWindow.argtypes=[wintypes.HWND];user.IsWindow.restype=wintypes.BOOL
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowThreadProcessId.restype = wintypes.DWORD
        user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.GetClassNameW.restype = ctypes.c_int
        user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.GetWindowRect.restype = wintypes.BOOL
        user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user.MonitorFromWindow.restype = wintypes.HANDLE
        user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        user.GetMonitorInfoW.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]; kernel.CloseHandle.restype = wintypes.BOOL
        self._api = user, kernel
        return self._api

    def _window_context(self,hwnd):
        user,kernel=self._windows_api()
        pid=wintypes.DWORD()
        if not hwnd or not user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid)):return ActivationContext()
        cls=ctypes.create_unicode_buffer(256)
        if not user.GetClassNameW(hwnd,cls,len(cls)):return ActivationContext()
        executable=''
        if pid.value!=os.getpid():
            handle=kernel.OpenProcess(0x1000,False,pid.value)
            if not handle:return ActivationContext()
            try:
                path=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(path))
                if not kernel.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)):return ActivationContext()
                executable=path.value
            finally:kernel.CloseHandle(handle)
        class MonitorInfo(ctypes.Structure):
            _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD)]
        rect=wintypes.RECT();monitor=MonitorInfo();monitor.cbSize=ctypes.sizeof(monitor);fullscreen=False
        if user.GetWindowRect(hwnd,ctypes.byref(rect)) and user.GetMonitorInfoW(user.MonitorFromWindow(hwnd,2),ctypes.byref(monitor)):
            bounds=monitor.rcMonitor
            fullscreen=(rect.left<=bounds.left and rect.top<=bounds.top and rect.right>=bounds.right and rect.bottom>=bounds.bottom)
        return classify_window(hwnd,pid.value,executable,cls.value,fullscreen=fullscreen)

    def _foreground_context(self):
        user,kernel=self._windows_api();hwnd=user.GetForegroundWindow();pid=wintypes.DWORD()
        if not hwnd or not user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid)):return ActivationContext()
        token=(int(hwnd),int(pid.value));now=time.monotonic()
        if token==self._token and now<self._until:return self._context
        self._token,self._until=token,now
        self._context=self._window_context(hwnd)
        # Retry transient native failures immediately; don't cache them as denial.
        if self._context.token!= (0,0):self._until=now+.25
        return self._context

    def _pointer_context(self):
        user,kernel=self._windows_api();point=wintypes.POINT()
        if not user.GetCursorPos(ctypes.byref(point)):return ActivationContext()
        hwnd=user.WindowFromPoint(point)
        context=self._window_context(hwnd)
        if context.drag:return context
        root=user.GetAncestor(hwnd,2) if hwnd else 0  # GA_ROOT, not a hidden desktop behind a covering app.
        return self._window_context(root) if root and root!=hwnd else context

    def _origin_alive(self):
        if self._drag_origin is None:return False
        user,kernel=self._windows_api();hwnd,pid=self._drag_origin.token;actual=wintypes.DWORD()
        return bool(user.IsWindow(hwnd) and user.GetWindowThreadProcessId(hwnd,ctypes.byref(actual)) and actual.value==pid)

    def reset_drag(self,mouse_down=False):
        self._mouse_down=bool(mouse_down);self._drag_origin=None

    def context(self,mouse_down=None):
        if sys.platform!='win32':return ActivationContext()
        try:
            foreground=self._foreground_context()
            if mouse_down is None:return foreground
            if not mouse_down:
                self.reset_drag();return foreground
            if not self._mouse_down:
                self._mouse_down=True
                origin=self._pointer_context()
                self._drag_origin=origin if origin.drag else None
            if self._drag_origin is not None:
                if self._origin_alive():return ActivationContext(self._drag_origin.token,True,False)
                self._drag_origin=None
            return ActivationContext(foreground.token,False,foreground.selection)
        except (OSError,AttributeError,ValueError,TypeError):
            self._drag_origin=None
            return ActivationContext()
