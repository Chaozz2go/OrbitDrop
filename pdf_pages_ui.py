from pathlib import Path
import threading
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QSize
from PySide6.QtGui import QImage,QPixmap,QIcon,QTransform,QShortcut,QKeySequence
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QListWidget,QListWidgetItem,QListView,QAbstractItemView,QLabel
from editor_chrome import heading,EDITOR_STYLE,action_button

class PageSignals(QObject):page=Signal(int,object);done=Signal(str)
class PagePreviews(QRunnable):
    def __init__(self,path,stopped):super().__init__();self.path,self.stopped=path,stopped;self.signals=PageSignals()
    def run(self):
        try:
            import pymupdf
            with pymupdf.open(self.path) as pdf:
                for i,page in enumerate(pdf):
                    if self.stopped.is_set():break
                    factor=min(128/max(1,page.rect.width),160/max(1,page.rect.height));pix=page.get_pixmap(matrix=pymupdf.Matrix(factor,factor),alpha=False,colorspace=pymupdf.csRGB)
                    image=QImage(pix.samples,pix.width,pix.height,pix.stride,QImage.Format.Format_RGB888).copy();self.signals.page.emit(i,image)
            self.signals.done.emit('')
        except Exception as error:self.signals.done.emit(str(error))

class PageList(QListWidget):
    def __init__(self,owner):super().__init__(owner);self.owner=owner
    def dropEvent(self,event):
        before=self.owner.entries();super().dropEvent(event)
        if self.owner.entries()!=before:self.owner.history.append(before);self.owner.history=self.owner.history[-100:]
        self.owner.update_status()

class PdfPagesDialog(QDialog):
    def __init__(self,path,submit):
        super().__init__();self.path=str(path);self.submit=submit;self.stopped=threading.Event();self.images={};self.history=[];self.future=[]
        import pymupdf
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass or not pdf.is_pdf:raise ValueError('Bitte ein unverschlüsseltes PDF wählen.')
            self.count=len(pdf)
            if not 1<=self.count<=1000:raise ValueError('Seitenübersicht unterstützt 1 bis 1000 Quellseiten.')
        s=Path(path).stat();self.signature=(s.st_size,s.st_mtime_ns);self.setWindowTitle('OrbitDrop · PDF-Seiten');self.setStyleSheet(EDITOR_STYLE);self.resize(1000,780)
        layout=QVBoxLayout(self);heading(layout,'PDF-Seiten',Path(path).name+' · Mehrfachauswahl mit Strg/Shift · neue PDF-Kopie')
        self.pages=PageList(self);self.pages.setViewMode(QListView.ViewMode.IconMode);self.pages.setResizeMode(QListView.ResizeMode.Adjust);self.pages.setMovement(QListView.Movement.Snap);self.pages.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);self.pages.setDefaultDropAction(Qt.DropAction.MoveAction);self.pages.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.pages.setIconSize(QSize(128,160));self.pages.setGridSize(QSize(165,220));layout.addWidget(self.pages,1)
        # Explicit arrows preserve multi-selection ordering across Qt versions;
        # drag/drop remains available for mouse-based rearrangement.
        row=QHBoxLayout();layout.addLayout(row)
        for text,kind,callback in [('Nach links','previous',lambda:self.move(-1)),('Nach rechts','next',lambda:self.move(1)),('90° drehen','rotate_right',self.rotate),('Duplizieren',None,self.duplicate),('Entfernen','delete',self.remove)]:button=action_button(text,kind);button.clicked.connect(callback);row.addWidget(button)
        self.status=QLabel('Seiten ziehen oder mit den Pfeilen verschieben. Vorschaubilder werden geladen …');self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row);self.undo_button=action_button('Rückgängig','undo');self.undo_button.clicked.connect(self.undo);row.addWidget(self.undo_button);row.addStretch();close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);self.save_button=action_button('Als neues PDF speichern','save',True);self.save_button.clicked.connect(self.save);row.addWidget(self.save_button)
        self.rebuild([{'page':i,'rotation':0} for i in range(self.count)])
        self.shortcuts=[]
        for key,callback in [('Delete',self.remove),('Ctrl+Z',self.undo)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(callback);self.shortcuts.append(shortcut)
        self.job=PagePreviews(self.path,self.stopped);self.job.signals.page.connect(self.preview);self.job.signals.done.connect(self.loaded);QThreadPool.globalInstance().start(self.job)
        area=self.screen().availableGeometry();self.resize(min(1000,area.width()-40),min(780,area.height()-50))
    def entries(self):return [self.pages.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.pages.count())]
    def item(self,entry):
        item=QListWidgetItem();item.setData(Qt.ItemDataRole.UserRole,dict(entry));self.decorate(item);return item
    def decorate(self,item):
        entry=item.data(Qt.ItemDataRole.UserRole);item.setText(f"Seite {entry['page']+1}"+(f" · +{entry['rotation']}°" if entry['rotation'] else ''));image=self.images.get(entry['page'])
        if image is not None:item.setIcon(QIcon(QPixmap.fromImage(image).transformed(QTransform().rotate(entry['rotation']),Qt.TransformationMode.SmoothTransformation)))
    def rebuild(self,entries):
        self.pages.clear()
        for entry in entries:self.pages.addItem(self.item(entry))
        self.update_status()
    def remember(self,*args):self.history.append(self.entries());self.history=self.history[-100:];self.future=[]
    def update_status(self):self.save_button.setEnabled(self.pages.count()>0);self.undo_button.setEnabled(bool(self.history));self.status.setText(f'{self.pages.count()} Seiten in der Ausgabe · Original bleibt erhalten.')
    def preview(self,index,image):
        if self.stopped.is_set():return
        self.images[index]=image
        for i in range(self.pages.count()):
            item=self.pages.item(i)
            if item.data(Qt.ItemDataRole.UserRole)['page']==index:self.decorate(item)
    def loaded(self,error):
        if not self.stopped.is_set():self.update_status();self.status.setText('Vorschaubilder: '+error if error else f'{self.pages.count()} Seiten · Ziehen zum Sortieren; Export speichert die angezeigte Reihenfolge.')
    def selected(self):return sorted(self.pages.row(item) for item in self.pages.selectedItems())
    def rotate(self):
        if not self.selected():return
        self.remember()
        for row in self.selected():
            item=self.pages.item(row);entry=item.data(Qt.ItemDataRole.UserRole);entry['rotation']=(entry['rotation']+90)%360;item.setData(Qt.ItemDataRole.UserRole,entry);self.decorate(item)
        self.update_status()
    def duplicate(self):
        selected=self.selected()
        if not selected or self.pages.count()+len(selected)>2000:return
        self.remember()
        for row in reversed(selected):self.pages.insertItem(row+1,self.item(self.pages.item(row).data(Qt.ItemDataRole.UserRole)))
        self.update_status()
    def remove(self):
        if not self.selected():return
        self.remember()
        for row in reversed(self.selected()):self.pages.takeItem(row)
        self.update_status()
    def move(self,offset):
        rows=self.selected()
        if not rows or rows[0]+offset<0 or rows[-1]+offset>=self.pages.count():return
        self.remember()
        for row in (rows if offset<0 else reversed(rows)):
            item=self.pages.takeItem(row);self.pages.insertItem(row+offset,item);item.setSelected(True)
        self.update_status()
    def undo(self):
        if self.history:self.rebuild(self.history.pop());self.update_status()
    def save(self):
        if self.pages.count():self.submit('PDF-Seiten',[self.path],{'entries':self.entries(),'signature':self.signature});self.accept()
    def done(self,result):self.stopped.set();super().done(result)
