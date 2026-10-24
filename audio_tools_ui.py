"""Profile-driven audio enhancement with short, level-matched A/B playback."""
from collections import OrderedDict
from pathlib import Path
import math,shutil
from PySide6.QtCore import Qt,QUrl,QTimer,QStandardPaths,QObject,QRunnable,Signal
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath,QShortcut,QKeySequence
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QGridLayout,QCheckBox,QComboBox,QDoubleSpinBox,QLabel,QMessageBox,QScrollArea,QTabWidget,QInputDialog,QSlider,QSpacerItem,QSizePolicy
from editor_chrome import heading,EDITOR_STYLE,action_button
from slider_field import SliderField
from loading_ui import LoadingIndicator
from preview_runtime import preview_pool
from task_runtime import TaskControl,checkpoint
from audio_tools import audio_settings
from audio_dsp import EQ_FREQUENCIES,FX_KEYS
from audio_profiles import FACTORY,factory_profile,AudioProfileStore
from audio_preview import audio_probe,build_preview,preview_key,matched_gains

class AudioSignals(QObject):
    done=Signal(object,str)
    progress=Signal(int,str)
class AudioWork(QRunnable):
    def __init__(self,operation):super().__init__();self.operation=operation;self.signals=AudioSignals();self.control=TaskControl(self.signals.progress.emit)
    def run(self):
        try:
            with self.control.activate():checkpoint();result=self.operation()
            self.signals.done.emit(result,'')
        except Exception as error:self.signals.done.emit(None,str(error))

def cleanup_later(roots,attempt=0):
    pending=[]
    for root in roots:
        shutil.rmtree(root,ignore_errors=True)
        if Path(root).exists():pending.append(root)
    if pending and attempt<5:QTimer.singleShot(200*(attempt+1),lambda:cleanup_later(pending,attempt+1))

class EqCurve(QWidget):
    def __init__(self,dialog):super().__init__();self.dialog=dialog;self.setMinimumHeight(100)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.fillRect(self.rect(),QColor('#0e1928'));w=max(1,self.width()-40);h=max(1,self.height()-30);left=20;top=10
        painter.setPen(QPen(QColor('#344c66'),1));painter.drawLine(left,int(top+h/2),int(left+w),int(top+h/2))
        path=QPainterPath();active=self.dialog.eq_enabled.isChecked();strength=self.dialog.strength.value()/100
        for i,field in enumerate(self.dialog.eq):
            x=left+w*i/9;gain=field.value()*strength if active else 0;y=top+h*(12-gain)/24
            if i:path.lineTo(x,y)
            else:path.moveTo(x,y)
        painter.setPen(QPen(QColor('#ffbe8a'),2));painter.drawPath(path);painter.setPen(QColor('#a3b7ce'));painter.drawText(20,self.height()-3,'31 Hz');painter.drawText(max(20,self.width()-65),self.height()-3,'16 kHz')

class AudioToolsDialog(QDialog):
    def __init__(self,files,submit,prefs=None):
        super().__init__()
        if not files:raise ValueError('Bitte eine Audiodatei auswählen.')
        self.files=list(map(str,files));self.submit=submit;self.closed=False;self.updating=True;self.jobs=set();self.probe_job=None;self.preview_job=None;self.revision=0;self.duration=0.;self.channels=0;self.preview=None;self.cache=OrderedDict();self.retired=[];self.current=1;self.had_preview=False;self.sliding=False
        root=prefs.root if prefs is not None else QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        self.store=AudioProfileStore(root);self.setWindowTitle('OrbitDrop · Audio verbessern');self.setStyleSheet(EDITOR_STYLE);self.resize(1040,820)
        layout=QVBoxLayout(self);heading(layout,'Audio verbessern',f'{len(files)} Datei(en) · Profile, Equalizer & Hörvergleich · Originale bleiben erhalten')
        row=QHBoxLayout();layout.addLayout(row);self.profile=QComboBox();row.addWidget(self.profile,1)
        self.save_profile=action_button('Eigenes Profil speichern');self.save_profile.clicked.connect(self.save_own);row.addWidget(self.save_profile)
        self.delete_profile=action_button('Profil löschen');self.delete_profile.clicked.connect(self.delete_own);row.addWidget(self.delete_profile)
        self.profile_hint=QLabel();self.profile_hint.setWordWrap(True);layout.addWidget(self.profile_hint);self.modified=QLabel('Profil angepasst · bei Bedarf als eigenes Profil speichern');self.modified.setObjectName('editorSubtitle');layout.addWidget(self.modified);self.modified.hide()
        form=QFormLayout();layout.addLayout(form);self.strength=self.spin(0,100,100,' %',0);form.addRow('Profilstärke',SliderField(self.strength))
        switches=QHBoxLayout();layout.addLayout(switches)
        self.eq_enabled=QCheckBox('Equalizer aktiv');self.compressor=QCheckBox('Dynamik ausgleichen');self.deesser=QCheckBox('S-Laute reduzieren')
        for field in (self.eq_enabled,self.compressor,self.deesser):switches.addWidget(field)
        self.eq=[self.spin(-12,12,0,' dB') for _ in EQ_FREQUENCIES];self.quick=[];self.quick_values=[0.]*4;quick=QGridLayout();layout.addLayout(quick)
        self.quick_groups=((1,2),(3,4),(6,7),(8,9))
        for index,title in enumerate(('Bass','Wärme','Klarheit','Höhen')):
            field=self.spin(-12,12,0,' dB');self.quick.append(field);quick.addWidget(QLabel(title),index//2,index%2*2);quick.addWidget(SliderField(field,1),index//2,index%2*2+1);field.valueChanged.connect(lambda value,i=index:self.quick_changed(i,value))
        self.expand=action_button('Erweitert anzeigen');self.expand.setCheckable(True);layout.addWidget(self.expand)
        self.tabs=QTabWidget();self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setWidget(self.tabs);self.scroll.setMinimumHeight(180);self.scroll.setMaximumHeight(320);layout.addWidget(self.scroll,1);self.scroll.hide();self.expand.toggled.connect(self.show_advanced)
        self.eq_panel=self.add_tab('Equalizer');self.curve=EqCurve(self);self.eq_panel.addRow(self.curve)
        for frequency,field in zip(EQ_FREQUENCIES,self.eq):self.eq_panel.addRow((str(frequency)+' Hz') if frequency<1000 else f'{frequency/1000:g} kHz',SliderField(field,1))
        flat=action_button('EQ auf neutral setzen');flat.clicked.connect(self.flat_eq);self.eq_panel.addRow(flat)
        self.highpass=self.spin(0,250,0,' Hz',0);self.highpass.setSpecialValueText('Aus');self.eq_panel.addRow('Rumpelfilter · Hochpass',SliderField(self.highpass))
        dynamics=self.add_tab('Dynamik & S-Laute');self.comp_threshold=self.spin(-45,0,-20,' dB');self.comp_ratio=self.spin(1,8,2,' : 1');self.comp_attack=self.spin(.1,100,15,' ms');self.comp_release=self.spin(10,1000,180,' ms');self.comp_makeup=self.spin(0,12,0,' dB');self.comp_knee=self.spin(1,8,2.828,'',3)
        self.comp_fields=(self.comp_threshold,self.comp_ratio,self.comp_attack,self.comp_release,self.comp_makeup,self.comp_knee)
        for title,field in zip(('Einsatzschwelle','Verhältnis','Attack · reagiert nach','Release · klingt aus','Pegel nach Kompressor','Weicher Übergang · 1 hart, 8 weich'),self.comp_fields):dynamics.addRow(title,SliderField(field,1 if field.decimals() else 0))
        self.deess_intensity=self.spin(0,100,25,' %');self.deess_amount=self.spin(0,100,35,' %');self.deess_focus=self.spin(0,100,55,' %');self.deess_fields=(self.deess_intensity,self.deess_amount,self.deess_focus)
        for title,field in zip(('S-Laut-Erkennung','Maximale S-Laut-Absenkung','Frequenzfokus · niedrig → hoch'),self.deess_fields):dynamics.addRow(title,SliderField(field,1))
        output=self.add_tab('Lautheit, Fades & Randstille');self.normalize=QCheckBox('Lautheit mit zwei Durchläufen angleichen');self.normalize.setChecked(True);output.addRow(self.normalize)
        self.lufs=self.spin(-30,-10,-16,' LUFS');output.addRow('Lautheitsziel · unabhängig vom Klangprofil',SliderField(self.lufs,1));self.protect=QCheckBox('Spitzen begrenzen · mit Oversampling');self.protect.setChecked(True);output.addRow(self.protect);self.peak=self.spin(-6,-1,-1.5,' dB');output.addRow('Spitzenziel / Reserve',SliderField(self.peak,1))
        self.trim=QCheckBox('Stille nur am Anfang und Ende entfernen');output.addRow(self.trim);self.threshold=self.spin(-80,-20,-45,' dB');self.threshold_field=SliderField(self.threshold,1);output.addRow('Stille-Schwelle',self.threshold_field);self.padding=self.spin(0,2,.1,' s',2);output.addRow('Rand an Stille behalten',self.padding)
        self.fade_in=self.spin(0,30,0,' s');self.fade_out=self.spin(0,30,0,' s');output.addRow('Einblenden',self.fade_in);output.addRow('Ausblenden',self.fade_out)
        row=QHBoxLayout();layout.addLayout(row);self.source=QComboBox();self.source.addItems([Path(f).name for f in self.files]);
        for i,path in enumerate(self.files):self.source.setItemData(i,path,Qt.ItemDataRole.ToolTipRole)
        row.addWidget(self.source,1);self.preview_start=self.spin(0,0,0,' s');row.addWidget(QLabel('Vorschau ab'));row.addWidget(self.preview_start);self.preview_length=self.spin(.1,30,15,' s');row.addWidget(QLabel('Länge'));row.addWidget(self.preview_length)
        self.generate=action_button('Hörvorschau berechnen','play');self.generate.clicked.connect(self.request_preview);row.addWidget(self.generate)
        self.loading=LoadingIndicator();layout.addWidget(self.loading)
        row=QHBoxLayout();layout.addLayout(row);self.before_button=action_button('Original');self.after_button=action_button('Bearbeitet');self.before_button.setCheckable(True);self.after_button.setCheckable(True);self.after_button.setChecked(True);self.before_button.clicked.connect(lambda:self.select_audio(0));self.after_button.clicked.connect(lambda:self.select_audio(1));row.addWidget(self.before_button);row.addWidget(self.after_button)
        self.play=action_button('Abspielen / Pause','play');self.play.clicked.connect(self.toggle_play);row.addWidget(self.play);self.seek=QSlider(Qt.Orientation.Horizontal);self.seek.setRange(0,0);self.seek.sliderPressed.connect(lambda:setattr(self,'sliding',True));self.seek.sliderReleased.connect(self.seek_released);row.addWidget(self.seek,1);self.time_label=QLabel('0:00 / 0:00');row.addWidget(self.time_label)
        row=QHBoxLayout();layout.addLayout(row);self.match=QCheckBox('Wiedergabepegel näherungsweise angleichen (RMS)');self.match.setChecked(True);row.addWidget(self.match);self.auto=QCheckBox('Vorschau automatisch aktualisieren');self.auto.setChecked(True);row.addWidget(self.auto);row.addStretch();row.addWidget(QLabel('Lautstärke'));self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(80);self.volume.setMaximumWidth(100);row.addWidget(self.volume)
        self.note=QLabel('Klangvorschau für einen kurzen Ausschnitt. Randstille und Fades werden erst beim Export auf die ganze Datei angewendet. Endlautheit kann vom Ausschnitt abweichen. Ausgabe: 48 kHz; MP3: 192 kbit/s.');self.note.setWordWrap(True);self.note.setObjectName('editorSubtitle');layout.addWidget(self.note)
        self.status=QLabel('Audio wird geöffnet …');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.main_spacer=QSpacerItem(0,0,QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Expanding);layout.addItem(self.main_spacer)
        row=QHBoxLayout();layout.addLayout(row);close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);row.addStretch();self.format=QComboBox();self.format.addItems(['FLAC','WAV','MP3']);row.addWidget(self.format);self.start=action_button('Neue Audiodateien erstellen','save',True);self.start.clicked.connect(self.save);row.addWidget(self.start)
        self.players=[];self.outputs=[];self.pending_seek=[None,None];self.preview_note=self.note.text()
        for i in range(2):
            player=QMediaPlayer(self);audio=QAudioOutput(self);player.setAudioOutput(audio);player.positionChanged.connect(lambda position,n=i:self.position_changed(n,position));player.mediaStatusChanged.connect(lambda status,n=i:self.media_ready(n,status));player.playbackStateChanged.connect(lambda state,n=i:self.play_state(n,state));player.errorOccurred.connect(lambda error,message,n=i:self.player_error(n,message));self.players.append(player);self.outputs.append(audio)
        self.match.toggled.connect(self.apply_volume);self.volume.valueChanged.connect(self.apply_volume)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(500);self.timer.timeout.connect(self.request_preview)
        for field in self.eq+[self.strength,self.highpass]+list(self.comp_fields)+list(self.deess_fields):field.valueChanged.connect(self.fx_changed)
        for field in (self.eq_enabled,self.compressor,self.deesser):field.toggled.connect(self.fx_changed)
        for field in (self.lufs,self.peak,self.threshold,self.padding,self.fade_in,self.fade_out,self.preview_start,self.preview_length):field.valueChanged.connect(self.changed)
        for field in (self.normalize,self.protect,self.trim):field.toggled.connect(self.changed)
        self.format.currentTextChanged.connect(self.changed);self.source.currentIndexChanged.connect(self.load_source);self.profile.currentIndexChanged.connect(self.apply_profile)
        self.shortcut=QShortcut(QKeySequence(Qt.Key.Key_Space),self);self.shortcut.activated.connect(self.toggle_play)
        self.fill_profiles('podcast');self.updating=False;self.apply_profile();self.load_source()
    @staticmethod
    def spin(low,high,value,suffix='',decimals=1):
        field=QDoubleSpinBox();field.setDecimals(decimals);field.setRange(low,high);field.setValue(value);field.setSuffix(suffix);field.setSingleStep(.5 if decimals else 1);return field
    def add_tab(self,title):
        widget=QWidget();form=QFormLayout(widget);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);self.tabs.addTab(widget,title);return form
    def show_advanced(self,shown):self.scroll.setVisible(shown);self.main_spacer.changeSize(0,0,QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Fixed if shown else QSizePolicy.Policy.Expanding);self.layout().invalidate();self.expand.setText('Erweitert ausblenden' if shown else 'Erweitert anzeigen')
    def fill_profiles(self,selected=None):
        self.profile.blockSignals(True);self.profile.clear()
        for identifier,title,hint,values in FACTORY:self.profile.addItem(title,identifier)
        for item in self.store.items:self.profile.addItem('Eigenes · '+item['name'],'custom:'+item['id'])
        self.profile.setCurrentIndex(max(0,self.profile.findData(selected)));self.profile.blockSignals(False)
    def apply_profile(self,*args):
        key=self.profile.currentData()
        if not key:return
        custom=str(key).startswith('custom:');self.delete_profile.setEnabled(custom)
        if custom:
            item=next((p for p in self.store.items if p['id']==key.split(':',1)[1]),None)
            if not item:return
            values=item['parameters'];hint='Eigenes Klangprofil · Ausgabe und Lautheitsziel bleiben separat.'
        else:
            values=factory_profile(key);hint=next(p[2] for p in FACTORY if p[0]==key)
        self.updating=True
        for name in FX_KEYS:
            if name=='eq':
                for field,value in zip(self.eq,values['eq']):field.setValue(value)
            elif name=='deess_intensity':self.deess_intensity.setValue(values[name]*100)
            elif name=='deess_amount':self.deess_amount.setValue(values[name]*100)
            elif name=='deess_focus':self.deess_focus.setValue(values[name]*100)
            else:
                field=getattr(self,name);field.setChecked(values[name]) if isinstance(field,QCheckBox) else field.setValue(values[name])
        self.updating=False;self.profile_hint.setText(hint);self.modified.hide();self.sync_quick();self.fields();self.changed()
    def parameters(self):
        return audio_settings({'strength':self.strength.value(),'eq_enabled':self.eq_enabled.isChecked(),'eq':[f.value() for f in self.eq],'highpass':self.highpass.value(),'compressor':self.compressor.isChecked(),'comp_threshold':self.comp_threshold.value(),'comp_ratio':self.comp_ratio.value(),'comp_attack':self.comp_attack.value(),'comp_release':self.comp_release.value(),'comp_makeup':self.comp_makeup.value(),'comp_knee':self.comp_knee.value(),'deesser':self.deesser.isChecked(),'deess_intensity':self.deess_intensity.value()/100,'deess_amount':self.deess_amount.value()/100,'deess_focus':self.deess_focus.value()/100,'normalize':self.normalize.isChecked(),'lufs':self.lufs.value(),'protect':self.protect.isChecked(),'peak':self.peak.value(),'trim':self.trim.isChecked(),'threshold':self.threshold.value(),'padding':self.padding.value(),'fade_in':self.fade_in.value(),'fade_out':self.fade_out.value(),'format':self.format.currentText()})
    def sync_quick(self):
        old=self.updating;self.updating=True
        for i,indices in enumerate(self.quick_groups):
            value=sum(self.eq[n].value() for n in indices)/len(indices);self.quick[i].setValue(value);self.quick_values[i]=self.quick[i].value()
        self.updating=old;self.curve.update()
    def quick_changed(self,index,value):
        if self.updating:return
        delta=value-self.quick_values[index];self.updating=True
        for band in self.quick_groups[index]:self.eq[band].setValue(max(-12,min(12,self.eq[band].value()+delta)))
        self.eq_enabled.setChecked(True);self.updating=False;self.fx_changed()
    def flat_eq(self):
        self.updating=True
        for field in self.eq:field.setValue(0)
        self.updating=False;self.fx_changed()
    def fx_changed(self,*args):
        if self.updating:return
        self.modified.show();self.sync_quick();self.changed()
    def fields(self):
        for field in self.comp_fields:field.parentWidget().setEnabled(self.compressor.isChecked())
        for field in self.deess_fields:field.parentWidget().setEnabled(self.deesser.isChecked())
        for field in self.quick:field.parentWidget().setEnabled(self.eq_enabled.isChecked())
        self.threshold_field.setEnabled(self.trim.isChecked());self.padding.setEnabled(self.trim.isChecked());self.lufs.parentWidget().setEnabled(self.normalize.isChecked());self.peak.parentWidget().setEnabled(self.protect.isChecked() or self.normalize.isChecked());self.curve.update()
    def save_own(self):
        name,ok=QInputDialog.getText(self,'Audio-Profil speichern','Name des eigenen Klangprofils:')
        if not ok:return
        try:identifier=self.store.add(name,self.parameters());self.fill_profiles('custom:'+identifier);self.apply_profile();self.status.setText('Eigenes Klangprofil gespeichert.')
        except Exception as error:QMessageBox.warning(self,'Audio-Profil',str(error))
    def delete_own(self):
        key=str(self.profile.currentData())
        if not key.startswith('custom:'):return
        if QMessageBox.question(self,'Audio-Profil löschen','Dieses eigene Profil löschen?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:self.store.remove(key.split(':',1)[1]);self.fill_profiles('neutral');self.apply_profile()
        except Exception as error:QMessageBox.warning(self,'Audio-Profil',str(error))
    def work(self,operation,callback):
        job=AudioWork(operation);self.jobs.add(job)
        def ready(result,error):
            self.jobs.discard(job);callback(job,result,error)
        job.signals.done.connect(ready);job.signals.progress.connect(lambda value,text:self.loading.progress(value,text) if not self.closed and self.preview_job is job and value>=0 else None);preview_pool().start(job);return job
    def repaint_surface(self):
        if self.closed:return
        self.layout().activate();self.repaint()
        for widget in self.findChildren(QWidget):
            if widget.isVisible():widget.repaint()
    def detach(self):
        self.pending_seek=[None,None]
        for player in self.players:player.stop();player.setSource(QUrl())
    def playback_enabled(self,enabled):
        for field in (self.play,self.before_button,self.after_button,self.seek):field.setEnabled(enabled)
    def load_source(self,*args):
        if self.closed:return
        self.revision+=1;self.duration=0;self.preview=None;self.detach();self.playback_enabled(False);self.start.setEnabled(False);self.generate.setEnabled(False)
        if self.probe_job:self.probe_job.control.cancel()
        if self.preview_job:self.preview_job.control.cancel()
        source=self.files[self.source.currentIndex()];self.loading.busy('Audio wird geöffnet …');self.status.setText(self.store.error or 'Audio wird geprüft …')
        def ready(job,result,error):
            if self.closed or self.probe_job is not job:return
            self.probe_job=None;self.loading.finish();QTimer.singleShot(100,self.repaint_surface)
            if error:self.status.setText(error);return
            self.duration,self.channels=result;self.preview_start.blockSignals(True);self.preview_start.setRange(0,max(0,self.duration-.05));self.preview_start.setValue(0);self.preview_start.blockSignals(False);self.preview_length.blockSignals(True);self.preview_length.setMaximum(max(.1,min(30,self.duration)));self.preview_length.blockSignals(False);self.note.setText(self.preview_note+(' Mehrkanalquelle: Hörvorschau in Stereo.' if self.channels>2 else ''));self.status.setText((self.store.error+' · ' if self.store.error else '')+f'{self.duration:.1f} Sekunden · {self.channels} Kanal/Kanäle · Hörvorschau bei Bedarf berechnen.');self.changed()
        self.probe_job=self.work(lambda:audio_probe(source),ready)
    def changed(self,*args):
        if self.updating or self.closed:return
        self.fields();self.timer.stop()
        try:
            p=self.parameters()
            if self.duration and p['fade_in']+p['fade_out']>self.duration:raise ValueError('Ein- und Ausblenden sind zusammen länger als die Audiodatei.')
        except (ValueError,TypeError) as error:
            self.revision+=1;self.playback_enabled(False)
            for player in self.players:player.stop()
            if self.preview_job:self.preview_job.control.cancel()
            self.status.setText(str(error));self.start.setEnabled(False);self.generate.setEnabled(False);return
        self.start.setEnabled(self.duration>0);self.generate.setEnabled(self.duration>0)
        if not self.duration:return
        source=self.files[self.source.currentIndex()]
        try:key=preview_key(source,p,self.preview_start.value(),self.preview_length.value())
        except OSError as error:self.status.setText(str(error));self.start.setEnabled(False);return
        if self.preview and self.preview.key==key:
            self.playback_enabled(True);self.apply_volume();self.status.setText('Hörvorschau bereit · Original / Bearbeitet umschalten.');return
        self.revision+=1;self.playback_enabled(False)
        for player in self.players:player.stop()
        if self.preview_job:self.preview_job.control.cancel()
        if self.had_preview:
            self.status.setText('Vorschau veraltet · Einstellungen wurden geändert.')
            if self.auto.isChecked():self.timer.start()
    def request_preview(self):
        if self.closed or not self.duration:return
        if self.preview_job:
            self.preview_job.control.cancel();self.timer.start();return
        try:
            values=self.parameters();source=self.files[self.source.currentIndex()];start=self.preview_start.value();length=self.preview_length.value();key=preview_key(source,values,start,length)
        except Exception as error:self.status.setText(str(error));return
        self.had_preview=True
        if key in self.cache:
            result=self.cache.pop(key);self.cache[key]=result;self.use_preview(result);return
        revision=self.revision;self.loading.busy('Hörvorschau wird berechnet …');self.generate.setEnabled(False)
        def ready(job,result,error):
            if self.preview_job is job:self.preview_job=None
            if self.closed:
                if result:cleanup_later([result.root])
                return
            self.loading.finish();QTimer.singleShot(100,self.repaint_surface);self.generate.setEnabled(self.duration>0)
            if revision!=self.revision:
                if result:cleanup_later([result.root])
                return
            if error:self.status.setText('Vorschau: '+error);return
            self.cache[result.key]=result
            while len(self.cache)>3:
                old=self.cache.popitem(last=False)[1];self.retired.append(old.root)
            self.use_preview(result)
        self.preview_job=self.work(lambda:build_preview(source,values,start,length),ready)
    def use_preview(self,result):
        self.detach();self.preview=result
        for i,(player,path) in enumerate(zip(self.players,(result.before,result.after))):
            self.pending_seek[i]=0;player.setSource(QUrl.fromLocalFile(str(path)))
        self.seek.setRange(0,round(result.duration*1000));self.seek.setValue(0);self.playback_enabled(True);self.apply_volume();self.position_changed(self.current,0);self.status.setText('Hörvorschau bereit · Original / Bearbeitet umschalten. Pegelangleichung wirkt nur auf die Wiedergabe.')
        if self.retired:cleanup_later(self.retired);self.retired=[]
    def select_audio(self,index):
        if index==self.current:
            self.before_button.setChecked(index==0);self.after_button.setChecked(index==1);return
        old=self.players[self.current];position=old.position();playing=old.playbackState()==QMediaPlayer.PlaybackState.PlayingState;old.pause();self.current=index;self.before_button.setChecked(index==0);self.after_button.setChecked(index==1);self.seek_player(index,position)
        if playing:self.players[index].play()
    def toggle_play(self):
        if not self.preview or not self.play.isEnabled():return
        player=self.players[self.current]
        if player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:player.pause()
        else:
            if player.position()>=self.seek.maximum()-20:player.setPosition(0)
            player.play()
    def seek_released(self):
        self.sliding=False
        for i in range(2):self.seek_player(i,self.seek.value())
    def seek_player(self,index,position):
        player=self.players[index];self.pending_seek[index]=None if player.isSeekable() else position;player.setPosition(position)
    def media_ready(self,index,status):
        if not self.closed and status in (QMediaPlayer.MediaStatus.LoadedMedia,QMediaPlayer.MediaStatus.BufferedMedia) and self.pending_seek[index] is not None:
            position=self.pending_seek[index];self.pending_seek[index]=None;self.players[index].setPosition(position)
    def play_state(self,index,state):
        if not self.closed and index==self.current:self.play.setText('Pause' if state==QMediaPlayer.PlaybackState.PlayingState else 'Abspielen')
    def position_changed(self,index,position):
        if index!=self.current:return
        if not self.sliding:self.seek.setValue(position)
        duration=self.preview.duration if self.preview else 0
        self.time_label.setText(f'{position/1000:.1f} / {duration:.1f} s')
    def apply_volume(self,*args):
        gains=matched_gains(self.preview.before_rms,self.preview.after_rms) if self.preview and self.match.isChecked() else (1.,1.)
        for audio,gain in zip(self.outputs,gains):audio.setVolume(self.volume.value()/100*gain)
    def player_error(self,index,message):
        if not self.closed and self.preview and index==self.current:self.status.setText('Wiedergabe nicht möglich: '+message+' · Windows-Audioausgabe prüfen.')
    def save(self):
        if not self.duration:return
        try:
            p=self.parameters()
            if self.preview:
                source=self.files[self.source.currentIndex()]
                if preview_key(source,p,self.preview_start.value(),self.preview_length.value())[:4]!=self.preview.key[:4]:raise ValueError('Quelldatei seit der Vorschau geändert. Bitte Audio erneut öffnen.')
            self.submit('Audio verbessern',self.files,p);self.accept()
        except Exception as error:QMessageBox.warning(self,'Audio verbessern',str(error))
    def done(self,result):
        if not self.closed:
            self.closed=True;self.timer.stop()
            for job in self.jobs:job.control.cancel()
            self.detach();cleanup_later([p.root for p in self.cache.values()]+self.retired);self.cache.clear();self.retired=[];self.preview=None
        super().done(result)
    def closeEvent(self,event):self.done(QDialog.DialogCode.Rejected);event.accept()
