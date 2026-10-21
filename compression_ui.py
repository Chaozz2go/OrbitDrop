import io,threading
from pathlib import Path
from PIL import Image,ImageOps
from PySide6.QtCore import Qt,QObject,QRunnable,Signal,QThreadPool,QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QSpinBox,QDoubleSpinBox,QPushButton,QLineEdit,QMessageBox,QListWidget,QSizePolicy,QSlider,QWidget,QScrollArea
from editor_chrome import EDITOR_STYLE,heading
from ui_theme import icon
from slider_field import SliderField
from orbit_compression import compression_settings,image_bytes
from image_editor import pil_qimage
from quick_actions import save_preset
from compression_advice import size_text,inspect_compression,compression_advice

class CompressionSignals(QObject):done=Signal(object,str)
class CompressionPreview(QRunnable):
    def __init__(self,path,parameters):super().__init__();self.path=path;self.parameters=parameters;self.signals=CompressionSignals()
    def run(self):
        try:
            data,quality,size=image_bytes(self.path,self.parameters)
            with Image.open(io.BytesIO(data)) as image:
                image.thumbnail((900,650));preview=pil_qimage(image)
            with Image.open(self.path) as original:
                original=ImageOps.exif_transpose(original);original.thumbnail((900,650));before=pil_qimage(original)
            self.signals.done.emit((before,preview,len(data),quality,size),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class CompressionCheck(QRunnable):
    def __init__(self,files,kind,stopped):super().__init__();self.files,self.kind,self.stopped=files,kind,stopped;self.signals=CompressionSignals()
    def run(self):
        try:self.signals.done.emit(inspect_compression(self.files,self.kind,self.stopped),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class CompressionDialog(QDialog):
    def __init__(self,files,kind,submit,prefs):
        super().__init__();self.files=list(files);self.kind=kind;self.submit=submit;self.prefs=prefs;self.job=None;self.closed=False;self.revision=0;self.preview_image=None;self.original_image=None;self.records=None;self.check_job=None;self.check_error='';self.stopped=threading.Event()
        self.setStyleSheet(EDITOR_STYLE);self.setWindowTitle('OrbitDrop · Komprimieren');self.resize(920,760)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,12);content=QWidget();layout=QVBoxLayout(content)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);outer.addWidget(scroll,1)
        heading(layout,'Komprimieren',f'{len(files)} Datei(en) · {kind} · Originale bleiben erhalten')
        self.source_sizes=[Path(file).stat().st_size for file in self.files];self.first_size=self.source_sizes[0]
        self.size_summary=QLabel('Aktuelle Größe: '+size_text(sum(self.source_sizes))+(' gesamt · Erste Datei: '+size_text(self.first_size) if len(files)>1 else ''))
        self.size_summary.setWordWrap(True);self.size_summary.setToolTip('\n'.join(Path(file).name+': '+size_text(size) for file,size in zip(self.files,self.source_sizes)));layout.addWidget(self.size_summary)
        self.preview=QLabel('Bildvorschau wird berechnet …' if kind=='Bild' else 'Video → MP4 · Audio → MP3 · PDF → verlustfrei optimiertes PDF');self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setWordWrap(True);self.preview.setMinimumHeight(150);self.preview.setObjectName('previewSurface')
        preview_row=QHBoxLayout();layout.addLayout(preview_row,1);self.before=QLabel('Original');self.before.setAlignment(Qt.AlignmentFlag.AlignCenter);self.before.setMinimumSize(180,150);self.before.setObjectName('previewSurface')
        for label,title in [(self.before,'ORIGINAL'),(self.preview,'ERGEBNIS')]:
            column=QVBoxLayout();caption=QLabel(title);column.addWidget(caption);column.addWidget(label,1);preview_row.addLayout(column,1);label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
            if label is self.before:caption.setVisible(kind=='Bild')
        self.before.setVisible(kind=='Bild')
        form=QFormLayout();layout.addLayout(form)
        self.format=QComboBox();self.format.addItems(['WEBP','JPG','PNG']);form.addRow('Bildformat',self.format)
        self.quality=QSpinBox();self.quality.setRange(10,95);self.quality.setValue(82);self.quality_field=SliderField(self.quality);form.addRow('Qualität (höher = besser / größer)',self.quality_field)
        self.edge=QSpinBox();self.edge.setRange(0,16000);self.edge.setSpecialValueText('Originalgröße');self.edge.setSuffix(' px');form.addRow('Längste Bildkante',self.edge)
        self.height=QComboBox()
        for title,value in [('Originalhöhe',0),('Max. 480p',480),('Max. 720p',720),('Max. 1080p',1080),('Max. 1440p',1440),('Max. 2160p',2160)]:self.height.addItem(title,value)
        form.addRow('Videohöhe',self.height)
        self.bitrate=QComboBox();self.bitrate.addItems(['64','96','128','192','256','320']);self.bitrate.setCurrentText('128');form.addRow('Audio-Bitrate (kbit/s)',self.bitrate)
        self.target=QDoubleSpinBox();self.target.setRange(0,10000);self.target.setDecimals(3);self.target.setSpecialValueText('Kein Größenlimit');self.target.setSuffix(' MB pro Datei');form.addRow('Maximale Ergebnisgröße',self.target)
        self.target_slider=QSlider(Qt.Orientation.Horizontal);self.target_slider.setRange(1,100);self.target_slider.setValue(100);self.target_slider.setEnabled(self.first_size>=1000);self.target_slider.setToolTip('Zielgröße relativ zur ersten Datei. Nach links ziehen = kleiner. 0 MB im Zahlenfeld entfernt das Limit.');form.addRow('Zielgröße verkleinern',self.target_slider)
        self.target_description=QLabel('Kein Größenlimit · Regler nach links ziehen');self.target_description.setWordWrap(True);form.addRow(self.target_description)
        for widget,visible in [(self.format,kind=='Bild'),(self.quality_field,kind in ('Bild','Video')),(self.edge,kind=='Bild'),(self.height,kind=='Video'),(self.bitrate,kind=='Audio')]:
            widget.setVisible(visible);label=form.labelForField(widget)
            if label:label.setVisible(visible)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.advice=QLabel('');self.advice.setObjectName('editorSubtitle');self.advice.setWordWrap(True);layout.addWidget(self.advice)
        hint=QLabel('MB = 1.000.000 Byte. Das Limit wird am Ergebnis geprüft; unerreichbare Ziele führen zu einer Fehlermeldung. Ohne Limit ist eine kleinere Datei nicht garantiert. JPG erhält bei Transparenz einen weißen Hintergrund.');hint.setObjectName('editorSubtitle');hint.setWordWrap(True);layout.addWidget(hint)
        recipe=QHBoxLayout();layout.addLayout(recipe);self.preset_name=QLineEdit();self.preset_name.setMaxLength(28);self.preset_name.setPlaceholderText('Name für eigene Schnellaktion');recipe.addWidget(self.preset_name,1);save=QPushButton('Einstellungen merken');save.clicked.connect(self.save_recipe);recipe.addWidget(save)
        bottom=QHBoxLayout();bottom.setContentsMargins(18,0,18,0);outer.addLayout(bottom);self.close_button=QPushButton('Schließen');self.close_button.clicked.connect(self.reject);bottom.addWidget(self.close_button);bottom.addStretch();self.start=QPushButton('Neue Dateien erstellen');self.start.setObjectName('primaryAction');self.start.setIcon(icon('save','#102e27'));self.start.clicked.connect(self.apply);bottom.addWidget(self.start)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        for widget in (self.quality,self.edge,self.target):widget.valueChanged.connect(self.changed)
        self.format.currentIndexChanged.connect(self.changed);self.height.currentIndexChanged.connect(self.changed);self.bitrate.currentIndexChanged.connect(self.changed)
        self.target_slider.valueChanged.connect(self.target_from_slider)
        self.changed()
        if self.kind!='Bild':QTimer.singleShot(0,self.start_preflight)
        area=self.screen().availableGeometry();self.resize(min(920,area.width()-40),min(760,area.height()-50))
    def parameters(self):return compression_settings({'format':self.format.currentText(),'quality':self.quality.value(),'max_edge':self.edge.value(),'target_mb':self.target.value(),'video_height':self.height.currentData(),'audio_kbps':int(self.bitrate.currentText())})
    def changed(self,*unused):
        self.sync_size_target()
        self.revision+=1;self.quality_field.setEnabled(self.kind!='Bild' or self.format.currentText()!='PNG')
        if self.kind=='Bild':self.start.setEnabled(False);self.timer.start(250)
        else:self.update_advice()
    def target_from_slider(self,percent):
        self.target.setValue(max(.001,min(10000,self.first_size/1_000_000*percent/100)))
    def sync_size_target(self):
        target=self.target.value()*1_000_000
        percent=target/max(1,self.first_size)*100
        self.target_slider.blockSignals(True);self.target_slider.setValue(max(1,min(100,round(percent))) if target else 100);self.target_slider.blockSignals(False)
        self.target_description.setText((f'Ziel: {size_text(target)} pro Datei · {percent:.0f} % der ersten Datei'+(f' · {100-percent:.0f} % kleiner' if percent<100 else ' · keine Verkleinerung vorgegeben')) if target else 'Kein Größenlimit · Regler nach links ziehen')
    def start_preflight(self):
        if self.closed:return
        self.check_job=CompressionCheck(self.files,self.kind,self.stopped);self.check_job.signals.done.connect(self.preflight_ready);QThreadPool.globalInstance().start(self.check_job)
    def preflight_ready(self,records,error):
        self.check_job=None
        if self.closed:return
        self.records=records;self.check_error=error;self.update_advice()
        if records and self.kind=='PDF':self.preview.setText('Verlustfreie PDF-Probe\n'+size_text(sum(r['size'] for r in records))+' → '+size_text(sum(r['optimized'] for r in records)))
        elif records:self.preview.setText(('Video → MP4' if self.kind=='Video' else 'Audio → MP3')+f"\nGesamtdauer: {sum(r['duration'] for r in records)/60:.1f} Minuten\nZielgröße wird nach dem Export geprüft.")
    def update_advice(self):
        if self.check_error:self.status.setText('Vorprüfung fehlgeschlagen: '+self.check_error);self.advice.clear();self.start.setEnabled(False);return
        text,allowed=compression_advice(self.kind,self.records,self.parameters());self.advice.setText(text);self.status.setText('Vorprüfung abgeschlossen.' if self.records else 'Dateien werden vorgeprüft …');self.start.setEnabled(allowed)
    def refresh(self):
        if self.closed or self.job:return
        revision=self.revision;job=CompressionPreview(self.files[0],self.parameters());self.job=job;self.status.setText('Qualität und tatsächliche Bildgröße werden berechnet …');job.signals.done.connect(lambda result,error:self.ready(revision,result,error));QThreadPool.globalInstance().start(job)
    def ready(self,revision,result,error):
        self.job=None
        if self.closed:return
        if revision!=self.revision:self.timer.stop();self.refresh();return
        if error:self.status.setText(error);self.start.setEnabled(False);return
        self.original_image,self.preview_image,size,quality,dimensions=result;self.draw_preview();original=Path(self.files[0]).stat().st_size
        quality_text='verlustfrei' if self.format.currentText()=='PNG' else f'Qualität {quality}'
        self.advice.setText((f'{100*(1-size/original):.0f} % kleiner als das Original.' if size<original else 'Das Ergebnis ist nicht kleiner als das Original. WebP/JPG oder eine kleinere Bildkante ausprobieren.') if original else '')
        self.status.setText(f'Erste Datei: {original/1000:.1f} → {size/1000:.1f} KB · {dimensions[0]} × {dimensions[1]} px · {quality_text}'+(' · Weitere Dateien werden einzeln berechnet.' if len(self.files)>1 else ''));self.start.setEnabled(True)
    def draw_preview(self):
        for label,image in [(self.before,self.original_image),(self.preview,self.preview_image)]:
            if image is not None:label.setPixmap(QPixmap.fromImage(image).scaled(label.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def resizeEvent(self,event):super().resizeEvent(event);self.draw_preview()
    def save_recipe(self):
        try:save_preset(self.prefs,self.preset_name.text(),self.kind,self.parameters());self.status.setText('Schnellaktion gespeichert. Beim nächsten Öffnen im Bearbeiten-Kreis verfügbar.');self.preset_name.clear()
        except Exception as error:QMessageBox.warning(self,'Schnellaktion',str(error))
    def apply(self):
        if not self.start.isEnabled():return
        self.submit('Komprimieren',self.files,self.parameters());self.accept()
    def done(self,result):self.closed=True;self.stopped.set();self.timer.stop();super().done(result)

class QuickActionsDialog(QDialog):
    def __init__(self,prefs):
        super().__init__();self.prefs=prefs;self.setStyleSheet(EDITOR_STYLE);self.setWindowTitle('OrbitDrop · Schnellaktionen');self.resize(630,440)
        layout=QVBoxLayout(self);heading(layout,'Schnellaktionen','Im Komprimieren-Dialog eigene Einstellungen speichern. Passende Aktionen erscheinen direkt unter Strg.');self.items=QListWidget();layout.addWidget(self.items)
        row=QHBoxLayout();layout.addLayout(row)
        for title,callback in [('Entfernen',self.remove),('Startvorlagen hinzufügen',self.starters),('Schließen',self.accept)]:button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
        self.reload()
    def reload(self):
        self.items.clear()
        for item in self.prefs.values.get('quick_actions',[]):self.items.addItem(item['name']+' · '+item['kind'])
    def remove(self):
        row=self.items.currentRow()
        if row<0:return
        values=list(self.prefs.values['quick_actions']);values.pop(row);self.prefs.update(dict(self.prefs.values,quick_actions=values));self.reload()
    def starters(self):
        try:
            names={p['name'].casefold() for p in self.prefs.values.get('quick_actions',[])}
            for name,kind,params in [('Bilder fürs Web','Bild',{'max_edge':1600,'quality':80,'format':'WEBP'}),('Video 720p unter 20 MB','Video',{'video_height':720,'target_mb':20}),('Audio klein','Audio',{'audio_kbps':96})]:
                if name.casefold() not in names:save_preset(self.prefs,name,kind,params)
            self.reload()
        except Exception as error:QMessageBox.warning(self,'Schnellaktionen',str(error))
