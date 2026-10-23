"""Bounded-memory audio peaks and shared, interactive waveform timeline."""
from preview_runtime import preview_pool,preview_cache,source_key
from array import array
import math,threading
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QRectF
from PySide6.QtGui import QPainter,QColor,QPen,QFont
from PySide6.QtWidgets import QWidget
from ui_theme import CANVAS,paint_excluded
from timeline_view import visible_ticks

class WaveformCancelled(RuntimeError):pass


def extract_waveform(path,duration=None,points=2400,stopped=None,progress=None):
    import av
    stopped=stopped or threading.Event()
    def check():
        if stopped.is_set():raise WaveformCancelled('Wellenform geschlossen')
    check();points=max(64,min(8000,int(points)))
    with av.open(str(path),options={'protocol_whitelist':'file,pipe'}) as container:
        streams=list(container.streams.audio)
        if not streams:return {'duration':float(duration or 0),'peaks':[],'channels':0}
        stream=streams[0];videos=[v for v in container.streams.video if not (int(getattr(v.disposition,'value',v.disposition))&0x400)]
        reference=videos[0] if videos else stream;origin=float((reference.start_time or 0)*reference.time_base)
        if duration is None:
            declared=float(stream.duration*stream.time_base) if stream.duration else float(container.duration/av.time_base) if container.duration else 0
            duration=declared
        duration=float(duration)
        if not math.isfinite(duration) or duration<=0:raise ValueError('Keine gültige Dauer für die Audiospur.')
        channels=len(stream.codec_context.layout.channels);lanes=2 if channels==2 else 1;peaks=[[0.]*points for _ in range(lanes)]
        resampler=av.AudioResampler(format='fltp',rate=8000);fallback=0.;last_progress=-1
        def consume(frame):
            nonlocal fallback,last_progress
            check();rate=frame.sample_rate;start=float(frame.pts*frame.time_base)-origin if frame.pts is not None and frame.time_base else fallback
            fallback=start+frame.samples/rate;values=[]
            for plane in frame.planes:
                samples=array('f');samples.frombytes(bytes(plane)[:frame.samples*4]);values.append(samples)
            # Keep independent stereo peaks; aggregate other layouts by maximum,
            # so opposite-phase channels do not disappear in a mono mixdown.
            cursor=0
            while cursor<frame.samples:
                time=start+cursor/rate
                if time<0:cursor=max(cursor+1,min(frame.samples,math.ceil(-start*rate)));continue
                if time>=duration:break
                index=min(points-1,int(time/duration*points));end=min(frame.samples,max(cursor+1,math.ceil(((index+1)*duration/points-start)*rate)))
                for lane in range(lanes):
                    planes=[values[lane]] if lanes==2 else values
                    amplitude=max((abs(sample) for plane in planes for sample in plane[cursor:end]),default=0.)
                    if math.isfinite(amplitude):peaks[lane][index]=max(peaks[lane][index],min(1.,amplitude))
                cursor=end
            percent=min(100,int(max(0,fallback)/duration*100))
            if progress and percent>=last_progress+5:last_progress=percent;progress(percent)
        for decoded in container.decode(stream):
            check()
            for frame in resampler.resample(decoded):consume(frame)
        for frame in resampler.resample(None):consume(frame)
        check();return {'duration':duration,'peaks':peaks,'channels':channels}

class WaveSignals(QObject):
    done=Signal(object,str);progress=Signal(int)
class WaveJob(QRunnable):
    def __init__(self,path,duration,stopped):super().__init__();self.path,self.duration,self.stopped=path,duration,stopped;self.signals=WaveSignals()
    def run(self):
        try:
            key=source_key('waveform',self.path,self.duration)
            result=preview_cache.get(key)
            if result is None:
                result=extract_waveform(self.path,self.duration,stopped=self.stopped,progress=self.signals.progress.emit)
                if not self.stopped.is_set() and source_key('waveform',self.path,self.duration)==key:
                    preview_cache.put(key,result,512+sum(len(lane)*40 for lane in result['peaks']))
            if not self.stopped.is_set():self.signals.progress.emit(100)
            if not self.stopped.is_set():self.signals.done.emit(result,'')
        except WaveformCancelled:pass
        except Exception as error:
            if not self.stopped.is_set():self.signals.done.emit(None,str(error))

class Waveform(QWidget):
    seekRequested=Signal(float);segmentSelected=Signal(int);loaded=Signal(object);loadingProgress=Signal(int);finished=Signal()
    def __init__(self,owner,large=False):
        super().__init__();self.owner=owner;self.position=0.;self.selected_segment=-1;self.dragging=False;self.peaks=[];self.job=None;self.closed=False;self.message='Audiospur wird geladen …';self.stopped=None;self.large=large;self.display_gain=1.
        self.setMinimumHeight(190 if large else 88);self.setMouseTracking(True);self.setFocusPolicy(Qt.FocusPolicy.ClickFocus);self.setToolTip('Abschnitt anklicken · Position ziehen · Entf: ausgewählten Abschnitt entfernen')
        if not large:self.setMaximumHeight(100)
    def load(self,path,stopped,duration=None):
        if self.job or self.closed:return
        self.stopped=stopped;self.job=WaveJob(path,duration,stopped);self.job.signals.done.connect(self.ready);self.job.signals.progress.connect(self.progress);preview_pool(True).start(self.job)
    def progress(self,percent):
        if self.closed:return
        self.message=f'Audiospur wird berechnet … {percent} %';self.loadingProgress.emit(percent);self.update()
    def ready(self,result,error):
        self.job=None
        if self.closed or self.stopped and self.stopped.is_set():return
        if error:self.message='Wellenform nicht verfügbar: '+error;self.finished.emit();self.update();return
        self.peaks=result['peaks'];peak=max((max(lane,default=0.) for lane in self.peaks),default=0.);self.display_gain=min(16.,.9/peak) if peak>1e-6 else 1.;self.message='Keine Audiospur vorhanden' if not self.peaks else 'Audiospur · L / R' if len(self.peaks)==2 else 'Audiospur';self.message+=(' · Anzeige skaliert' if self.peaks and self.display_gain>1.05 else '');self.loaded.emit(result);self.finished.emit();self.update()
    def close_waveform(self):self.closed=True
    def setValue(self,value):
        if not self.dragging:self.position=max(0,min(1,value/100000));self.update()
    def value(self):return round(self.position*100000)
    def isSliderDown(self):return self.dragging
    def time_for(self,x):return max(0,min(1,(x-10)/max(1,self.width()-20)))*self.owner.model.duration
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor(CANVAS));p.setPen(QColor('#8fa8bf'));p.setFont(QFont('Segoe UI',8));p.drawText(QRectF(12,3,self.width()-24,20),Qt.AlignmentFlag.AlignVCenter,self.message)
        model=self.owner.model
        if not model:return
        left,width,top,bottom=10,max(1,self.width()-20),48 if self.large else 27,self.height()-9
        if self.large:
            for time,x,label in visible_ticks(model.duration,left,width,event.rect().left(),event.rect().right()):
                p.drawText(QRectF(max(0,min(self.width()-56,x-28)),23,56,20),Qt.AlignmentFlag.AlignCenter,label)
        lanes=max(1,len(self.peaks));height=(bottom-top)/lanes
        for lane,peaks in enumerate(self.peaks):
            center=top+(lane+.5)*height;p.setPen(QPen(QColor('#7ed9ba' if lane==0 else '#74b8ee'),1))
            p.drawLine(left,round(center),left+width,round(center))
            for pixel in range(max(0,event.rect().left()-left),min(width,event.rect().right()-left+1)):
                a=int(pixel/width*len(peaks));b=max(a+1,int((pixel+1)/width*len(peaks)));amplitude=max(peaks[a:b],default=0.);extent=max(.5,min(1.,amplitude*self.display_gain)*(height/2-3))
                p.drawLine(left+pixel,round(center-extent),left+pixel,round(center+extent))
        for index,(start,end,keep) in enumerate(model.segments):
            rect=QRectF(left+width*start/model.duration,top,width*(end-start)/model.duration,bottom-top)
            if not keep:paint_excluded(p,rect)
            elif index==self.selected_segment:p.fillRect(rect,QColor(255,190,138,22))
            if index==self.selected_segment:
                p.setPen(QPen(QColor('#ffbe83'),2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(rect.adjusted(1,1,-1,-1),4,4)
        p.setPen(QPen(QColor('#ffbe83'),1))
        for cut in model.cuts:
            x=round(left+width*cut/model.duration);p.drawLine(x,top,x,bottom)
        x=round(left+width*self.position);p.setPen(QPen(QColor('#f3f8ff'),2));p.drawLine(x,23,x,self.height()-2);p.end()
    def mousePressEvent(self,event):
        if not self.owner.model or event.button()!=Qt.MouseButton.LeftButton:return
        time=self.time_for(event.position().x());self.position=time/self.owner.model.duration;self.dragging=True
        for i,(start,end,_) in enumerate(self.owner.model.segments):
            if start<=time<end or time==self.owner.model.duration and i==len(self.owner.model.segments)-1:self.selected_segment=i;self.segmentSelected.emit(i);break
        self.seekRequested.emit(time);self.update()
    def mouseMoveEvent(self,event):
        if self.dragging and self.owner.model:self.position=self.time_for(event.position().x())/self.owner.model.duration;self.update()
    def mouseReleaseEvent(self,event):
        if self.dragging:self.dragging=False;self.seekRequested.emit(self.time_for(event.position().x()));self.update()
