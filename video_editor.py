from pathlib import Path
import threading
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QUrl,QTimer,QRectF
from PySide6.QtGui import QPainter,QColor,QPixmap,QTransform,QShortcut,QKeySequence
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QVideoSink
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QSlider,QListWidget,QListWidgetItem,QSplitter,QMessageBox,QCheckBox
from app_ui import STYLE
from edit_models import CutModel,read_frame
from image_editor import pil_qimage
from filetypes import backend
from filmstrip import Filmstrip


def stamp(seconds):
    milliseconds=round(max(0,seconds)*1000);hours,remainder=divmod(milliseconds,3600000);minutes,remainder=divmod(remainder,60000);seconds,millis=divmod(remainder,1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{millis:03}'

class VideoCanvas(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumSize(440,280);self.image=None;self.angle=0
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#0e1118'))
        if self.image and not self.image.isNull():
            pixmap=QPixmap.fromImage(self.image)
            if self.angle:pixmap=pixmap.transformed(QTransform().rotate(self.angle),Qt.TransformationMode.SmoothTransformation)
            size=pixmap.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio);left=(self.width()-size.width())//2;top=(self.height()-size.height())//2
            painter.drawPixmap(left,top,size.width(),size.height(),pixmap)

class Timeline(QSlider):
    def __init__(self,owner):super().__init__(Qt.Orientation.Horizontal);self.owner=owner;self.setRange(0,100000);self.setMinimumHeight(36)
    def paintEvent(self,event):
        super().paintEvent(event);model=self.owner.model
        if not model:return
        painter=QPainter(self);width=max(1,self.width()-18)
        for start,end,keep in model.segments:
            left=9+width*start/model.duration;right=9+width*end/model.duration
            painter.fillRect(QRectF(left,1,max(1,right-left),5),QColor('#72cdae' if keep else '#e3747e'))
        painter.setPen(QColor('#ffc37d'))
        for position in model.cuts:
            x=int(9+width*position/model.duration);painter.drawLine(x,0,x,self.height()-1)

class FrameSignals(QObject):done=Signal(object,object)
class FrameJob(QRunnable):
    def __init__(self,path,position,steps,stopped):
        super().__init__();self.path,self.position,self.steps,self.stopped=path,position,steps,stopped;self.signals=FrameSignals()
    def run(self):
        try:
            image,position,duration=read_frame(self.path,self.position,self.steps,self.stopped)
            self.signals.done.emit((pil_qimage(image),position,duration),None)
        except Exception as error:self.signals.done.emit(None,str(error))

class VideoEditor(QDialog):
    def __init__(self,path,submit,parent=None):
        super().__init__(parent);self.path=str(path);self.submit=submit;self.position=0.;self.model=None;self.angle=0;self.manual=True
        self.frame_job=None;self.pending_steps=0;self.pending_seek=None;self.stopped=threading.Event();self.add_when_ready=False;self.shortcuts=[];self.updating_lists=False
        self.setWindowTitle('OrbitDrop · Videoschnitt · '+Path(path).name);self.resize(1180,800);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);splitter=QSplitter();layout.addWidget(splitter,1)
        self.canvas=VideoCanvas();splitter.addWidget(self.canvas)
        side=QWidget();side_layout=QVBoxLayout(side);side_layout.addWidget(QLabel('SCHNITTMARKEN'))
        self.marks=QListWidget();self.marks.setMaximumWidth(340);self.marks.itemDoubleClicked.connect(self.go_to_mark);side_layout.addWidget(self.marks)
        remove=QPushButton('Marke entfernen (Entf)');remove.clicked.connect(self.remove_cut);side_layout.addWidget(remove)
        side_layout.addWidget(QLabel('ABSCHNITTE · Haken = behalten'))
        self.segments=QListWidget();self.segments.itemChanged.connect(self.segment_changed);self.segments.itemDoubleClicked.connect(self.go_to_segment);self.segments.currentRowChanged.connect(self.select_segment);side_layout.addWidget(self.segments)
        splitter.addWidget(side);splitter.setSizes([830,320])
        self.timeline=Filmstrip(self);layout.addWidget(self.timeline);self.timeline.seekRequested.connect(self.seek);self.timeline.segmentSelected.connect(self.select_segment)
        segment_row=QHBoxLayout();layout.addLayout(segment_row)
        self.selected_label=QLabel('Abschnitt in der Videoleiste anklicken');segment_row.addWidget(self.selected_label,1)
        self.remove_segment_button=QPushButton('Abschnitt entfernen');self.remove_segment_button.setEnabled(False);self.remove_segment_button.clicked.connect(lambda:self.set_selected_keep(False));segment_row.addWidget(self.remove_segment_button)
        self.restore_segment_button=QPushButton('Wiederherstellen');self.restore_segment_button.setEnabled(False);self.restore_segment_button.clicked.connect(lambda:self.set_selected_keep(True));segment_row.addWidget(self.restore_segment_button)
        self.time_label=QLabel('Video wird geöffnet …');layout.addWidget(self.time_label)
        controls=QHBoxLayout();layout.addLayout(controls)
        self.play=QPushButton('▶ / Pause · Leertaste');self.play.clicked.connect(self.toggle_play);controls.addWidget(self.play)
        previous=QPushButton('← Einzelbild');previous.clicked.connect(lambda:self.step(-1));controls.addWidget(previous)
        following=QPushButton('Einzelbild →');following.clicked.connect(lambda:self.step(1));controls.addWidget(following)
        self.cut_button=QPushButton('Schnitt setzen · C');self.cut_button.clicked.connect(self.add_cut);controls.addWidget(self.cut_button)
        for label,angle in [('↶ 90°',-90),('↷ 90°',90),('180°',180)]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,a=angle:self.rotate(a));controls.addWidget(button)
        hint=QLabel('Leertaste: Start/Pause · ←/→: echtes Einzelbild · C: Schnittmarke · Entf: gewählte Marke entfernen. Abschnitt in der Videoleiste anklicken und „Abschnitt entfernen“ drücken.');hint.setWordWrap(True);layout.addWidget(hint)
        self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status)
        bottom=QHBoxLayout();layout.addLayout(bottom);self.separate=QCheckBox('Behaltene Abschnitte als einzelne Videos');bottom.addWidget(self.separate);bottom.addStretch()
        self.export=QPushButton('Auswahl als MP4 speichern');self.export.clicked.connect(self.save);bottom.addWidget(self.export)
        close=QPushButton('Schließen');close.clicked.connect(self.reject);bottom.addWidget(close)
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio);self.sink=QVideoSink(self);self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.video_frame);self.player.errorOccurred.connect(lambda error,message:self.status.setText('Wiedergabe: '+message+' · Einzelbildvorschau ist unabhängig davon verfügbar.'))
        self.player.setSource(QUrl.fromLocalFile(self.path))
        self._shortcut('Space',self.toggle_play);self._shortcut('Left',lambda:self.step(-1));self._shortcut('Right',lambda:self.step(1));self._shortcut('C',self.add_cut);self._shortcut('Delete',self.remove_cut)
        self.export.setEnabled(False);self.cut_button.setEnabled(False)
        self.seek(0)
    def _shortcut(self,key,callback):
        shortcut=QShortcut(QKeySequence(key),self);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);shortcut.setAutoRepeat(key in ('Left','Right'));shortcut.activated.connect(callback);self.shortcuts.append(shortcut)
    def decode(self,position,steps=0):
        if self.frame_job:
            if steps:self.pending_steps+=steps
            else:self.pending_seek=position;self.pending_steps=0
            return
        job=FrameJob(self.path,position,steps,self.stopped);self.frame_job=job
        self.status.setText('Einzelbild wird dekodiert …');job.signals.done.connect(self.decoded);QThreadPool.globalInstance().start(job)
    def decoded(self,result,error):
        self.frame_job=None
        if self.stopped.is_set():return
        if error:
            self.status.setText('Vorschau: '+error);self.add_when_ready=False
        elif result:
            image,position,duration=result;self.canvas.image=image;self.canvas.update();self.position=position
            if self.model is None:self.model=CutModel(duration);self.refresh_lists();self.timeline.load(self.path,duration,self.stopped)
            self.player.setPosition(round(position*1000));self.cut_button.setEnabled(True)
            self.export.setEnabled(bool(backend('ffmpeg') and backend('ffprobe')))
            self.status.setText('Einzelbild bereit.' if self.export.isEnabled() else 'Export benötigt FFmpeg/FFprobe. Im Kreis: Tools → Programm → Konverter.')
            self.update_time()
        if self.pending_seek is not None:
            target=self.pending_seek;self.pending_seek=None;self.decode(target);return
        if self.pending_steps:
            steps=self.pending_steps;self.pending_steps=0;self.decode(self.position,steps);return
        if self.add_when_ready and not error:self.add_when_ready=False;self.add_cut()
    def seek(self,position):
        self.player.pause();self.manual=True;self.decode(position)
    def step(self,steps):
        self.player.pause();self.manual=True
        self.decode(self.position,steps)
    def toggle_play(self):
        if self.frame_job:return
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause();self.manual=True;self.decode(self.position)
        else:
            if not self.model:return
            self.manual=False
            if self.player.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia:self.position=0
            next_position=self.kept_position(self.position)
            if next_position is None:return
            self.position=next_position;self.player.setPosition(round(self.position*1000));self.player.play()
    def video_frame(self,frame):
        if self.manual or not frame.isValid():return
        position=max(0,frame.startTime()/1_000_000) if frame.startTime()>=0 else self.player.position()/1000
        next_position=self.kept_position(position)
        if next_position is None:self.player.pause();return
        if next_position>position+1e-6:self.player.setPosition(round(next_position*1000));return
        image=frame.toImage()
        if image.isNull():return
        rotation=frame.rotation().value if hasattr(frame,'rotation') else 0
        if rotation:image=image.transformed(QTransform().rotate(rotation))
        if hasattr(frame,'mirrored') and frame.mirrored():image=image.mirrored(True,False)
        self.canvas.image=image;self.canvas.update()
        self.position=max(0,frame.startTime()/1_000_000) if frame.startTime()>=0 else self.player.position()/1000
        self.update_time()
    def update_time(self):
        if not self.model:return
        self.time_label.setText(stamp(self.position)+' / '+stamp(self.model.duration)+f' · Drehung {self.angle}°')
        if not self.timeline.isSliderDown():self.timeline.setValue(round(min(1,self.position/self.model.duration)*100000))
    def kept_position(self,position):
        if not self.model:return position
        for start,end,keep in self.model.segments:
            if keep and position<end-1e-6:return max(start,position)
        return None
    def select_segment(self,index):
        if self.updating_lists or not self.model or not 0<=index<len(self.model.segments):return
        self.timeline.selected_segment=index
        if self.segments.currentRow()!=index:self.segments.setCurrentRow(index)
        start,end,keep=self.model.segments[index]
        self.selected_label.setText(f'Abschnitt {index+1} · {stamp(start)} – {stamp(end)}'+(' · entfernt' if not keep else ''))
        self.remove_segment_button.setEnabled(keep);self.restore_segment_button.setEnabled(not keep);self.timeline.update()
    def set_selected_keep(self,keep):
        index=self.timeline.selected_segment
        if not self.model or not 0<=index<len(self.model.segments):return
        self.player.pause();self.model.keep(index,keep);self.refresh_lists();self.select_segment(index)
        self.status.setText('Abschnitt wiederhergestellt.' if keep else 'Abschnitt entfernt. Er wird bei Wiedergabe und Export übersprungen; das Original bleibt erhalten.')
    def add_cut(self):
        if self.frame_job:self.add_when_ready=True;return
        if not self.model:return
        if not self.manual:
            self.player.pause();self.manual=True;self.add_when_ready=True;self.decode(self.position);return
        if self.model.add(self.position):self.refresh_lists();self.select_segment(next(i for i,(start,end,_) in enumerate(self.model.segments) if start<=self.position<end));self.status.setText('Schnittmarke bei '+stamp(self.position)+' gesetzt.')
        else:self.status.setText('Hier ist bereits eine Marke oder der Anfang/das Ende.')
    def remove_cut(self):
        if not self.model:return
        index=self.marks.currentRow()
        if index<0:return
        self.model.remove(index);self.refresh_lists();self.status.setText('Marke entfernt. Zusammengeführte Abschnitte und Behalten-Auswahl prüfen.')
    def refresh_lists(self):
        if not self.model:return
        self.updating_lists=True;self.marks.clear();self.segments.clear()
        for position in self.model.cuts:self.marks.addItem(stamp(position))
        for index,(start,end,keep) in enumerate(self.model.segments):
            item=QListWidgetItem(f'{index+1} · {stamp(start)} – {stamp(end)}');item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if keep else Qt.CheckState.Unchecked);self.segments.addItem(item)
        self.updating_lists=False;self.timeline.update()
        index=self.timeline.selected_segment
        if index>=0:self.select_segment(min(index,len(self.model.segments)-1))
    def segment_changed(self,item):
        if self.updating_lists or not self.model:return
        index=self.segments.row(item);self.model.keep(index,item.checkState()==Qt.CheckState.Checked);self.select_segment(index);self.timeline.update()
    def go_to_mark(self,item):
        if self.model:self.seek(self.model.cuts[self.marks.row(item)])
    def go_to_segment(self,item):
        if self.model:self.seek(self.model.segments[self.segments.row(item)][0])
    def rotate(self,angle):self.angle=(self.angle+angle)%360;self.canvas.angle=self.angle;self.canvas.update();self.update_time()
    def save(self):
        if not self.model or self.frame_job:return
        ranges=self.model.ranges()
        if not ranges:QMessageBox.information(self,'Videoschnitt','Bitte mindestens einen Abschnitt behalten.');return
        self.player.pause();self.submit('Video bearbeiten',[self.path],{'ranges':ranges,'angle':self.angle,'separate':self.separate.isChecked()});self.accept()
    def done(self,result):
        self.stopped.set();self.player.stop();self.player.setSource(QUrl());super().done(result)
