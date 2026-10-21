"""Waveform-based audio cutting with the shared cut model."""
from pathlib import Path
import threading
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QListWidget,QListWidgetItem,QCheckBox,QMessageBox,QSplitter
from editor_chrome import EDITOR_STYLE,heading,toolbar,action_button
from edit_models import CutModel
from video_editor import stamp
from waveform import Waveform
from timeline_view import TimelineView
from filetypes import backend

class AudioEditor(QDialog):
    def __init__(self,path,submit):
        super().__init__();self.path=str(path);self.submit=submit;self.model=None;self.updating_lists=False;self.shortcuts=[];self.stopped=threading.Event()
        self.setWindowTitle('OrbitDrop · Audioschnitt · '+Path(path).name);self.resize(1050,780);self.setStyleSheet(EDITOR_STYLE)
        layout=QVBoxLayout(self);layout.setSpacing(10);heading(layout,'Audioschnitt',Path(path).name+' · Leertaste: Start/Pause · C: Schnitt · Entf: Abschnitt entfernen')
        self.timeline=Waveform(self,large=True);self.waveform=self.timeline;self.timeline_view=TimelineView([self.timeline]);layout.addWidget(self.timeline_view,2);self.timeline.seekRequested.connect(self.seek);self.timeline.segmentSelected.connect(self.select_segment);self.timeline.loaded.connect(self.waveform_loaded)
        self.undo_button=action_button('','undo',tooltip='Schnittschritt rückgängig · Strg+Z');self.undo_button.clicked.connect(lambda:self.history_step(False));self.timeline_view.controls.addWidget(self.undo_button)
        self.redo_button=action_button('','rotate_right',tooltip='Schnittschritt wiederholen · Strg+Y');self.redo_button.clicked.connect(lambda:self.history_step(True));self.timeline_view.controls.addWidget(self.redo_button)
        bar,controls=toolbar();layout.addWidget(bar)
        self.play=action_button('Abspielen','play',True,'Start / Pause · Leertaste');self.play.clicked.connect(self.toggle_play);controls.addWidget(self.play)
        for kind,title,amount in [('previous','0,1 Sekunden zurück · ←',-.1),('next','0,1 Sekunden vor · →',.1)]:
            button=action_button('',kind,tooltip=title);button.setFixedWidth(38);button.clicked.connect(lambda checked=False,n=amount:self.step(n));controls.addWidget(button)
        cut=action_button('Schnitt C','cut');cut.clicked.connect(self.add_cut);controls.addWidget(cut)
        self.remove_segment_button=action_button('Entfernen Entf','delete');self.remove_segment_button.setEnabled(False);self.remove_segment_button.clicked.connect(lambda:self.set_selected_keep(False));controls.addWidget(self.remove_segment_button)
        self.restore_segment_button=action_button('','undo',tooltip='Abschnitt wiederherstellen');self.restore_segment_button.setEnabled(False);self.restore_segment_button.clicked.connect(lambda:self.set_selected_keep(True));controls.addWidget(self.restore_segment_button)
        controls.addStretch();self.time_label=QLabel('Audio wird geöffnet …');self.time_label.setObjectName('timeReadout');layout.addWidget(self.time_label)
        panels=QSplitter();layout.addWidget(panels,1)
        for title,attribute in [('SCHNITTMARKEN','marks'),('ABSCHNITTE · Haken = behalten','segments')]:
            box=QWidget();box.setObjectName('editorControls');column=QVBoxLayout(box);column.addWidget(QLabel(title));items=QListWidget();items.setMinimumHeight(70);column.addWidget(items,1);setattr(self,attribute,items);panels.addWidget(box)
            if attribute=='marks':
                self.marks_box=box;remove=action_button('Marke entfernen · Shift+Entf','delete');remove.clicked.connect(self.remove_cut);column.addWidget(remove)
        self.marks_box.hide()
        self.marks.itemDoubleClicked.connect(lambda item:self.seek(self.model.cuts[self.marks.row(item)]) if self.model else None)
        self.segments.itemChanged.connect(self.changed);self.segments.currentRowChanged.connect(self.select_segment);self.segments.itemDoubleClicked.connect(lambda item:self.seek(self.model.segments[self.segments.row(item)][0]) if self.model else None)
        row=QHBoxLayout();layout.addLayout(row);self.selected_label=QLabel('Abschnitt in der Audiospur anklicken');row.addWidget(self.selected_label,1)
        details=QPushButton('Schnittmarken');details.setCheckable(True);details.toggled.connect(self.marks_box.setVisible);row.addWidget(details)
        self.status=QLabel('Audiospur anklicken oder ziehen, um die Position zu wählen.');self.status.setObjectName('editorSubtitle');self.status.setWordWrap(True);layout.addWidget(self.status)
        bottom=QHBoxLayout();layout.addLayout(bottom);self.separate=QCheckBox('Als einzelne Clips');bottom.addWidget(self.separate);bottom.addStretch()
        close=action_button('Schließen');close.clicked.connect(self.reject);bottom.addWidget(close)
        self.export=action_button('Als MP3 speichern','save',True);self.export.setEnabled(False);self.export.clicked.connect(self.save);bottom.addWidget(self.export)
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio)
        self.player.durationChanged.connect(self.duration_changed);self.player.positionChanged.connect(self.update_time);self.player.errorOccurred.connect(lambda error,message:self.status.setText('Wiedergabe: '+message) if not self.stopped.is_set() else None)
        for key,callback in [('Ctrl+Z',lambda:self.history_step(False)),('Ctrl+Y',lambda:self.history_step(True)),('Space',self.toggle_play),('Left',lambda:self.step(-.1)),('Right',lambda:self.step(.1)),('C',self.add_cut),('Delete',lambda:self.set_selected_keep(False)),('Shift+Delete',self.remove_cut)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);shortcut.setAutoRepeat(key in ('Left','Right'));shortcut.activated.connect(callback);self.shortcuts.append(shortcut)
        self.player.setSource(QUrl.fromLocalFile(self.path));self.timeline.load(self.path,self.stopped)
        area=self.screen().availableGeometry();self.resize(min(1050,area.width()-40),min(780,area.height()-50))
    def waveform_loaded(self,result):
        if not self.model and result['duration']>0:self.duration_changed(round(result['duration']*1000))
    def duration_changed(self,milliseconds):
        if milliseconds<=0 or self.model or self.stopped.is_set():return
        self.model=CutModel(milliseconds/1000);self.refresh_lists();self.update_time()
        self.export.setEnabled(bool(backend('ffmpeg') and backend('ffprobe')))
        if not self.export.isEnabled():self.status.setText('Export benötigt FFmpeg und FFprobe: Alt → Konverter.')
    def kept_position(self,position):
        if not self.model:return position
        for start,end,keep in self.model.segments:
            if keep and position<end-1e-6:return max(start,position)
        return None
    def update_time(self,*unused):
        if not self.model or self.stopped.is_set():return
        position=self.player.position()/1000
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:
            kept=self.kept_position(position)
            if kept is None:self.player.pause();return
            if kept>position+1e-6:self.player.setPosition(round(kept*1000));return
        self.time_label.setText(stamp(position)+' / '+stamp(self.model.duration));self.timeline.setValue(round(position/self.model.duration*100000))
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.timeline_view.follow()
    def seek(self,position):
        if not self.model or self.stopped.is_set():return
        self.player.pause();self.player.setPosition(round(max(0,min(position,self.model.duration))*1000));self.update_time()
    def step(self,amount):
        if self.model:self.seek(self.player.position()/1000+amount)
    def toggle_play(self):
        if not self.model:return
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
        else:
            position=0 if self.player.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia else self.player.position()/1000;position=self.kept_position(position)
            if position is not None:self.player.setPosition(round(position*1000));self.player.play()
    def add_cut(self):
        self.player.pause()
        if self.model and self.model.add(self.player.position()/1000):
            self.refresh_lists();position=self.player.position()/1000;self.select_segment(next(i for i,(start,end,_) in enumerate(self.model.segments) if start<=position<end))
    def remove_cut(self):
        if self.model and self.marks.currentRow()>=0:
            self.model.remove(self.marks.currentRow());self.refresh_lists();self.status.setText('Marke entfernt. Behalten-Auswahl prüfen.')
    def select_segment(self,index):
        if self.updating_lists or not self.model or not 0<=index<len(self.model.segments):return
        self.timeline.selected_segment=index
        if self.segments.currentRow()!=index:self.segments.setCurrentRow(index)
        start,end,keep=self.model.segments[index];self.selected_label.setText(f'Abschnitt {index+1}'+(' · entfernt' if not keep else ''));self.selected_label.setToolTip(stamp(start)+' – '+stamp(end));self.remove_segment_button.setEnabled(keep);self.restore_segment_button.setEnabled(not keep);self.timeline.update()
    def set_selected_keep(self,keep):
        index=self.timeline.selected_segment
        if not self.model or not 0<=index<len(self.model.segments):return
        self.player.pause();self.model.keep(index,keep);self.refresh_lists();self.select_segment(index);self.status.setText('Abschnitt wiederhergestellt.' if keep else 'Abschnitt entfernt; Wiedergabe und Export überspringen ihn.')
    def history_step(self,redo=False):
        if not self.model:return
        self.player.pause();changed=self.model.redo() if redo else self.model.undo()
        if changed:self.refresh_lists();self.status.setText('Schnittschritt wiederholt.' if redo else 'Schnittschritt rückgängig gemacht.')
    def refresh_lists(self):
        self.undo_button.setEnabled(bool(self.model.undo_stack));self.redo_button.setEnabled(bool(self.model.redo_stack))
        self.updating_lists=True;self.marks.clear();self.segments.clear()
        for cut in self.model.cuts:self.marks.addItem(stamp(cut))
        for index,(start,end,keep) in enumerate(self.model.segments):
            item=QListWidgetItem(f'{index+1} · '+stamp(start)+' – '+stamp(end));item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if keep else Qt.CheckState.Unchecked);self.segments.addItem(item)
        self.updating_lists=False;self.timeline.update()
        if self.model and self.timeline.selected_segment>=0:self.select_segment(min(self.timeline.selected_segment,len(self.model.segments)-1))
    def changed(self,item):
        if not self.updating_lists:self.model.keep(self.segments.row(item),item.checkState()==Qt.CheckState.Checked);self.select_segment(self.segments.row(item));self.timeline.update();self.undo_button.setEnabled(bool(self.model.undo_stack));self.redo_button.setEnabled(bool(self.model.redo_stack))
    def save(self):
        if not self.model or not self.model.ranges():QMessageBox.information(self,'Audioschnitt','Bitte mindestens einen Abschnitt behalten.');return
        self.player.pause();self.submit('Audio bearbeiten',[self.path],{'ranges':self.model.ranges(),'separate':self.separate.isChecked()});self.accept()
    def done(self,result):
        if not self.stopped.is_set():
            self.stopped.set();self.timeline.close_waveform();self.player.stop();self.player.setAudioOutput(None);self.player.setSource(QUrl());self.player.deleteLater();self.audio.deleteLater()
        super().done(result)
