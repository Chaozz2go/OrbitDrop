"""Clickable clip strip; source time stays stable when a segment is excluded."""
from PySide6.QtCore import Qt,QRectF,QPointF,QObject,Signal,QRunnable,QThreadPool
from PySide6.QtGui import QPainter,QColor,QPen,QFont,QPixmap
from PySide6.QtWidgets import QWidget
from edit_models import read_frame
from image_editor import pil_qimage
from ui_theme import CANVAS,paint_excluded

class ThumbnailSignals(QObject):ready=Signal(int,object)
class ThumbnailJob(QRunnable):
    def __init__(self,path,duration,stopped,count=14):
        super().__init__();self.path,self.duration,self.stopped,self.count=path,duration,stopped,count;self.signals=ThumbnailSignals()
    def run(self):
        for index in range(self.count):
            if self.stopped.is_set():return
            try:
                image,_,_=read_frame(self.path,self.duration*(index+.5)/self.count,stopped=self.stopped)
                image.thumbnail((180,100))
                if self.stopped.is_set():return
                self.signals.ready.emit(index,pil_qimage(image))
            except Exception:return

class Filmstrip(QWidget):
    seekRequested=Signal(float)
    segmentSelected=Signal(int)
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.position=0;self.selected_segment=-1;self.thumbnails={};self.count=14;self.dragging=False;self.thumbnail_job=None
        self.setMinimumHeight(128);self.setMaximumHeight(128);self.setMouseTracking(True);self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setToolTip('Abschnitt anklicken → Entf. Obere Zeitleiste ziehen: im Video springen.')
    def load(self,path,duration,stopped):
        if self.thumbnail_job:return
        job=ThumbnailJob(path,duration,stopped,self.count);self.thumbnail_job=job
        job.signals.ready.connect(self.thumbnail_ready);QThreadPool.globalInstance().start(job)
    def thumbnail_ready(self,index,image):
        if self.owner.stopped.is_set():return
        self.thumbnails[index]=image;self.update()
    def isSliderDown(self):return self.dragging
    def setValue(self,value):self.position=max(0,min(1,value/100000));self.update()
    def x_for(self,time):return 10+(self.width()-20)*time/self.owner.model.duration
    def time_for(self,x):return max(0,min(self.owner.model.duration,(x-10)/max(1,self.width()-20)*self.owner.model.duration))
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.fillRect(self.rect(),QColor(CANVAS))
        model=self.owner.model
        if not model:
            painter.setPen(QColor('#aab4c9'));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Videoleiste wird geladen …');return
        left,width=10,max(1,self.width()-20);top,height=30,88
        painter.setFont(QFont('Segoe UI',8));painter.setPen(QColor('#b7c1d4'))
        for tick in range(9):
            seconds=model.duration*tick/8;x=left+width*tick/8
            label=f'{int(seconds//60):02}:{seconds%60:04.1f}'
            painter.drawText(QRectF(max(0,min(self.width()-56,x-28)),2,56,22),Qt.AlignmentFlag.AlignCenter,label)
        painter.setClipRect(QRectF(left,top,width,height))
        for index in range(self.count):
            rect=QRectF(left+width*index/self.count,top,width/self.count+1,height)
            if index in self.thumbnails:
                pixmap=QPixmap.fromImage(self.thumbnails[index]);size=pixmap.size().scaled(int(rect.width()),height,Qt.AspectRatioMode.KeepAspectRatioByExpanding)
                pixmap=pixmap.scaled(size,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                painter.save();painter.setClipRect(rect);painter.drawPixmap(int(rect.center().x()-pixmap.width()/2),top,pixmap);painter.restore()
            else:painter.fillRect(rect,QColor('#293447'))
        painter.setClipping(False)
        for index,(start,end,keep) in enumerate(model.segments):
            rect=QRectF(self.x_for(start),top,max(1,self.x_for(end)-self.x_for(start)),height)
            if not keep:paint_excluded(painter,rect)
            elif index==self.selected_segment:painter.fillRect(rect,QColor(255,190,138,22))
            painter.setPen(QPen(QColor('#ffbe83' if index==self.selected_segment else '#7ed9ba' if keep else '#db7584'),3 if index==self.selected_segment else 1))
            painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRect(rect.adjusted(1,1,-1,-1))
            if rect.width()>42:
                label=f'{index+1}' if keep else 'Entfernt';painter.fillRect(QRectF(rect.left()+3,top+height-24,min(rect.width()-6,78),20),QColor(10,14,22,200));painter.drawText(rect.adjusted(6,62,-4,0),Qt.AlignmentFlag.AlignLeft,label)
        x=left+width*self.position;painter.setPen(QPen(QColor('#ffffff'),2));painter.drawLine(int(x),24,int(x),125)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#f2f7ff'));painter.drawPolygon([QPointF(x-5,23),QPointF(x+5,23),QPointF(x,29)])
    def mousePressEvent(self,event):
        if not self.owner.model or event.button()!=Qt.MouseButton.LeftButton:return
        time=self.time_for(event.position().x())
        if 30<=event.position().y()<=118:
            for index,(start,end,_) in enumerate(self.owner.model.segments):
                if start<=time<end or time==self.owner.model.duration and index==len(self.owner.model.segments)-1:
                    self.selected_segment=index;self.segmentSelected.emit(index);break
            self.seekRequested.emit(time)
        elif event.position().y()<30:self.dragging=True;self.seekRequested.emit(time)
        self.update()
    def mouseMoveEvent(self,event):
        if self.dragging and self.owner.model:self.position=self.time_for(event.position().x())/self.owner.model.duration;self.update()
    def mouseReleaseEvent(self,event):
        if self.dragging:self.dragging=False;self.seekRequested.emit(self.time_for(event.position().x()))
