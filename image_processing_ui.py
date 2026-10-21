from pathlib import Path
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QTimer
from PySide6.QtGui import QPixmap,QImage,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox,QPushButton,QMessageBox,QScrollArea,QWidget
from editor_chrome import EDITOR_STYLE,heading
from ui_theme import icon
from slider_field import SliderField
from image_editor import pil_qimage
from image_processing import load_image,prepare_image,trace_svg,settings

class PreviewSignals(QObject):done=Signal(object,str)
class ImagePreviewJob(QRunnable):
    def __init__(self,path,target,options):super().__init__();self.path,self.target,self.options=path,target,options;self.signals=PreviewSignals()
    def run(self):
        try:
            original=load_image(self.path);prepared,threshold=prepare_image(original,self.options,vector=self.target=='SVG');svg=None
            if self.target=='SVG':
                svg=trace_svg(prepared,self.options,original.size);rendered=None
            else:
                show=prepared.copy();show.thumbnail((1200,850));rendered=pil_qimage(show)
            original.thumbnail((1200,850));self.signals.done.emit((pil_qimage(original),rendered,threshold,svg),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class ImageProcessingDialog(QDialog):
    def __init__(self,path,target,submit,initial=None):
        super().__init__();self.path=str(path);self.target=target;self.submit=submit;self.job=None;self.pending=False;self.valid=False;self.images=[];self.closed=False
        self.setWindowTitle('OrbitDrop · '+('SVG vektorisieren' if target=='SVG' else 'Schwarzweiß / Bitmap')+' · '+Path(path).name);self.resize(1120,790);self.setStyleSheet(EDITOR_STYLE)
        layout=QVBoxLayout(self);layout.setContentsMargins(22,18,22,18);layout.setSpacing(12)
        heading(layout,'SVG vektorisieren' if target=='SVG' else 'Bitmap erstellen' if target=='BITMAP' else 'Schwarzweiß',Path(path).name+' · Original und Ergebnis im direkten Vergleich')
        body=QHBoxLayout();body.setSpacing(16);layout.addLayout(body,1)
        previews=QHBoxLayout();body.addLayout(previews,1);self.previews=[]
        for title in ('ORIGINAL','ERGEBNIS'):
            column=QVBoxLayout();previews.addLayout(column,1);caption=QLabel(title);caption.setObjectName('editorSubtitle');column.addWidget(caption)
            label=QLabel('Vorschau wird erstellt …');label.setAlignment(Qt.AlignmentFlag.AlignCenter);label.setMinimumSize(180,200);label.setObjectName('previewSurface');column.addWidget(label,1);self.previews.append(label)
        controls=QWidget();controls.setObjectName('editorControls');form=QFormLayout(controls);form.setContentsMargins(16,16,16,16);form.setSpacing(12);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(controls);scroll.setMinimumWidth(320);scroll.setMaximumWidth(370);body.addWidget(scroll);self.fields={};self.slider_fields={}
        self.mode=QComboBox();self.mode.addItem('Schwarzweiß · 1 Bit','binary');self.mode.addItem('Graustufen','gray')
        if target=='SVG':self.mode.addItem('Farbe','color')
        form.addRow('Bildmodus',self.mode)
        self.auto=QCheckBox('Schwellwert automatisch bestimmen');self.auto.setChecked(True);form.addRow(self.auto)
        for key,title,default,low,high,decimals in [('threshold','Schwellwert',128,0,255,0),('contrast','Kontrast',1,.1,3,2),('brightness','Helligkeit',1,.1,3,2),('blur','Glätten vor Umwandlung',0,0,3,1)]:
            box=QSpinBox() if decimals==0 else QDoubleSpinBox();box.setRange(low,high)
            if decimals:box.setDecimals(decimals);box.setSingleStep(.1)
            box.setValue(default);field=SliderField(box,decimals);field.slider.setMinimumWidth(120);form.addRow(title,field);self.slider_fields[key]=field;self.fields[key]=box
        self.invert=QCheckBox('Farben umkehren');form.addRow(self.invert);self.dither=QCheckBox('Rasterung (Floyd–Steinberg) · eher für Fotos');form.addRow(self.dither)
        if target=='SVG':
            for key,title,default,low,high in [('max_edge','Arbeitsauflösung · längste Kante',1600,256,2400),('speckle','Kleine Flecken entfernen · Pixel',4,0,100),('colors','Maximale Farben / Grautöne',16,2,64)]:
                box=QSpinBox();box.setRange(low,high);box.setValue(default);field=SliderField(box);field.slider.setMinimumWidth(120);form.addRow(title,field);self.slider_fields[key]=field;self.fields[key]=box
            box=QDoubleSpinBox();box.setRange(0,5);box.setSingleStep(.1);box.setValue(1);field=SliderField(box,2);field.slider.setMinimumWidth(120);form.addRow('Konturen vereinfachen',field);self.slider_fields['simplify']=field;self.fields['simplify']=box
            self.curve=QComboBox()
            for title,value in [('Weiche Kurven','spline'),('Gerade Kanten','polygon'),('Pixelkonturen','pixel')]:self.curve.addItem(title,value)
            form.addRow('Konturform',self.curve);self.white=QCheckBox('Weißen Hintergrund in SVG aufnehmen');form.addRow(self.white)
        self.status=QLabel('Vorschau wird erstellt …');self.status.setWordWrap(True);layout.addWidget(self.status)
        bottom=QHBoxLayout();layout.addLayout(bottom);reset=QPushButton('Zurücksetzen');reset.clicked.connect(self.reset);bottom.addWidget(reset);bottom.addStretch();self.save_button=QPushButton('Als '+('SVG' if target=='SVG' else 'BMP · 1 Bit' if target=='BITMAP' else 'PNG')+' speichern');self.save_button.setObjectName('primaryAction');self.save_button.setIcon(icon('save','#102e27'));self.save_button.setEnabled(False);self.save_button.clicked.connect(self.save);bottom.addWidget(self.save_button);close=QPushButton('Schließen');close.clicked.connect(self.reject);bottom.addWidget(close)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        self.mode.currentIndexChanged.connect(self.changed);self.auto.toggled.connect(self.changed);self.invert.toggled.connect(self.changed);self.dither.toggled.connect(self.changed)
        for widget in self.fields.values():widget.valueChanged.connect(self.changed)
        if target=='SVG':self.curve.currentIndexChanged.connect(self.changed);self.white.toggled.connect(self.changed)
        if initial:self.mode.setCurrentIndex(self.mode.findData(initial))
        if target=='BITMAP':self.mode.setEnabled(False)
        self.changed()
        area=self.screen().availableGeometry();self.resize(min(1120,area.width()-40),min(790,area.height()-50))
    def options(self):
        values={key:widget.value() for key,widget in self.fields.items()};values.update(mode=self.mode.currentData(),auto_threshold=self.auto.isChecked(),invert=self.invert.isChecked(),dither=self.dither.isChecked())
        if self.target=='SVG':values.update(curve=self.curve.currentData(),white_background=self.white.isChecked())
        return settings(values)
    def changed(self,*args):
        binary=self.mode.currentData()=='binary';self.auto.setEnabled(binary);self.fields['threshold'].setEnabled(binary and not self.auto.isChecked() and not self.dither.isChecked());self.dither.setEnabled(binary)
        if 'colors' in self.fields:self.fields['colors'].setEnabled(not binary)
        for field in self.slider_fields.values():field.update_enabled()
        self.valid=False;self.save_button.setEnabled(False);self.pending=True;self.timer.start(300)
    def refresh(self):
        if self.closed or self.job:return
        self.pending=False;options=self.options();job=ImagePreviewJob(self.path,self.target,options);self.job=job;self.status.setText('Vorschau wird berechnet …');job.signals.done.connect(lambda result,error:self.ready(options,result,error));QThreadPool.globalInstance().start(job)
    def ready(self,options,result,error):
        self.job=None
        if self.closed:return
        if options!=self.options() or self.pending:self.refresh();return
        if error:self.status.setText(error);return
        original,processed,threshold,svg=result
        # Keep renderer QObject creation and destruction on the GUI thread. The
        # worker only computes pixels/paths; no GUI-affine lifetime crosses it.
        if svg:
            renderer=QSvgRenderer(svg.encode());size=renderer.defaultSize();size.scale(1200,850,Qt.AspectRatioMode.KeepAspectRatio)
            processed=QImage(size,QImage.Format.Format_ARGB32);processed.fill(Qt.GlobalColor.white);painter=QPainter(processed);renderer.render(painter);painter.end()
        size=len(svg or '');self.images=[original,processed];self.draw_previews();self.valid=True;self.save_button.setEnabled(True)
        self.status.setText(f'Schwellwert: {threshold}'+(f' · SVG: {size/1024:.1f} KB · Echte Vektorpfade; Fotos werden vereinfacht.' if self.target=='SVG' else ' · Original bleibt erhalten.'))
    def draw_previews(self):
        for label,image in zip(self.previews,self.images):label.setPixmap(QPixmap.fromImage(image).scaled(label.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def resizeEvent(self,event):super().resizeEvent(event);self.draw_previews()
    def reset(self):
        from image_processing import DEFAULTS
        for key,widget in self.fields.items():widget.setValue(DEFAULTS[key])
        self.auto.setChecked(True);self.invert.setChecked(False);self.dither.setChecked(False);self.mode.setCurrentIndex(0)
        if self.target=='SVG':self.white.setChecked(False);self.curve.setCurrentIndex(0)
        self.changed()
    def save(self):
        if not self.valid or self.job or self.pending:return
        self.submit('Bild aufbereiten',[self.path],{'target':self.target,'processing':self.options()});self.accept()

    def done(self,result):
        self.closed=True;self.timer.stop();super().done(result)
