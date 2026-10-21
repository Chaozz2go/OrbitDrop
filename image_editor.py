from pathlib import Path
import math
from PIL import Image,ImageOps
from PySide6.QtCore import Qt,QRectF,QPointF,Signal,QObject,QRunnable,QThreadPool,QTimer
from PySide6.QtGui import QImage,QPixmap,QPainter,QColor,QPen,QPainterPath
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QComboBox,QFormLayout,QSpinBox,QDoubleSpinBox,QCheckBox,QScrollArea
from editor_chrome import EDITOR_STYLE,heading,toolbar,action_button
from ui_theme import CANVAS,APRICOT,BACKGROUND
from slider_field import SliderField
from photo_effects import adjust_photo,photo_settings,resize_photo,DEFAULTS


def pil_qimage(image):
    image=image.convert('RGBA')
    return QImage(image.tobytes('raw','RGBA'),image.width,image.height,image.width*4,QImage.Format.Format_RGBA8888).copy()

class CropCanvas(QWidget):
    changed=Signal()
    def __init__(self):
        super().__init__();self.setMinimumSize(420,300);self.setMouseTracking(True)
        self.image=None;self.pixmap=None;self.selection=None;self.mode=None;self.anchor=None;self.ratio=0
    def set_image(self,image):
        self.image=image;preview=image.copy();preview.thumbnail((1800,1200));self.pixmap=QPixmap.fromImage(pil_qimage(preview));self.selection=None;self.update();self.changed.emit()
    def image_rect(self):
        if not self.image:return QRectF()
        scale=min((self.width()-24)/self.image.width,(self.height()-24)/self.image.height)
        width,height=self.image.width*scale,self.image.height*scale
        return QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)
    def pixel(self,point):
        rect=self.image_rect()
        return QPointF(max(0,min(self.image.width,(point.x()-rect.left())/rect.width()*self.image.width)),max(0,min(self.image.height,(point.y()-rect.top())/rect.height()*self.image.height)))
    def display(self,selection):
        rect=self.image_rect();sx=rect.width()/self.image.width;sy=rect.height()/self.image.height
        return QRectF(rect.left()+selection.left()*sx,rect.top()+selection.top()*sy,selection.width()*sx,selection.height()*sy)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.fillRect(self.rect(),QColor(BACKGROUND));clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),12,12);painter.fillPath(clip,QColor(CANVAS));painter.setClipPath(clip)
        if not self.pixmap:return
        rect=self.image_rect();painter.drawPixmap(rect.toRect(),self.pixmap)
        if self.selection and self.selection.width()>0 and self.selection.height()>0:
            selected=self.display(self.selection)
            shadow=QPainterPath();shadow.addRect(rect);shadow.addRect(selected);shadow.setFillRule(Qt.FillRule.OddEvenFill)
            painter.fillPath(shadow,QColor(0,0,0,150));painter.setPen(QPen(QColor(APRICOT),2));painter.drawRect(selected)
            painter.setBrush(QColor('#f4faf8'))
            for point in [selected.topLeft(),selected.topRight(),selected.bottomLeft(),selected.bottomRight()]:painter.drawEllipse(point,4,4)
    def mousePressEvent(self,event):
        if not self.image or event.button()!=Qt.MouseButton.LeftButton or not self.image_rect().contains(event.position()):return
        point=self.pixel(event.position());self.mode='new';self.anchor=point;self.original=self.selection
        if self.selection:
            view=self.display(self.selection)
            for corner,opposite in [(view.topLeft(),self.selection.bottomRight()),(view.topRight(),self.selection.bottomLeft()),(view.bottomLeft(),self.selection.topRight()),(view.bottomRight(),self.selection.topLeft())]:
                if (event.position()-corner).manhattanLength()<14:self.anchor=opposite;self.mode='resize';return
            if self.selection.contains(point):self.mode='move'
    def mouseMoveEvent(self,event):
        if not self.mode or not self.image:return
        point=self.pixel(event.position())
        if self.mode=='move':
            delta=point-self.anchor;rect=QRectF(self.original);left=max(0,min(self.image.width-rect.width(),rect.left()+delta.x()));top=max(0,min(self.image.height-rect.height(),rect.top()+delta.y()));rect.moveTopLeft(QPointF(left,top))
        else:
            dx,dy=point.x()-self.anchor.x(),point.y()-self.anchor.y()
            if self.ratio and dx and dy:
                width,height=abs(dx),abs(dy)
                if width/height>self.ratio:width=height*self.ratio
                else:height=width/self.ratio
                point=QPointF(self.anchor.x()+math.copysign(width,dx),self.anchor.y()+math.copysign(height,dy))
            rect=QRectF(self.anchor,point).normalized()
        self.selection=rect;self.update();self.changed.emit()
    def mouseReleaseEvent(self,event):self.mode=None
    def crop_box(self):
        if not self.selection or self.selection.width()<2 or self.selection.height()<2:return None
        rect=self.selection
        return (max(0,int(rect.left())),max(0,int(rect.top())),min(self.image.width,math.ceil(rect.right())),min(self.image.height,math.ceil(rect.bottom())))

class PhotoSignals(QObject):done=Signal(object,str)

class PhotoPreviewJob(QRunnable):
    def __init__(self,image,options):
        super().__init__();self.image=image;self.options=options;self.signals=PhotoSignals()
    def run(self):
        try:self.signals.done.emit(pil_qimage(adjust_photo(self.image,self.options)),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class ImageEditor(QDialog):
    def __init__(self,path,submit,parent=None):
        super().__init__(parent);self.path=str(path);self.submit=submit;self.angle=0;self.closed=False;self.job=None;self.preview_revision=0;self.original_held=False
        self.setWindowTitle('OrbitDrop · Bild bearbeiten · '+Path(path).name);self.resize(1140,780);self.setStyleSheet(EDITOR_STYLE)
        with Image.open(path) as original:
            if getattr(original,'n_frames',1)>1:raise ValueError('Bitte ein Einzelbild wählen.')
            if original.width*original.height>80_000_000:raise ValueError('Bild überschreitet 80 Megapixel.')
            self.original=ImageOps.exif_transpose(original).convert('RGBA')
        self.image=self.original;self.processed=None;self.preview_source=self.image.copy();self.preview_source.thumbnail((1600,1100))
        layout=QVBoxLayout(self);layout.setContentsMargins(22,18,22,18);layout.setSpacing(12)
        heading(layout,'Bild bearbeiten',Path(path).name+' · Ausschnitt, Farben und Größe · neue PNG-Kopie')
        body=QHBoxLayout();body.setSpacing(18);layout.addLayout(body,1)
        left=QVBoxLayout();body.addLayout(left,1);self.canvas=CropCanvas();left.addWidget(self.canvas,1)
        bar,row=toolbar();left.addWidget(bar)
        self.compare=action_button('Original halten','compare',tooltip='Gedrückt halten: unbearbeitetes Original vergleichen');self.compare.setObjectName('originalPreview');self.compare.pressed.connect(lambda:self.compare_original(True));self.compare.released.connect(lambda:self.compare_original(False));row.addWidget(self.compare)
        self.status=QLabel();self.status.setWordWrap(True);left.addWidget(self.status)
        controls=QWidget();controls.setObjectName('editorControls');controls.setMinimumWidth(285);controls.setMaximumWidth(330)
        form=QFormLayout(controls);form.setContentsMargins(16,16,16,16);form.setSpacing(12);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(controls);scroll.setMinimumWidth(305);scroll.setMaximumWidth(350);body.addWidget(scroll)
        self.fields={};self.slider_fields={}
        for key,title,low,high,decimals in [('brightness','Helligkeit',.1,3,2),('contrast','Kontrast',.1,3,2),('saturation','Sättigung',0,3,2),('sharpness','Schärfe',0,3,2),('warmth','Wärme',-100,100,0)]:
            editor=QDoubleSpinBox() if decimals else QSpinBox();editor.setRange(low,high)
            if decimals:editor.setDecimals(decimals);editor.setSingleStep(.05)
            editor.setValue(DEFAULTS[key]);field=SliderField(editor,decimals);field.slider.setMinimumWidth(120);self.fields[key]=editor;self.slider_fields[key]=field;form.addRow(title,field)
        self.gray=QCheckBox('Schwarzweiß / Graustufen');form.addRow(self.gray)
        ratio=QComboBox()
        for title,value in [('Freier Ausschnitt',0),('Quadrat 1:1',1),('16:9',16/9),('4:3',4/3),('Hochformat 9:16',9/16)]:ratio.addItem(title,value)
        ratio.currentIndexChanged.connect(lambda:self.set_ratio(ratio.currentData()));self.ratio=ratio;form.addRow('Ausschnitt',ratio)
        for label,angle,kind in [('',-90,'rotate_left'),('',90,'rotate_right')]:
            button=action_button(label,kind,tooltip='90° links drehen' if angle<0 else '90° rechts drehen');button.setFixedWidth(38);button.clicked.connect(lambda checked=False,a=angle:self.rotate(a));row.addWidget(button)
        reset_crop=action_button('','reset',tooltip='Ausschnitt entfernen');reset_crop.setFixedWidth(38);reset_crop.clicked.connect(self.reset_crop);row.addWidget(reset_crop)
        half_turn=QPushButton('Um 180° drehen');half_turn.clicked.connect(lambda:self.rotate(180));form.addRow(half_turn)
        clear=QPushButton('Ausschnitt entfernen');clear.clicked.connect(self.reset_crop);form.addRow(clear)
        self.width=QSpinBox();self.height=QSpinBox()
        for title,field in [('Breite',self.width),('Höhe',self.height)]:
            field.setRange(0,30000);field.setSpecialValueText('Automatisch');field.setSuffix(' px');form.addRow(title,field)
        self.keep_ratio=QCheckBox('Seitenverhältnis beibehalten');self.keep_ratio.setChecked(True);form.addRow(self.keep_ratio)
        note=QLabel('0 / Automatisch behält die passende Kante bei. Zwei Werte mit Seitenverhältnis bilden einen Begrenzungsrahmen.');note.setWordWrap(True);note.setObjectName('editorSubtitle');form.addRow(note)
        bottom=QHBoxLayout();layout.addLayout(bottom);reset=QPushButton('Alles zurücksetzen');reset.clicked.connect(self.reset);bottom.addWidget(reset);bottom.addStretch()
        cancel=QPushButton('Schließen');cancel.clicked.connect(self.reject);bottom.addWidget(cancel)
        self.save_button=action_button('Als PNG speichern','save',True);self.save_button.clicked.connect(self.save);bottom.addWidget(self.save_button)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        for field in self.fields.values():field.valueChanged.connect(self.changed)
        self.gray.toggled.connect(self.changed)
        for field in (self.width,self.height):field.valueChanged.connect(self.update_status)
        self.keep_ratio.toggled.connect(self.update_status)
        self.canvas.changed.connect(self.update_status);self.canvas.set_image(self.image);self.update_status()
        area=self.screen().availableGeometry();self.resize(min(1140,area.width()-40),min(780,area.height()-50))
    def options(self):return photo_settings({**{key:field.value() for key,field in self.fields.items()},'grayscale':self.gray.isChecked()})
    def changed(self,*unused):
        self.preview_revision+=1;self.save_button.setEnabled(False);self.timer.start(120)
    def refresh(self):
        if self.closed or self.job:return
        preview=self.preview_source.copy();revision=self.preview_revision
        job=PhotoPreviewJob(preview,self.options());self.job=job;job.signals.done.connect(lambda result,error:self.ready(job,revision,result,error));QThreadPool.globalInstance().start(job)
    def ready(self,job,revision,result,error):
        self.job=None
        if self.closed:return
        if revision!=self.preview_revision:self.timer.stop();self.refresh();return
        if error:self.status.setText(error);self.save_button.setEnabled(False);return
        self.processed=result
        if not self.original_held:self.canvas.pixmap=QPixmap.fromImage(result);self.canvas.update()
        self.save_button.setEnabled(True);self.update_status()
    def compare_original(self,held):
        self.original_held=held
        if held:
            preview=self.preview_source;self.canvas.pixmap=QPixmap.fromImage(pil_qimage(preview))
        elif self.processed is not None:self.canvas.pixmap=QPixmap.fromImage(self.processed)
        self.canvas.update()
    def rotate(self,angle):
        self.angle=(self.angle+angle)%360;self.image=self.image.rotate(-angle,expand=True);self.canvas.set_image(self.image);self.preview_source=self.image.copy();self.preview_source.thumbnail((1600,1100));self.processed=None;self.changed()
    def reset_crop(self):self.canvas.selection=None;self.canvas.update();self.update_status()
    def reset(self):
        self.angle=0;self.image=self.original;self.canvas.set_image(self.image);self.preview_source=self.image.copy();self.preview_source.thumbnail((1600,1100));self.processed=None
        for key,field in self.fields.items():field.setValue(DEFAULTS[key])
        self.gray.setChecked(False);self.width.setValue(0);self.height.setValue(0);self.keep_ratio.setChecked(True);self.ratio.setCurrentIndex(0);self.changed()
    def set_ratio(self,ratio):self.canvas.ratio=ratio;self.reset_crop()
    def resize_options(self):return {'width':self.width.value(),'height':self.height.value(),'keep_ratio':self.keep_ratio.isChecked()}
    def update_status(self,*unused):
        box=self.canvas.crop_box();width,height=(box[2]-box[0],box[3]-box[1]) if box else self.image.size
        values=self.resize_options();w,h=values['width'],values['height']
        if w or h:
            if values['keep_ratio']:
                scale=min(w/width if w else float('inf'),h/height if h else float('inf'));width,height=max(1,round(width*scale)),max(1,round(height*scale))
            else:width,height=w or width,h or height
        self.status.setText(f'Ausgabe: {width} × {height} Pixel · Drehung: {self.angle}° · Ausschnitt ziehen, Ecken ändern oder Auswahl verschieben')
    def save(self):
        self.submit('Bild bearbeiten',[self.path],{'angle':self.angle,'crop':self.canvas.crop_box(),'adjustments':self.options(),'resize':self.resize_options()});self.accept()
    def done(self,result):
        self.closed=True;self.timer.stop();super().done(result)
