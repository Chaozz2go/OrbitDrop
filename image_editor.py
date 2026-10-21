from pathlib import Path
import math
from PIL import Image,ImageOps
from PySide6.QtCore import Qt,QRectF,QPointF,Signal
from PySide6.QtGui import QImage,QPixmap,QPainter,QColor,QPen,QPainterPath
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QComboBox
from app_ui import STYLE


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
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#0f121b'))
        if not self.pixmap:return
        rect=self.image_rect();painter.drawPixmap(rect.toRect(),self.pixmap)
        if self.selection and self.selection.width()>0 and self.selection.height()>0:
            selected=self.display(self.selection)
            shadow=QPainterPath();shadow.addRect(rect);shadow.addRect(selected);shadow.setFillRule(Qt.FillRule.OddEvenFill)
            painter.fillPath(shadow,QColor(0,0,0,150));painter.setPen(QPen(QColor('#7ed9ba'),2));painter.drawRect(selected)
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

class ImageEditor(QDialog):
    def __init__(self,path,submit,parent=None):
        super().__init__(parent);self.path=str(path);self.submit=submit;self.angle=0
        self.setWindowTitle('OrbitDrop · Bild zuschneiden / drehen · '+Path(path).name);self.resize(1000,740);self.setStyleSheet(STYLE)
        with Image.open(path) as original:self.image=ImageOps.exif_transpose(original).copy()
        layout=QVBoxLayout(self);self.canvas=CropCanvas();layout.addWidget(self.canvas,1)
        row=QHBoxLayout();layout.addLayout(row)
        for label,angle in [('↶ 90° links',-90),('↷ 90° rechts',90),('180°',180)]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,a=angle:self.rotate(a));row.addWidget(button)
        ratio=QComboBox();ratio.addItem('Freier Ausschnitt',0);ratio.addItem('Quadrat 1:1',1);ratio.addItem('16:9',16/9);ratio.addItem('4:3',4/3);ratio.currentIndexChanged.connect(lambda:self.set_ratio(ratio.currentData()));row.addWidget(ratio)
        reset=QPushButton('Auswahl zurücksetzen');reset.clicked.connect(self.reset);row.addWidget(reset)
        self.status=QLabel();layout.addWidget(self.status);self.canvas.changed.connect(self.update_status);self.canvas.set_image(self.image)
        hint=QLabel('Ausschnitt ziehen · Ecken zum Ändern ziehen · Auswahl zum Verschieben anfassen. Original bleibt erhalten.');layout.addWidget(hint)
        bottom=QHBoxLayout();layout.addLayout(bottom);bottom.addStretch();save=QPushButton('Bild als PNG speichern');save.clicked.connect(self.save);bottom.addWidget(save);cancel=QPushButton('Schließen');cancel.clicked.connect(self.reject);bottom.addWidget(cancel)
    def rotate(self,angle):
        self.angle=(self.angle+angle)%360;self.image=self.image.rotate(-angle,expand=True);self.canvas.set_image(self.image)
    def reset(self):self.canvas.selection=None;self.canvas.update();self.update_status()
    def set_ratio(self,ratio):self.canvas.ratio=ratio;self.reset()
    def update_status(self):
        box=self.canvas.crop_box();size=(box[2]-box[0],box[3]-box[1]) if box else self.image.size
        self.status.setText(f'Ausgabe: {size[0]} × {size[1]} Pixel · Drehung: {self.angle}°')
    def save(self):
        self.submit('Bild bearbeiten',[self.path],{'angle':self.angle,'crop':self.canvas.crop_box()});self.accept()
