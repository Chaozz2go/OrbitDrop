from copy import deepcopy
from pathlib import Path
from PIL import Image,ImageOps
from PySide6.QtCore import Qt,Signal,QPointF,QRectF
from PySide6.QtGui import QPixmap,QPainter,QPen,QColor,QShortcut,QKeySequence
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QSpinBox,QListWidget,QColorDialog
from editor_chrome import EDITOR_STYLE,heading,toolbar
from ui_theme import icon
from image_editor import CropCanvas,pil_qimage
from annotations import render_marks,validate_marks

class MarkCanvas(CropCanvas):
    committed=Signal(dict);moved=Signal(int,object);selected=Signal(int)
    def __init__(self):
        super().__init__();self.tool='redact';self.marks=[];self.active=-1;self.draft=None;self.color='#ff6b5e';self.stroke=5;self.font_size=28;self.text='Text';self.moving=None
    def mousePressEvent(self,event):
        if not self.image or event.button()!=Qt.MouseButton.LeftButton or not self.image_rect().contains(event.position()):return
        point=self.pixel(event.position());self.anchor=point
        if self.tool=='move':
            for index in range(len(self.marks)-1,-1,-1):
                m=self.marks[index];box=QRectF(QPointF(m['x1'],m['y1']),QPointF(m['x2'],m['y2'])).normalized().adjusted(-6,-6,6,6)
                if box.contains(point):self.active=index;self.moving=deepcopy(m);self.selected.emit(index);return
            self.active=-1;return
        self.draft=dict(kind=self.tool,x1=point.x(),y1=point.y(),x2=point.x(),y2=point.y(),color=self.color,stroke=self.stroke,font_size=self.font_size,text=self.text)
        if self.tool=='text':
            self.draft['x2']=min(self.image.width,point.x()+max(20,len(self.text)*self.font_size*.6));self.draft['y2']=min(self.image.height,point.y()+self.font_size*1.3)
    def mouseMoveEvent(self,event):
        if self.anchor is None:return
        point=self.pixel(event.position())
        if self.moving is not None:
            m=self.moving;dx=point.x()-self.anchor.x();dy=point.y()-self.anchor.y();dx=max(-min(m['x1'],m['x2']),min(self.image.width-max(m['x1'],m['x2']),dx));dy=max(-min(m['y1'],m['y2']),min(self.image.height-max(m['y1'],m['y2']),dy))
            self.marks[self.active]={**m,'x1':m['x1']+dx,'x2':m['x2']+dx,'y1':m['y1']+dy,'y2':m['y2']+dy};self.update();return
        if self.draft and self.tool!='text':self.draft.update(x2=point.x(),y2=point.y());self.update()
    def mouseReleaseEvent(self,event):
        if self.moving is not None:
            after=deepcopy(self.marks[self.active]);self.marks[self.active]=self.moving;self.moving=None;self.moved.emit(self.active,after)
        elif self.draft:
            m=self.draft;self.draft=None
            if m['kind']=='text' or abs(m['x2']-m['x1'])+abs(m['y2']-m['y1'])>2:self.committed.emit(m)
        self.anchor=None;self.update()
    def paintEvent(self,event):
        super().paintEvent(event)
        if self.draft or self.moving is not None:
            painter=QPainter(self);painter.setPen(QPen(QColor('#83dfc0'),2,Qt.PenStyle.DashLine))
            m=self.draft or self.marks[self.active];painter.drawRect(self.display(QRectF(QPointF(m['x1'],m['y1']),QPointF(m['x2'],m['y2'])).normalized()));painter.end()

class AnnotationDialog(QDialog):
    def __init__(self,path,submit):
        super().__init__();self.path=str(path);self.submit=submit;self.marks=[];self.undo_stack=[];self.redo_stack=[]
        with Image.open(path) as original:
            if getattr(original,'n_frames',1)>1 or original.width*original.height>80_000_000:raise ValueError('Bitte ein Einzelbild bis 80 Megapixel wählen.')
            self.image=ImageOps.exif_transpose(original).convert('RGBA')
        self.preview=self.image.copy();self.preview.thumbnail((1600,1100))
        self.setWindowTitle('OrbitDrop · Schwärzen & Beschriften');self.setStyleSheet(EDITOR_STYLE);self.resize(1100,780)
        layout=QVBoxLayout(self);heading(layout,'Schwärzen & Beschriften',Path(path).name+' · Markierungen werden fest in eine neue PNG-Kopie geschrieben')
        frame,bar=toolbar();layout.addWidget(frame);self.tool=QComboBox()
        for title,value in [('Schwärzen','redact'),('Pfeil','arrow'),('Rahmen','rectangle'),('Text','text'),('Verschieben','move')]:self.tool.addItem(title,value)
        self.tool.currentIndexChanged.connect(lambda:self.set_tool());bar.addWidget(self.tool)
        self.text=QLineEdit('Text');self.text.setMaxLength(500);self.text.textChanged.connect(lambda text:setattr(self.canvas,'text',text));bar.addWidget(self.text,1)
        self.size=QSpinBox();self.size.setRange(6,500);self.size.setValue(28);self.size.setSuffix(' px Text');self.size.valueChanged.connect(lambda value:setattr(self.canvas,'font_size',value));bar.addWidget(self.size)
        self.stroke=QSpinBox();self.stroke.setRange(1,100);self.stroke.setValue(5);self.stroke.setSuffix(' px Linie');self.stroke.valueChanged.connect(lambda value:setattr(self.canvas,'stroke',value));bar.addWidget(self.stroke)
        color=QPushButton('Farbe');color.clicked.connect(self.choose_color);bar.addWidget(color)
        self.canvas=MarkCanvas();self.canvas.set_image(self.image);layout.addWidget(self.canvas,1)
        self.canvas.committed.connect(self.add_mark);self.canvas.moved.connect(self.move_mark);self.canvas.selected.connect(lambda i:self.items.setCurrentRow(i))
        row=QHBoxLayout();layout.addLayout(row);self.items=QListWidget();self.items.setMaximumHeight(85);row.addWidget(self.items,1)
        delete=QPushButton('Markierung entfernen');delete.clicked.connect(self.remove_mark);row.addWidget(delete)
        self.undo=QPushButton('Rückgängig');self.undo.clicked.connect(self.undo_mark);row.addWidget(self.undo);self.redo=QPushButton('Wiederholen');self.redo.clicked.connect(self.redo_mark);row.addWidget(self.redo)
        self.notice=QLabel('Mit der Maus zeichnen. Schwarz deckt vollständig ab; Farbe gilt für Text, Pfeile und Rahmen. Die Kontrolle sensibler Stellen bleibt bei dir.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        bottom=QHBoxLayout();layout.addLayout(bottom);close=QPushButton('Schließen');close.clicked.connect(self.reject);bottom.addWidget(close);bottom.addStretch();self.save_button=QPushButton('Als neue PNG speichern');self.save_button.setObjectName('primaryAction');self.save_button.setIcon(icon('save','#102e27'));self.save_button.clicked.connect(self.save);bottom.addWidget(self.save_button)
        self.shortcuts=[]
        for key,callback in [('Ctrl+Z',self.undo_mark),('Ctrl+Y',self.redo_mark)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(callback);self.shortcuts.append(shortcut)
        area=self.screen().availableGeometry();self.resize(min(1100,area.width()-40),min(780,area.height()-50));self.redraw()
    def set_tool(self):self.canvas.tool=self.tool.currentData()
    def choose_color(self):
        color=QColorDialog.getColor(QColor(self.canvas.color),self,'Markierungsfarbe')
        if color.isValid():self.canvas.color=color.name()
    def remember(self):self.undo_stack.append(deepcopy(self.marks));self.undo_stack=self.undo_stack[-30:];self.redo_stack=[]
    def add_mark(self,mark):
        if len(self.marks)>=200:self.notice.setText('Maximal 200 Markierungen. Vorhandene Markierung entfernen.');return
        validate_marks([mark],self.image.size);self.remember();self.marks.append(mark);self.redraw()
    def move_mark(self,index,mark):self.remember();self.marks[index]=mark;self.redraw()
    def remove_mark(self):
        index=self.items.currentRow()
        if index>=0:self.remember();self.marks.pop(index);self.redraw()
    def undo_mark(self):
        if self.undo_stack:self.redo_stack.append(deepcopy(self.marks));self.marks=self.undo_stack.pop();self.redraw()
    def redo_mark(self):
        if self.redo_stack:self.undo_stack.append(deepcopy(self.marks));self.marks=self.redo_stack.pop();self.redraw()
    def redraw(self):
        self.canvas.marks=self.marks;self.canvas.active=-1;self.canvas.pixmap=QPixmap.fromImage(pil_qimage(render_marks(self.preview,self.marks,self.image.size)));self.canvas.update();self.items.clear()
        names={'redact':'Schwärzung','arrow':'Pfeil','rectangle':'Rahmen','text':'Text'}
        for i,m in enumerate(self.marks):self.items.addItem(f"{i+1}. {names[m['kind']]}"+(' · '+m['text'][:50] if m['kind']=='text' else ''))
        self.undo.setEnabled(bool(self.undo_stack));self.redo.setEnabled(bool(self.redo_stack));self.save_button.setEnabled(bool(self.marks))
    def save(self):
        if not self.marks:return
        self.submit('Bild markieren',[self.path],{'marks':deepcopy(self.marks)});self.accept()
