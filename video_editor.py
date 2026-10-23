from pathlib import Path
import threading
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QUrl,QTimer,QRectF
from PySide6.QtGui import QPainter,QColor,QPixmap,QTransform,QShortcut,QKeySequence,QPainterPath
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QVideoSink
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QSlider,QListWidget,QListWidgetItem,QSplitter,QMessageBox,QCheckBox,QMenu
from editor_chrome import EDITOR_STYLE,heading,toolbar,action_button
from ui_theme import CANVAS,BACKGROUND,icon
from waveform import Waveform
from timeline_view import TimelineView
from edit_models import CutModel,FrameReader
from preview_runtime import preview_pool
from loading_ui import LoadingIndicator
from image_editor import pil_qimage
from filetypes import backend
from filmstrip import Filmstrip


def stamp(seconds):
    milliseconds=round(max(0,seconds)*1000);hours,remainder=divmod(milliseconds,3600000);minutes,remainder=divmod(remainder,60000);seconds,millis=divmod(remainder,1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{millis:03}'

class VideoCanvas(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumSize(400,170);self.image=None;self.angle=0
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.fillRect(self.rect(),QColor(BACKGROUND));clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),12,12);painter.fillPath(clip,QColor(CANVAS));painter.setClipPath(clip)
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
    def __init__(self,reader,position,steps,stopped):
        super().__init__();self.reader,self.position,self.steps,self.stopped=reader,position,steps,stopped;self.signals=FrameSignals()
    def run(self):
        try:
            image,position,duration=self.reader.read(self.position,self.steps,self.stopped)
            self.signals.done.emit((pil_qimage(image),position,duration),None)
        except Exception as error:self.signals.done.emit(None,str(error))
        finally:
            if self.stopped.is_set():self.reader.close()

class VideoEditor(QDialog):
    def __init__(self,path,submit,parent=None):
        super().__init__(parent);self.path=str(path);self.submit=submit;self.position=0.;self.model=None;self.angle=0;self.manual=True
        self.reader=FrameReader(path);self.wave_finished=False;self.wave_percent=None
        self.frame_job=None;self.pending_steps=0;self.pending_seek=None;self.stopped=threading.Event();self.add_when_ready=False;self.shortcuts=[];self.updating_lists=False
        self.setWindowTitle('OrbitDrop · Videoschnitt · '+Path(path).name);self.resize(1180,900);self.setStyleSheet(EDITOR_STYLE)
        layout=QVBoxLayout(self);heading(layout,'Videoschnitt',Path(path).name+' · Leertaste: Start/Pause · C: Schnitt · Entf: Entfernen')
        self.canvas=VideoCanvas();layout.addWidget(self.canvas,1)
        self.loading=LoadingIndicator();self.loading.busy('Video wird geöffnet …');layout.addWidget(self.loading)
        bar,controls=toolbar();layout.addWidget(bar)
        self.play=action_button('', 'play',True,'Start / Pause · Leertaste');self.play.setFixedWidth(48);self.play.clicked.connect(self.toggle_play);controls.addWidget(self.play)
        for kind,label,step in [('previous','Einzelbild zurück · ←',-1),('next','Einzelbild vor · →',1)]:
            button=action_button('',kind,tooltip=label);button.setFixedWidth(38);button.clicked.connect(lambda checked=False,n=step:self.step(n));controls.addWidget(button)
        self.cut_button=action_button('Schnitt C','cut');self.cut_button.clicked.connect(self.add_cut);controls.addWidget(self.cut_button)
        self.remove_segment_button=action_button('Entfernen Entf','delete');self.remove_segment_button.setEnabled(False);self.remove_segment_button.clicked.connect(lambda:self.set_selected_keep(False));controls.addWidget(self.remove_segment_button)
        self.restore_segment_button=action_button('Wiederherstellen','undo',tooltip='Entfernten Abschnitt wiederherstellen');self.restore_segment_button.setEnabled(False);self.restore_segment_button.clicked.connect(lambda:self.set_selected_keep(True));controls.addWidget(self.restore_segment_button)
        controls.addStretch();self.time_label=QLabel('Video wird geöffnet …');self.time_label.setObjectName('timeReadout');controls.addWidget(self.time_label)
        self.timeline=Filmstrip(self);self.timeline.seekRequested.connect(self.seek);self.timeline.segmentSelected.connect(self.select_segment)
        self.waveform=Waveform(self);self.timeline.loadingChanged.connect(self.update_loading);self.waveform.loadingProgress.connect(self.wave_progress);self.waveform.finished.connect(self.wave_ready);self.timeline_view=TimelineView([self.timeline,self.waveform]);layout.addWidget(self.timeline_view);self.waveform.seekRequested.connect(self.seek);self.waveform.segmentSelected.connect(self.select_segment)
        segment_row=QHBoxLayout();layout.addLayout(segment_row)
        self.undo_button=action_button('','undo',tooltip='Schnittschritt rückgängig · Strg+Z');self.undo_button.clicked.connect(lambda:self.history_step(False));self.timeline_view.controls.addWidget(self.undo_button)
        self.redo_button=action_button('','rotate_right',tooltip='Schnittschritt wiederholen · Strg+Y');self.redo_button.clicked.connect(lambda:self.history_step(True));self.timeline_view.controls.addWidget(self.redo_button)
        self.selected_label=QLabel('Abschnitt in einer Spur anklicken');segment_row.addWidget(self.selected_label,1)
        self.compact_time=QLabel('');self.compact_time.setObjectName('timeReadout');segment_row.addWidget(self.compact_time)
        self.details_button=QPushButton('Marken && Abschnitte');self.details_button.setCheckable(True);segment_row.addWidget(self.details_button)
        rotation=QPushButton('Drehen');rotation.setToolTip('Video drehen');rotation_menu=QMenu(rotation)
        for title,angle in [('90° links',-90),('90° rechts',90),('180°',180)]:rotation_menu.addAction(title).triggered.connect(lambda checked=False,n=angle:self.rotate(n))
        rotation.setMenu(rotation_menu);segment_row.addWidget(rotation)
        self.details=QWidget();self.details.setObjectName('editorControls');details_layout=QHBoxLayout(self.details);details_layout.setContentsMargins(12,10,12,10)
        mark_column=QVBoxLayout();details_layout.addLayout(mark_column,1);mark_column.addWidget(QLabel('SCHNITTMARKEN'))
        self.marks=QListWidget();self.marks.setMinimumHeight(40);self.marks.itemDoubleClicked.connect(self.go_to_mark);mark_column.addWidget(self.marks)
        remove=action_button('Marke entfernen · Shift+Entf','delete');remove.clicked.connect(self.remove_cut);mark_column.addWidget(remove)
        segment_column=QVBoxLayout();details_layout.addLayout(segment_column,2);segment_column.addWidget(QLabel('ABSCHNITTE · Haken = behalten'))
        self.segments=QListWidget();self.segments.setMinimumHeight(50);self.segments.itemChanged.connect(self.segment_changed);self.segments.itemDoubleClicked.connect(self.go_to_segment);self.segments.currentRowChanged.connect(self.select_segment);segment_column.addWidget(self.segments)
        self.details.setMaximumHeight(160);layout.addWidget(self.details);self.details.hide();self.details_button.toggled.connect(self.details.setVisible)
        self.status=QLabel('');self.status.setObjectName('editorSubtitle');self.status.setWordWrap(True);layout.addWidget(self.status)
        bottom=QHBoxLayout();layout.addLayout(bottom);self.separate=QCheckBox('Als einzelne Clips');bottom.addWidget(self.separate);bottom.addStretch()
        close=action_button('Schließen');close.clicked.connect(self.reject);bottom.addWidget(close)
        self.export=action_button('Als MP4 speichern','save',True);self.export.clicked.connect(self.save);bottom.addWidget(self.export)
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio);self.sink=QVideoSink(self);self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.video_frame);self.player.errorOccurred.connect(lambda error,message:self.status.setText('Wiedergabe: '+message+' · Einzelbildvorschau ist unabhängig davon verfügbar.'))
        self._shortcut('Ctrl+Z',lambda:self.history_step(False));self._shortcut('Ctrl+Y',lambda:self.history_step(True));self._shortcut('Space',self.toggle_play);self._shortcut('Left',lambda:self.step(-1));self._shortcut('Right',lambda:self.step(1));self._shortcut('C',self.add_cut);self._shortcut('Delete',lambda:self.set_selected_keep(False));self._shortcut('Shift+Delete',self.remove_cut)
        self.export.setEnabled(False);self.cut_button.setEnabled(False)
        QTimer.singleShot(0,self.start_load)
        area=self.screen().availableGeometry();self.fit_toolbar(min(1180,area.width()-40));self.resize(min(1180,area.width()-40),min(900,area.height()-50))
    def start_load(self):
        if self.stopped.is_set():return
        self.player.setSource(QUrl.fromLocalFile(self.path));self.seek(0)
    def fit_toolbar(self,width):
        wide=width>=1280;self.time_label.setVisible(wide);self.compact_time.setVisible(not wide);self.restore_segment_button.setText('Wiederherstellen' if width>=850 else '')
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'compact_time'):self.fit_toolbar(self.width())

    def _shortcut(self,key,callback):
        shortcut=QShortcut(QKeySequence(key),self);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);shortcut.setAutoRepeat(key in ('Left','Right'));shortcut.activated.connect(callback);self.shortcuts.append(shortcut)
    def decode(self,position,steps=0):
        if self.frame_job:
            if steps:self.pending_steps+=steps
            else:self.pending_seek=position;self.pending_steps=0
            return
        job=FrameJob(self.reader,position,steps,self.stopped);self.frame_job=job
        self.status.setText('Einzelbild wird dekodiert …');job.signals.done.connect(self.decoded);preview_pool().start(job)
    def decoded(self,result,error):
        self.frame_job=None
        if self.stopped.is_set():return
        if error:
            self.status.setText('Vorschau: '+error);self.add_when_ready=False
            if self.model is None:self.loading.finish()
        elif result:
            image,position,duration=result;self.canvas.image=image;self.canvas.update();self.position=position
            if self.model is None:self.model=CutModel(duration);self.refresh_lists();self.timeline.load(self.path,duration,self.stopped);self.waveform.load(self.path,self.stopped,duration);self.update_loading()
            self.player.setPosition(round(position*1000));self.cut_button.setEnabled(True)
            self.export.setEnabled(bool(backend('ffmpeg') and backend('ffprobe')))
            self.status.setText('Einzelbild bereit.' if self.export.isEnabled() else 'Export benötigt FFmpeg/FFprobe. Im Kreis: Alt → Konverter.')
            self.update_time()
        if self.pending_seek is not None:
            target=self.pending_seek;self.pending_seek=None;self.decode(target);return
        if self.pending_steps:
            steps=self.pending_steps;self.pending_steps=0;self.decode(self.position,steps);return
        if self.add_when_ready and not error:self.add_when_ready=False;self.add_cut()
    def wave_progress(self,percent):self.wave_percent=percent;self.update_loading()
    def wave_ready(self):self.wave_finished=True;self.update_loading()
    def update_loading(self):
        if self.stopped.is_set() or self.model is None:return
        strip=self.timeline;count=len(strip.thumbnails)
        if strip.finished and self.wave_finished:
            self.loading.finish()
            if strip.error:self.status.setText('Videoleiste nicht vollständig: '+strip.error)
            return
        text=('Videoleiste nicht verfügbar' if strip.error else f'Videoleiste: {count} von {strip.count} Bildern · {round(count/strip.count*100)} %')
        text+=' · Audiospur: '+('bereit' if self.wave_finished else f'{self.wave_percent} %' if self.wave_percent is not None else 'wird geöffnet …')
        if not strip.finished:self.loading.progress(count/strip.count*100,text)
        elif self.wave_percent is not None:self.loading.progress(self.wave_percent,text)
        else:self.loading.busy(text)
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
        if self.stopped.is_set() or self.manual or not frame.isValid():return
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
        text=stamp(self.position)+' / '+stamp(self.model.duration);self.time_label.setText(text);self.compact_time.setText(text);self.time_label.setToolTip(f'Drehung {self.angle}°')
        value=round(min(1,self.position/self.model.duration)*100000)
        if not self.timeline.isSliderDown():self.timeline.setValue(value)
        self.waveform.setValue(value);self.timeline_view.follow() if not self.manual else None
    def kept_position(self,position):
        if not self.model:return position
        for start,end,keep in self.model.segments:
            if keep and position<end-1e-6:return max(start,position)
        return None
    def select_segment(self,index):
        if self.updating_lists or not self.model or not 0<=index<len(self.model.segments):return
        self.timeline.selected_segment=index;self.waveform.selected_segment=index;self.waveform.update()
        if self.segments.currentRow()!=index:self.segments.setCurrentRow(index)
        start,end,keep=self.model.segments[index]
        self.selected_label.setText(f'Abschnitt {index+1}'+(' · entfernt' if not keep else ''));self.selected_label.setToolTip(stamp(start)+' – '+stamp(end))
        self.remove_segment_button.setEnabled(keep);self.restore_segment_button.setEnabled(not keep);self.timeline.update()
    def set_selected_keep(self,keep):
        index=self.timeline.selected_segment
        if not self.model or not 0<=index<len(self.model.segments):return
        self.player.pause();self.manual=True;self.model.keep(index,keep);self.refresh_lists();self.select_segment(index)
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
        self.model.remove(index);self.refresh_lists();self.waveform.update();self.status.setText('Marke entfernt. Zusammengeführte Abschnitte und Behalten-Auswahl prüfen.')
    def history_step(self,redo=False):
        if not self.model:return
        self.player.pause();self.manual=True;self.add_when_ready=False
        changed=self.model.redo() if redo else self.model.undo()
        if changed:self.refresh_lists();self.status.setText('Schnittschritt wiederholt.' if redo else 'Schnittschritt rückgängig gemacht.')
    def refresh_lists(self):
        if not self.model:return
        self.undo_button.setEnabled(bool(self.model.undo_stack));self.redo_button.setEnabled(bool(self.model.redo_stack))
        self.updating_lists=True;self.marks.clear();self.segments.clear()
        for position in self.model.cuts:self.marks.addItem(stamp(position))
        for index,(start,end,keep) in enumerate(self.model.segments):
            item=QListWidgetItem(f'{index+1} · {stamp(start)} – {stamp(end)}');item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if keep else Qt.CheckState.Unchecked);self.segments.addItem(item)
        self.updating_lists=False;self.timeline.update();self.waveform.update()
        index=self.timeline.selected_segment
        if index>=0:self.select_segment(min(index,len(self.model.segments)-1))
    def segment_changed(self,item):
        if self.updating_lists or not self.model:return
        index=self.segments.row(item);self.model.keep(index,item.checkState()==Qt.CheckState.Checked);self.select_segment(index);self.timeline.update();self.waveform.update();self.undo_button.setEnabled(bool(self.model.undo_stack));self.redo_button.setEnabled(bool(self.model.redo_stack))
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
        if not self.stopped.is_set():
            self.stopped.set();self.waveform.close_waveform()
            if self.frame_job is None:self.reader.close()
            self.player.stop();self.player.setVideoSink(None);self.player.setAudioOutput(None)
            try:self.sink.videoFrameChanged.disconnect(self.video_frame)
            except (RuntimeError,TypeError):pass
            self.player.setSource(QUrl());self.player.deleteLater();self.sink.deleteLater();self.audio.deleteLater()
        super().done(result)
