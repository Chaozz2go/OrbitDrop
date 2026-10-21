import io
from pathlib import Path
from PIL import Image,ImageOps
from PySide6.QtCore import Qt,QObject,QRunnable,Signal,QThreadPool,QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QSpinBox,QDoubleSpinBox,QPushButton,QLineEdit,QMessageBox,QListWidget,QSizePolicy
from editor_chrome import EDITOR_STYLE,heading
from ui_theme import icon
from slider_field import SliderField
from orbit_compression import compression_settings,image_bytes
from image_editor import pil_qimage
from quick_actions import save_preset

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

class CompressionDialog(QDialog):
    def __init__(self,files,kind,submit,prefs):
        super().__init__();self.files=list(files);self.kind=kind;self.submit=submit;self.prefs=prefs;self.job=None;self.closed=False;self.revision=0;self.preview_image=None;self.original_image=None
        self.setStyleSheet(EDITOR_STYLE);self.setWindowTitle('OrbitDrop · Komprimieren');self.resize(920,760)
        layout=QVBoxLayout(self);heading(layout,'Komprimieren',f'{len(files)} Datei(en) · {kind} · Originale bleiben erhalten')
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
        self.target=QDoubleSpinBox();self.target.setRange(0,10000);self.target.setDecimals(2);self.target.setSpecialValueText('Kein Größenlimit');self.target.setSuffix(' MB pro Datei');form.addRow('Maximale Ergebnisgröße',self.target)
        for widget,visible in [(self.format,kind=='Bild'),(self.quality_field,kind in ('Bild','Video')),(self.edge,kind=='Bild'),(self.height,kind=='Video'),(self.bitrate,kind=='Audio')]:
            widget.setVisible(visible);label=form.labelForField(widget)
            if label:label.setVisible(visible)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        hint=QLabel('MB = 1.000.000 Byte. Das Limit wird am Ergebnis geprüft; unerreichbare Ziele führen zu einer Fehlermeldung. Ohne Limit ist eine kleinere Datei nicht garantiert. JPG erhält bei Transparenz einen weißen Hintergrund.');hint.setObjectName('editorSubtitle');hint.setWordWrap(True);layout.addWidget(hint)
        recipe=QHBoxLayout();layout.addLayout(recipe);self.preset_name=QLineEdit();self.preset_name.setMaxLength(28);self.preset_name.setPlaceholderText('Name für eigene Schnellaktion');recipe.addWidget(self.preset_name,1);save=QPushButton('Einstellungen merken');save.clicked.connect(self.save_recipe);recipe.addWidget(save)
        bottom=QHBoxLayout();layout.addLayout(bottom);self.close_button=QPushButton('Schließen');self.close_button.clicked.connect(self.reject);bottom.addWidget(self.close_button);bottom.addStretch();self.start=QPushButton('Neue Dateien erstellen');self.start.setObjectName('primaryAction');self.start.setIcon(icon('save','#102e27'));self.start.clicked.connect(self.apply);bottom.addWidget(self.start)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        for widget in (self.quality,self.edge,self.target):widget.valueChanged.connect(self.changed)
        self.format.currentIndexChanged.connect(self.changed);self.height.currentIndexChanged.connect(self.changed);self.bitrate.currentIndexChanged.connect(self.changed)
        self.changed();area=self.screen().availableGeometry();self.resize(min(920,area.width()-40),min(760,area.height()-50))
    def parameters(self):return compression_settings({'format':self.format.currentText(),'quality':self.quality.value(),'max_edge':self.edge.value(),'target_mb':self.target.value(),'video_height':self.height.currentData(),'audio_kbps':int(self.bitrate.currentText())})
    def changed(self,*unused):
        self.revision+=1;self.quality_field.setEnabled(self.kind!='Bild' or self.format.currentText()!='PNG')
        if self.kind=='Bild':self.start.setEnabled(False);self.timer.start(250)
        else:self.status.setText('Video mit Größenlimit verwendet zwei Durchläufe. PDFs werden ohne Rasterisierung optimiert.' if self.kind in ('Video','PDF') else 'Audio wird als neue MP3 gespeichert.');self.start.setEnabled(True)
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
    def done(self,result):self.closed=True;self.timer.stop();super().done(result)

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
