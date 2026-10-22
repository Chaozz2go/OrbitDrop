"""Bounded shortcut events from a private Windows Raw Input message thread.

Only configured key states and derived mode events are kept briefly in memory.
No text, files, clipboard contents, hooks, key suppression or disk logging.
"""
from collections import deque
from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import sys
import threading
import time
from shortcuts import KEY_CODES,polling_keys,pressed_mode

SIDES={0x10:(0xa0,0xa1),0x11:(0xa2,0xa3),0x12:(0xa4,0xa5)}


def physical_key(vkey,make_code,flags):
    if vkey==0x10:return 0xa1 if make_code==0x36 else 0xa0
    if vkey==0x11:return 0xa3 if flags&2 else 0xa2
    if vkey==0x12:return 0xa5 if flags&2 else 0xa4
    return vkey


@dataclass(frozen=True)
class ShortcutEvent:
    mode:str
    token:tuple
    at:float


class ShortcutEvents:
    def __init__(self,values):
        self.lock=threading.Lock();self.events=deque(maxlen=16);self.down=set()
        self.values={};self.codes={};self.watched=set();self.enabled=True
        self.available=False;self.error='';self.ready=threading.Event();self.stopping=threading.Event()
        self.thread=None;self.thread_id=0;self.user=None
        self.configure(values)
    def configure(self,values,enabled=True):
        bindings={key:values[key] for key in ('convert_key','edit_key','files_key')}
        with self.lock:
            if bindings!=self.values:
                self.values=bindings;self.codes=polling_keys(bindings)
                self.watched=set(self.codes.values())
                for sides in SIDES.values():self.watched.update(sides)
                self.down={code for code in self.watched if self.user and self.user.GetAsyncKeyState(code)&0x8000}
                self.events.clear()
            self.enabled=enabled
            if not enabled:self.events.clear()
    def _snapshot(self):
        return {name:(any(side in self.down for side in SIDES[code]) if code in SIDES else code in self.down) for name,code in self.codes.items()}
    def feed(self,vkey,down,left,token,now=None):
        with self.lock:
            if vkey not in self.watched:return
            before=self._snapshot()
            if down:self.down.add(vkey)
            else:self.down.discard(vkey)
            mode=pressed_mode(self.values,self._snapshot(),before)
            if mode and left and self.enabled:
                self.events.append(ShortcutEvent(mode,tuple(token),time.monotonic() if now is None else now))
    def drain(self):
        with self.lock:
            result=list(self.events);self.events.clear();return result
    def start(self):
        if sys.platform=='win32' and self.thread is None:
            self.thread=threading.Thread(target=self._run,name='OrbitDropShortcutEvents',daemon=True);self.thread.start()
        return self
    def close(self):
        self.stopping.set()
        if self.user and self.thread_id:self.user.PostThreadMessageW(self.thread_id,0x12,0,0)
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=1)
        self.drain()
    def _run(self):
        window=None;registered=False;atom=0;instance=None
        try:
            user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            self.user=user
            result_type=ctypes.c_ssize_t
            window_proc=ctypes.WINFUNCTYPE(result_type,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
            class WindowClass(ctypes.Structure):
                _fields_=[('style',wintypes.UINT),('proc',window_proc),('class_extra',ctypes.c_int),('window_extra',ctypes.c_int),('instance',wintypes.HINSTANCE),('icon',wintypes.HANDLE),('cursor',wintypes.HANDLE),('background',wintypes.HANDLE),('menu',wintypes.LPCWSTR),('name',wintypes.LPCWSTR)]
            class Device(ctypes.Structure):
                _fields_=[('page',wintypes.USHORT),('usage',wintypes.USHORT),('flags',wintypes.DWORD),('window',wintypes.HWND)]
            class Header(ctypes.Structure):
                _fields_=[('kind',wintypes.DWORD),('size',wintypes.DWORD),('device',wintypes.HANDLE),('param',wintypes.WPARAM)]
            class Keyboard(ctypes.Structure):
                _fields_=[('make',wintypes.USHORT),('flags',wintypes.USHORT),('reserved',wintypes.USHORT),('key',wintypes.USHORT),('message',wintypes.UINT),('extra',wintypes.ULONG)]
            signatures={
                'DefWindowProcW':([wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM],result_type),
                'RegisterClassW':([ctypes.POINTER(WindowClass)],wintypes.ATOM),
                'CreateWindowExW':([wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,ctypes.c_void_p],wintypes.HWND),
                'RegisterRawInputDevices':([ctypes.POINTER(Device),wintypes.UINT,wintypes.UINT],wintypes.BOOL),
                'GetRawInputData':([wintypes.HANDLE,wintypes.UINT,ctypes.c_void_p,ctypes.POINTER(wintypes.UINT),wintypes.UINT],wintypes.UINT),
                'GetForegroundWindow':([],wintypes.HWND),
                'GetWindowThreadProcessId':([wintypes.HWND,ctypes.POINTER(wintypes.DWORD)],wintypes.DWORD),
                'GetAsyncKeyState':([ctypes.c_int],wintypes.SHORT),
                'GetMessageW':([ctypes.POINTER(wintypes.MSG),wintypes.HWND,wintypes.UINT,wintypes.UINT],wintypes.BOOL),
                'PeekMessageW':([ctypes.POINTER(wintypes.MSG),wintypes.HWND,wintypes.UINT,wintypes.UINT,wintypes.UINT],wintypes.BOOL),
                'TranslateMessage':([ctypes.POINTER(wintypes.MSG)],wintypes.BOOL),
                'DispatchMessageW':([ctypes.POINTER(wintypes.MSG)],result_type),
                'DestroyWindow':([wintypes.HWND],wintypes.BOOL),
                'UnregisterClassW':([wintypes.LPCWSTR,wintypes.HINSTANCE],wintypes.BOOL),
                'PostThreadMessageW':([wintypes.DWORD,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM],wintypes.BOOL),
            }
            for name,(args,result) in signatures.items():
                function=getattr(user,name);function.argtypes=args;function.restype=result
            kernel.GetModuleHandleW.argtypes=[wintypes.LPCWSTR];kernel.GetModuleHandleW.restype=wintypes.HMODULE
            kernel.GetCurrentThreadId.argtypes=[];kernel.GetCurrentThreadId.restype=wintypes.DWORD
            instance=kernel.GetModuleHandleW(None)
            def receive(hwnd,message,wparam,lparam):
                if message==0xff:
                    try:
                        count=wintypes.UINT()
                        header_size=ctypes.sizeof(Header)
                        if user.GetRawInputData(lparam,0x10000003,None,ctypes.byref(count),header_size)==0 and header_size+ctypes.sizeof(Keyboard)<=count.value<=4096:
                            data=ctypes.create_string_buffer(count.value)
                            copied=user.GetRawInputData(lparam,0x10000003,data,ctypes.byref(count),header_size)
                            if copied==count.value and Header.from_buffer(data).kind==1:
                                keyboard=Keyboard.from_buffer(data,header_size)
                                vk=physical_key(keyboard.key,keyboard.make,keyboard.flags)
                                if vk in self.watched and keyboard.make!=0xff and keyboard.key<255:
                                    foreground=user.GetForegroundWindow();pid=wintypes.DWORD()
                                    if foreground:user.GetWindowThreadProcessId(foreground,ctypes.byref(pid))
                                    self.feed(vk,not bool(keyboard.flags&1),bool(user.GetAsyncKeyState(1)&0x8000),(int(foreground or 0),pid.value))
                    except (OSError,ValueError,TypeError):pass
                return user.DefWindowProcW(hwnd,message,wparam,lparam)
            self._callback=window_proc(receive)
            name='OrbitDropShortcutInput'+str(id(self))
            cls=WindowClass();cls.proc=self._callback;cls.instance=instance;cls.name=name
            atom=user.RegisterClassW(ctypes.byref(cls))
            if not atom:raise ctypes.WinError(ctypes.get_last_error())
            window=user.CreateWindowExW(0,name,'',0,0,0,0,0,wintypes.HWND(-3),None,instance,None)
            if not window:raise ctypes.WinError(ctypes.get_last_error())
            # INPUTSINK only: preserve all normal keyboard messages in other apps.
            device=Device(1,6,0x100,window)
            if not user.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(Device)):raise ctypes.WinError(ctypes.get_last_error())
            registered=True
            with self.lock:self.down={code for code in self.watched if user.GetAsyncKeyState(code)&0x8000}
            message=wintypes.MSG();user.PeekMessageW(ctypes.byref(message),None,0,0,0)
            self.thread_id=kernel.GetCurrentThreadId();self.available=True;self.ready.set()
            while not self.stopping.is_set():
                status=user.GetMessageW(ctypes.byref(message),None,0,0)
                if status<=0:break
                user.TranslateMessage(ctypes.byref(message));user.DispatchMessageW(ctypes.byref(message))
        except Exception as error:self.error=str(error)
        finally:
            self.available=False;self.ready.set()
            if registered:
                device=Device(1,6,1,None);user.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(Device))
            if window:user.DestroyWindow(window)
            if atom:user.UnregisterClassW(name,instance)
            self.thread_id=0
