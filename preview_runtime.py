"""Bounded preview workers and a session-only cache, separate from exports."""
from collections import OrderedDict
from pathlib import Path
import threading
from PySide6.QtCore import QThreadPool

_pools={}
def preview_pool(background=False):
    key=bool(background)
    if key not in _pools:
        pool=QThreadPool();pool.setMaxThreadCount(2);_pools[key]=pool
    return _pools[key]

def previews_running():return any(pool.activeThreadCount() for pool in _pools.values())

def source_key(kind,path,*options):
    path=Path(path).resolve();s=path.stat()
    return (kind,str(path),s.st_size,s.st_mtime_ns,*options)

class PreviewCache:
    def __init__(self,limit=32*1024*1024):
        self.limit=limit;self.used=0;self.items=OrderedDict();self.lock=threading.Lock()
    def get(self,key):
        with self.lock:
            entry=self.items.get(key)
            if entry is None:return None
            self.items.move_to_end(key);return entry[0]
    def put(self,key,value,size):
        size=max(1,int(size))
        with self.lock:
            old=self.items.pop(key,None)
            if old:self.used-=old[1]
            if size>self.limit:return
            while self.items and self.used+size>self.limit:
                _,(_,cost)=self.items.popitem(last=False);self.used-=cost
            self.items[key]=(value,size);self.used+=size
    def clear(self):
        with self.lock:self.items.clear();self.used=0

preview_cache=PreviewCache()
