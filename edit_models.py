"""Editing state and timestamp-accurate paused frame decoding."""
from collections import deque
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

class CutModel:
    def __init__(self,duration):
        self.duration=float(duration);self.cuts=[];self.segments=[(0.0,self.duration,True)];self.undo_stack=[];self.redo_stack=[]
    def snapshot(self):return (list(self.cuts),list(self.segments))
    def remember(self):self.undo_stack.append(self.snapshot());self.undo_stack=self.undo_stack[-100:];self.redo_stack.clear()
    def undo(self):
        if not self.undo_stack:return False
        self.redo_stack.append(self.snapshot());self.cuts,self.segments=self.undo_stack.pop();return True
    def redo(self):
        if not self.redo_stack:return False
        self.undo_stack.append(self.snapshot());self.cuts,self.segments=self.redo_stack.pop();return True
    def _rebuild(self):
        old=self.segments;bounds=[0.0]+self.cuts+[self.duration];self.segments=[]
        for start,end in zip(bounds,bounds[1:]):
            overlapping=[keep for left,right,keep in old if left<end-1e-7 and right>start+1e-7]
            self.segments.append((start,end,any(overlapping) if overlapping else True))
    def add(self,position):
        position=float(position)
        if not 1e-6<position<self.duration-1e-6:return False
        if any(abs(position-existing)<1e-6 for existing in self.cuts):return False
        self.remember();self.cuts=sorted(self.cuts+[position]);self._rebuild();return True
    def remove(self,index):
        if not 0<=index<len(self.cuts):return
        self.remember();self.cuts.pop(index);self._rebuild()
    def keep(self,index,keep):
        start,end,old=self.segments[index]
        if old==bool(keep):return
        self.remember();self.segments[index]=(start,end,bool(keep))
    def ranges(self):return [(start,end) for start,end,keep in self.segments if keep]


@lru_cache(maxsize=12)
def _timing(path,size,mtime):
    import av
    with av.open(path) as container:
        streams=[stream for stream in container.streams.video if not (int(getattr(stream.disposition,'value',stream.disposition)) & 0x400)]
        if not streams:raise ValueError('Kein Videostream gefunden.')
        stream=streams[0];base=stream.time_base;origin=int(stream.start_time or 0)
        declared=float(stream.duration*base) if stream.duration else float(container.duration/av.time_base) if container.duration else 0
        if declared>2:
            container.seek(origin+int((declared-2)/float(base)),stream=stream,backward=True,any_frame=False)
        last=None;previous=None;last_duration=0
        for frame in container.decode(stream):
            if frame.pts is None:continue
            previous,last=last,float(frame.pts*frame.time_base-origin*base)
            last_duration=float(getattr(frame,'duration',0) or 0)*float(frame.time_base)
        if last is not None:
            hold=last_duration if last_duration>0 else last-previous if previous is not None and last>previous else 1/float(stream.average_rate or 25)
            return max(.000001,last+hold)
        if declared>0:return declared
        raise ValueError('Videodauer konnte nicht bestimmt werden.')


def video_duration(path):
    path=Path(path).resolve();status=path.stat();return _timing(str(path),status.st_size,status.st_mtime_ns)


class FrameReader:
    """One serialized decoder per editor; forward steps reuse its iterator."""
    def __init__(self,path):
        import threading
        self.path=str(path);self.container=None;self.lock=threading.RLock();self._actual=None;self._forward=None;self._ahead=None;self._signature=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        with self.lock:
            self._forward=None;self._ahead=None;self._actual=None;self._signature=None
            if self.container is not None:self.container.close();self.container=None
    def read(self,position=0.0,steps=0,stopped=None,max_size=(1600,1000),sequential=False):
        with self.lock:return self._read(position,steps,stopped,max_size,sequential)
    def _read(self,position,steps,stopped,max_size,sequential):
        import av
        def check():
            if stopped and stopped.is_set():raise RuntimeError('Vorschau geschlossen')
        check()
        stat=Path(self.path).stat();signature=(stat.st_size,stat.st_mtime_ns)
        if self._signature is not None and signature!=self._signature:raise ValueError('Videodatei wurde geändert. Bitte den Editor neu öffnen.')
        if self.container is None:self.container=av.open(self.path);self._signature=signature
        container=self.container
        streams=[stream for stream in container.streams.video if not (int(getattr(stream.disposition,'value',stream.disposition)) & 0x400)]
        if not streams:raise ValueError('Kein Videostream für die Vorschau gefunden.')
        stream=streams[0];base=stream.time_base;origin=int(stream.start_time or 0)
        duration=video_duration(self.path)
        if duration<=0:raise ValueError('Videodauer konnte nicht ermittelt werden.')
        target=max(0,min(float(position),max(0,duration-1e-6)))
        def time_of(frame):
            if frame.pts is None:raise ValueError('Einzelbildschritte benötigen Bildzeitstempel in dieser Datei.')
            return float(frame.pts*frame.time_base-origin*base)
        def frames_from(start):
            check();container.seek(max(origin,int(Fraction(str(max(0,start)))/base)+origin),stream=stream,backward=True,any_frame=False)
            for frame in container.decode(stream):
                check();yield frame,time_of(frame)
        selected=None;actual=0.0;iterator=None;ahead=None
        if steps>0 and self._actual is not None and abs(target-self._actual)<1e-7 and self._forward is not None:
            iterator=self._forward
            # The frame after a covering-frame seek has already been decoded.
            remaining=steps
            candidate=self._ahead;self._ahead=None
            while remaining:
                if candidate is None:
                    try:candidate=next(iterator)
                    except StopIteration:break
                frame,time=candidate;candidate=None
                if time>target+1e-7:selected,actual=frame,time;remaining-=1
            if selected is None:
                # At EOF use the normal timestamp path to retain the last frame.
                iterator=None
        if steps==0 and sequential and self._actual is not None and 0<target-self._actual<=1.0 and self._forward is not None:
            iterator=self._forward;candidate=self._ahead;self._ahead=None
            while True:
                if candidate is None:
                    try:candidate=next(iterator)
                    except StopIteration:break
                frame,time=candidate;candidate=None
                if time>target+1e-7:
                    if selected is None:iterator=None
                    else:ahead=(frame,time)
                    break
                selected,actual=frame,time
            if selected is None:iterator=None
        if iterator is None:
            if steps<0:
                count=abs(steps);window=max(1.0,count/15)
                while True:
                    begin=max(0,target-window);previous=deque(maxlen=count);first=None
                    for frame,time in frames_from(begin):
                        if first is None:first=time
                        if time>=target-1e-7:break
                        previous.append(time)
                    if len(previous)>=count or begin<=0:
                        chosen=previous[0] if previous else first or 0.0;break
                    window*=2
                iterator=frames_from(max(0,chosen-.001))
                for frame,time in iterator:
                    if time>=chosen-1e-7:selected,actual=frame,time;break
            elif steps>0:
                remaining=steps;iterator=frames_from(max(0,target-.001))
                for frame,time in iterator:
                    selected,actual=frame,time
                    if time>target+1e-7:
                        remaining-=1
                        if not remaining:break
            else:
                iterator=frames_from(max(0,target-.001))
                for frame,time in iterator:
                    if time>target+1e-7:
                        if selected is None:selected,actual=frame,time
                        else:ahead=(frame,time)
                        break
                    selected,actual=frame,time
        if selected is None:raise ValueError('Dieses Videobild konnte nicht dekodiert werden.')
        check();self._actual=actual;self._forward=iterator;self._ahead=ahead
        # Resize in the decoder before allocating a full RGB image (e.g. 4K).
        scale=min(1.,max_size[0]/selected.width,max_size[1]/selected.height)
        preview=selected.reformat(width=max(1,round(selected.width*scale)),height=max(1,round(selected.height*scale)),format='rgb24')
        image=preview.to_image();rotation=getattr(selected,'rotation',0)
        if rotation:image=image.rotate(float(rotation),expand=True)
        image.thumbnail(max_size)
        return image,max(0,actual),duration


def read_frame(path,position=0.0,steps=0,stopped=None):
    """Standalone timestamp-accurate access; editors retain a FrameReader."""
    with FrameReader(path) as reader:return reader.read(position,steps,stopped)
