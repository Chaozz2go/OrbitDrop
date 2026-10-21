"""Cooperative task cancellation plus cancellable subprocess trees."""
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time

class Cancelled(Exception):
    pass

_local=threading.local()

class TaskControl:
    def __init__(self,callback=None):
        self.cancelled=threading.Event()
        self.callback=callback or (lambda percent,message:None)
        self.base=0.0;self.span=100.0
        self.outputs=[]
        self.last_emit=0.0
    def cancel(self):self.cancelled.set()
    def check(self):
        if self.cancelled.is_set():raise Cancelled('Abgebrochen')
    def report(self,percent=None,message=''):
        now=time.monotonic()
        if percent is None:
            value=-1
        else:value=max(0,min(99,int(self.base+self.span*max(0,min(100,percent))/100)))
        if now-self.last_emit>=.08 or percent in (0,100):
            self.callback(value,message);self.last_emit=now
    @contextmanager
    def activate(self):
        old=getattr(_local,'control',None);_local.control=self
        try:yield self
        finally:_local.control=old


def current():return getattr(_local,'control',None)
def checkpoint(percent=None,message=''):
    control=current()
    if control:
        control.check()
        if percent is not None or message:control.report(percent,message)


def copy_stream(source,target,total=None):
    copied=0
    while True:
        checkpoint()
        block=source.read(1024*1024)
        if not block:break
        target.write(block);copied+=len(block)
        if total:checkpoint(copied*100/total,'Daten werden verarbeitet …')
    return copied


def stop_process(process):
    if process.poll() is not None:return
    if sys.platform=='win32':
        taskkill=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'
        subprocess.run([str(taskkill),'/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
    else:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    try:process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        if sys.platform!='win32':
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:process.kill()
        process.communicate(timeout=5)


def run_process(args,timeout=10,duration=None):
    control=current()
    if control:control.check()
    options={'creationflags':subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform=='win32' else {'start_new_session':True}
    progress_dir=None;progress_file=None
    if duration and control and Path(str(args[0])).stem.lower().startswith('ffmpeg'):
        progress_dir=tempfile.TemporaryDirectory(prefix='orbit-progress-')
        progress_file=Path(progress_dir.name)/'progress.txt'
        args=[args[0],'-progress',str(progress_file),'-nostats',*args[1:]]
    process=None
    try:
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,errors='replace',**options)
        start=time.monotonic()
        while True:
            if control:control.check()
            if time.monotonic()-start>timeout:raise subprocess.TimeoutExpired(args,timeout)
            if progress_file and progress_file.exists():
                # A bounded tail is enough to read the latest FFmpeg timestamp.
                with progress_file.open('rb') as handle:
                    handle.seek(max(0,progress_file.stat().st_size-4096));text=handle.read().decode('utf-8',errors='replace')
                values=[line.split('=',1)[1] for line in text.splitlines() if line.startswith('out_time_us=')]
                if values:
                    try:control.report(float(values[-1])/1_000_000/duration*100,'Video/Audio wird konvertiert …')
                    except ValueError:pass
            try:
                stdout,stderr=process.communicate(timeout=.12)
                break
            except subprocess.TimeoutExpired:pass
        if control:control.check()
        return subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    except BaseException:
        if process:
            try:stop_process(process)
            except Exception:
                process.kill();process.wait()
        raise
    finally:
        if progress_dir:progress_dir.cleanup()
