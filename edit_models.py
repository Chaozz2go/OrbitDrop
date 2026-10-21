"""Editing state and timestamp-accurate paused frame decoding."""
from collections import deque
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

class CutModel:
    def __init__(self,duration):
        self.duration=float(duration);self.cuts=[];self.segments=[(0.0,self.duration,True)]
    def _rebuild(self):
        old=self.segments;bounds=[0.0]+self.cuts+[self.duration];self.segments=[]
        for start,end in zip(bounds,bounds[1:]):
            overlapping=[keep for left,right,keep in old if left<end-1e-7 and right>start+1e-7]
            self.segments.append((start,end,any(overlapping) if overlapping else True))
    def add(self,position):
        position=float(position)
        if not 1e-6<position<self.duration-1e-6:return False
        if any(abs(position-existing)<1e-6 for existing in self.cuts):return False
        self.cuts=sorted(self.cuts+[position]);self._rebuild();return True
    def remove(self,index):
        if not 0<=index<len(self.cuts):return
        self.cuts.pop(index);self._rebuild()
    def keep(self,index,keep):
        start,end,_=self.segments[index];self.segments[index]=(start,end,bool(keep))
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


def read_frame(path,position=0.0,steps=0,stopped=None):
    """Seek to a keyframe, then decode real PTS. Never guess a frame duration."""
    import av
    def check():
        if stopped and stopped.is_set():raise RuntimeError('Vorschau geschlossen')
    check()
    with av.open(str(path)) as container:
        streams=[stream for stream in container.streams.video if not (int(getattr(stream.disposition,'value',stream.disposition)) & 0x400)]
        if not streams:raise ValueError('Kein Videostream für die Vorschau gefunden.')
        stream=streams[0];base=stream.time_base;origin=int(stream.start_time or 0)
        duration=video_duration(path)
        if duration<=0:raise ValueError('Videodauer konnte nicht ermittelt werden.')
        target=max(0,min(float(position),max(0,duration-1e-6)))
        def time_of(frame):
            if frame.pts is None:raise ValueError('Einzelbildschritte benötigen Bildzeitstempel in dieser Datei.')
            return float(frame.pts*frame.time_base-origin*base)
        def frames_from(start):
            check();container.seek(max(origin,int(Fraction(str(max(0,start)))/base)+origin),stream=stream,backward=True,any_frame=False)
            for frame in container.decode(stream):
                check();yield frame,time_of(frame)
        selected=None;actual=0.0
        if steps<0:
            count=abs(steps);window=max(1.0,count/15)
            while True:
                begin=max(0,target-window);previous=deque(maxlen=count);first=None
                for frame,time in frames_from(begin):
                    if first is None:first=time
                    if time>=target-1e-7:break
                    previous.append(time)
                if len(previous)>=count or begin<=0:
                    chosen=previous[0] if previous else first or 0.0
                    break
                window*=2
            for frame,time in frames_from(max(0,chosen-.001)):
                if time>=chosen-1e-7:selected,actual=frame,time;break
        elif steps>0:
            remaining=steps
            for frame,time in frames_from(max(0,target-.001)):
                selected,actual=frame,time
                if time>target+1e-7:
                    remaining-=1
                    if not remaining:break
        else:
            # Show the frame covering the requested time, not the following frame.
            for frame,time in frames_from(max(0,target-.001)):
                if time>target+1e-7:
                    if selected is None:selected,actual=frame,time
                    break
                selected,actual=frame,time
        if selected is None:raise ValueError('Dieses Videobild konnte nicht dekodiert werden.')
        image=selected.to_image()
        # Camera display rotation is carried by frame side data in modern PyAV.
        rotation=getattr(selected,'rotation',0)
        if rotation:image=image.rotate(float(rotation),expand=True)
        image.thumbnail((1600,1000))
        return image,max(0,actual),duration
