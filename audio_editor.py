"""Audio cutting shares the existing cut model and timeline, no second downloader cutter."""
from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QListWidget,QListWidgetItem,QCheckBox,QMessageBox
from app_ui import STYLE
from edit_models import CutModel
from video_editor import Timeline,stamp
from filetypes import backend

class AudioEditor(QDialog):
    def __init__(self,path,submit):
        super().__init__();self.path=str(path);self.submit=submit;self.model=None;self.updating_lists=False;self.shortcuts=[]
        self.setWindowTitle('OrbitDrop · Audioschnitt · '+Path(path).name);self.resize(800,600);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);layout.addWidget(QLabel(Path(path).name))
        self.time_label=QLabel('Audio wird geöffnet …');layout.addWidget(self.time_label)
        self.timeline=Timeline(self);layout.addWidget(self.timeline);self.timeline.sliderReleased.connect(lambda:self.seek(self.timeline.value()/100000*self.model.duration) if self.model else None)
        controls=QHBoxLayout();layout.addLayout(controls)
        for label,callback in [('▶ / Pause · Leertaste',self.toggle_play),('← 0,1 s',lambda:self.step(-.1)),('0,1 s →',lambda:self.step(.1)),('Schnitt setzen · C',self.add_cut)]:
            button=QPushButton(label);button.clicked.connect(callback);controls.addWidget(button)
        layout.addWidget(QLabel('SCHNITTMARKEN · Doppelklick springt zur Marke'))
        self.marks=QListWidget();self.marks.itemDoubleClicked.connect(lambda item:self.seek(self.model.cuts[self.marks.row(item)]));layout.addWidget(self.marks)
        remove=QPushButton('Gewählte Marke entfernen · Entf');remove.clicked.connect(self.remove_cut);layout.addWidget(remove)
        layout.addWidget(QLabel('ABSCHNITTE · Haken = behalten'))
        self.segments=QListWidget();self.segments.itemChanged.connect(self.changed);self.segments.itemDoubleClicked.connect(lambda item:self.seek(self.model.segments[self.segments.row(item)][0]));layout.addWidget(self.segments)
        self.separate=QCheckBox('Abschnitte als einzelne Audiodateien speichern');layout.addWidget(self.separate)
        self.status=QLabel('Leertaste: Start/Pause · ←/→: 0,1 Sekunden · C: Marke · Entf: Marke entfernen');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.export=QPushButton('Auswahl als MP3 speichern');self.export.setEnabled(False);self.export.clicked.connect(self.save);layout.addWidget(self.export)
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio)
        self.player.durationChanged.connect(self.duration_changed);self.player.positionChanged.connect(self.update_time);self.player.errorOccurred.connect(lambda error,message:self.status.setText('Wiedergabe: '+message))
        for key,callback in [('Space',self.toggle_play),('Left',lambda:self.step(-.1)),('Right',lambda:self.step(.1)),('C',self.add_cut),('Delete',self.remove_cut)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);shortcut.setAutoRepeat(key in ('Left','Right'));shortcut.activated.connect(callback);self.shortcuts.append(shortcut)
        self.player.setSource(QUrl.fromLocalFile(self.path))
    def duration_changed(self,milliseconds):
        if milliseconds<=0 or self.model:return
        self.model=CutModel(milliseconds/1000);self.refresh_lists();self.update_time()
        self.export.setEnabled(bool(backend('ffmpeg') and backend('ffprobe')))
        if not self.export.isEnabled():self.status.setText('Export benötigt FFmpeg und FFprobe: Tools → Programm → Konverter.')
    def update_time(self,*unused):
        if not self.model:return
        position=self.player.position()/1000;self.time_label.setText(stamp(position)+' / '+stamp(self.model.duration))
        if not self.timeline.isSliderDown():self.timeline.setValue(round(position/self.model.duration*100000))
    def seek(self,position):self.player.pause();self.player.setPosition(round(max(0,min(position,self.model.duration))*1000))
    def step(self,amount):
        if self.model:self.seek(self.player.position()/1000+amount)
    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
        else:
            if self.player.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia:self.player.setPosition(0)
            self.player.play()
    def add_cut(self):
        self.player.pause()
        if self.model and self.model.add(self.player.position()/1000):self.refresh_lists()
    def remove_cut(self):
        if self.model and self.marks.currentRow()>=0:
            self.model.remove(self.marks.currentRow());self.refresh_lists();self.status.setText('Marke entfernt. Behalten-Auswahl prüfen.')
    def refresh_lists(self):
        self.updating_lists=True;self.marks.clear();self.segments.clear()
        for cut in self.model.cuts:self.marks.addItem(stamp(cut))
        for start,end,keep in self.model.segments:
            item=QListWidgetItem(stamp(start)+' – '+stamp(end));item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if keep else Qt.CheckState.Unchecked);self.segments.addItem(item)
        self.updating_lists=False;self.timeline.update()
    def changed(self,item):
        if not self.updating_lists:self.model.keep(self.segments.row(item),item.checkState()==Qt.CheckState.Checked);self.timeline.update()
    def save(self):
        if not self.model or not self.model.ranges():QMessageBox.information(self,'Audioschnitt','Bitte mindestens einen Abschnitt behalten.');return
        self.player.pause();self.submit('Audio bearbeiten',[self.path],{'ranges':self.model.ranges(),'separate':self.separate.isChecked()});self.accept()
    def done(self,result):self.player.stop();self.player.setSource(QUrl());super().done(result)
