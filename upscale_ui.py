from pathlib import Path
from PIL import Image
import threading
from PySide6.QtCore import QObject,Signal,QRunnable,QTimer,Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QSpinBox,QCheckBox,QLabel,QScrollArea
from editor_chrome import heading,EDITOR_STYLE,action_button
from slider_field import SliderField
from image_editor import pil_qimage
from image_upscale import prepare_source,enlarge,upscale_settings,target_size
from preview_runtime import preview_pool,source_key
from loading_ui import LoadingIndicator

class UpscaleSignals(QObject):done=Signal(object,str)
class UpscalePreview(QRunnable):
    def __init__(self,path,values,edit,stopped,source=None,signature=None):super().__init__();self.path,self.values,self.edit,self.stopped,self.source,self.signature=path,values,edit,stopped,source,signature;self.signals=UpscaleSignals()
    def run(self):
        try:
            if self.stopped.is_set():return
            signature=source_key('upscale',self.path)
            image=self.source if self.source is not None and signature==self.signature else prepare_source(self.path,self.edit)
            if source_key('upscale',self.path)!=signature:raise ValueError('Bild wurde während des Ladens geändert. Bitte erneut öffnen.')
            size=target_size(image.size,self.values);factor=size[0]/image.width
            # Compare a central sample at the actual output pixel scale, rather
            # than shrinking away interpolation differences in a fitted image.
            edge=max(16,min(256,round(512/max(1,factor))));w,h=min(edge,image.width),min(edge,image.height)
            x=(image.width-w)//2;y=(image.height-h)//2;sample=image.crop((x,y,x+w,y+h))
            local=dict(self.values,width=0,height=0,factor=factor)
            after=enlarge(sample,local);before=sample.resize(after.size,resample=Image.Resampling.NEAREST)
            if not self.stopped.is_set():self.signals.done.emit((pil_qimage(before),pil_qimage(after),image.size,size,image,signature),'')
        except Exception as error:
            if not self.stopped.is_set():self.signals.done.emit(None,str(error))

class UpscaleDialog(QDialog):
    def __init__(self,path,submit,edit=None,parent=None):
        super().__init__(parent);self.path=str(path);self.submit=submit;self.edit=edit or {};self.stopped=threading.Event();self.job=None;self.revision=0;self.source=None;self.signature=None
        self.setWindowTitle('OrbitDrop · Vergrößern & verbessern');self.setStyleSheet(EDITOR_STYLE);self.resize(1060,760)
        layout=QVBoxLayout(self);heading(layout,'Vergrößern & verbessern',Path(path).name+' · Interpolation ohne KI · Ausgabe als neue PNG-Datei')
        form=QFormLayout();layout.addLayout(form);self.factor=QComboBox()
        for title,data in [('2×',2),('3×',3),('4×',4),('Eigene Zielgröße',0)]:self.factor.addItem(title,data)
        form.addRow('Vergrößerung',self.factor);self.width=QSpinBox();self.height=QSpinBox()
        for title,field in [('Zielbreite',self.width),('Zielhöhe',self.height)]:field.setRange(0,30000);field.setSpecialValueText('Automatisch');field.setSuffix(' px');form.addRow(title,field)
        self.method=QComboBox()
        for title,data in [('Lanczos · detailliert','lanczos'),('Bikubisch · weichere Übergänge','bicubic'),('Pixel-Art · klare Pixel erhalten','nearest')]:self.method.addItem(title,data)
        form.addRow('Verfahren',self.method);self.denoise=QCheckBox('Vorsichtig entrauschen');form.addRow(self.denoise)
        self.sharpen=QSpinBox();self.sharpen.setRange(0,200);self.sharpen.setSuffix(' %');self.sharpen_field=SliderField(self.sharpen);form.addRow('Nachschärfen',self.sharpen_field)
        hint=QLabel('Interpolation ergänzt Pixel, keine verlorenen Details. Pixel-Art erhält harte Pixel und deaktiviert Glättung/Schärfung. Eigene Breite/Höhe begrenzen das Ziel bei erhaltenem Seitenverhältnis; 0 = automatisch.');hint.setWordWrap(True);layout.addWidget(hint)
        self.loading=LoadingIndicator();layout.addWidget(self.loading);row=QHBoxLayout();layout.addLayout(row,1);self.previews=[]
        for title in ('Originalausschnitt · auf gleiche Größe mit klaren Pixeln','Ergebnis · 100 % Pixelansicht'):
            column=QVBoxLayout();row.addLayout(column,1);caption=QLabel(title);caption.setWordWrap(True);column.addWidget(caption)
            label=QLabel();label.setAlignment(Qt.AlignmentFlag.AlignCenter);label.setObjectName('previewSurface');scroll=QScrollArea();scroll.setWidget(label);scroll.setWidgetResizable(True);column.addWidget(scroll,1);self.previews.append(label)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        bottom=QHBoxLayout();layout.addLayout(bottom);close=action_button('Schließen');close.clicked.connect(self.reject);bottom.addWidget(close);bottom.addStretch();self.save_button=action_button('Als PNG speichern','save',True);self.save_button.clicked.connect(self.save);bottom.addWidget(self.save_button)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        self.factor.currentIndexChanged.connect(self.changed);self.method.currentIndexChanged.connect(self.changed);self.width.valueChanged.connect(self.changed);self.height.valueChanged.connect(self.changed);self.denoise.toggled.connect(self.changed);self.sharpen.valueChanged.connect(self.changed);self.changed()
    def options(self):
        custom=self.factor.currentData()==0
        if custom and not(self.width.value() or self.height.value()):raise ValueError('Bitte eine Zielbreite oder Zielhöhe eingeben.')
        return upscale_settings(dict(factor=self.factor.currentData() or 2,width=self.width.value() if custom else 0,height=self.height.value() if custom else 0,method=self.method.currentData(),denoise=self.denoise.isChecked(),sharpen=self.sharpen.value()))
    def changed(self,*unused):
        if self.stopped.is_set():return
        self.revision+=1;self.save_button.setEnabled(False);custom=self.factor.currentData()==0;self.width.setEnabled(custom);self.height.setEnabled(custom)
        smooth=self.method.currentData()!='nearest';self.denoise.setEnabled(smooth);self.sharpen_field.setEnabled(smooth)
        self.loading.busy('Vorschau wird vorbereitet …');self.timer.start(180)
    def refresh(self):
        if self.stopped.is_set() or self.job:return
        try:values=self.options()
        except ValueError as error:self.loading.finish();self.status.setText(str(error));return
        revision=self.revision;job=UpscalePreview(self.path,values,self.edit,self.stopped,self.source,self.signature);self.job=job
        job.signals.done.connect(lambda result,error:self.ready(job,revision,result,error));preview_pool().start(job)
    def ready(self,job,revision,result,error):
        self.job=None
        if self.stopped.is_set():return
        if result is not None:self.source,self.signature=result[4],result[5]
        if revision!=self.revision:self.refresh();return
        self.loading.finish()
        if error:self.status.setText(error);return
        before,after,original,size,_,_=result
        for label,image in zip(self.previews,(before,after)):label.setPixmap(QPixmap.fromImage(image));label.setMinimumSize(image.size())
        self.status.setText(f'{original[0]} × {original[1]} → {size[0]} × {size[1]} Pixel · Mittlerer Bildausschnitt, Ergebnis bei 100 % · Original bleibt erhalten.');self.save_button.setEnabled(True)
    def save(self):
        if self.job or not self.save_button.isEnabled():return
        if source_key('upscale',self.path)!=self.signature:
            self.source=None;self.changed();self.status.setText('Bild wurde geändert. Vorschau wird neu geladen.');return
        self.submit('Bild vergrößern',[self.path],{'upscale':self.options(),'edit':self.edit,'source_signature':self.signature});self.accept()
    def done(self,result):self.stopped.set();self.timer.stop();super().done(result)
