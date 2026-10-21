"""Temporary always-on-top shelf; stores references and drags copies."""
from pathlib import Path
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDrag, QCursor, QAction
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QAbstractItemView, QMenu, QFileIconProvider, QMessageBox)
from file_actions import validate_paths, paths_from_urls, file_mime

class ShelfList(QListWidget):
    def __init__(self, shelf):
        super().__init__(shelf)
        self.shelf=shelf
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.context_menu)
        self.icons=QFileIconProvider()

    def add_paths(self,files):
        existing={self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())}
        for path in validate_paths(files):
            if str(path) in existing:continue
            item=QListWidgetItem(path.name or str(path))
            item.setData(Qt.ItemDataRole.UserRole,str(path));item.setToolTip(str(path))
            from PySide6.QtCore import QFileInfo
            item.setIcon(self.icons.icon(QFileInfo(str(path))))
            self.addItem(item);existing.add(str(path))
        self.shelf.update_count()

    def accept_local(self,event):
        try:
            files=paths_from_urls(event.mimeData().urls())
            if not event.possibleActions() & Qt.DropAction.CopyAction:
                raise ValueError('Kopieraktion nicht verfügbar.')
            event.setDropAction(Qt.DropAction.CopyAction);event.accept()
            return files
        except Exception:
            event.ignore();return []

    def dragEnterEvent(self,event):self.accept_local(event)
    def dragMoveEvent(self,event):self.accept_local(event)
    def dropEvent(self,event):
        files=self.accept_local(event)
        if files:self.add_paths(files)

    def selected_paths(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.selectedItems()]

    def startDrag(self,supported_actions):
        files=self.selected_paths()
        try:
            mime=file_mime(files)
        except ValueError as error:
            QMessageBox.information(self,'Ablage',str(error));return
        drag=QDrag(self);drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction,Qt.DropAction.CopyAction)

    def remove_selected(self):
        for item in self.selectedItems():self.takeItem(self.row(item))
        self.shelf.update_count()

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):
            self.remove_selected();event.accept()
        else:super().keyPressEvent(event)

    def context_menu(self,point):
        menu=QMenu(self)
        remove=menu.addAction('Aus Ablage entfernen');remove.triggered.connect(self.remove_selected)
        copy=menu.addAction('Dateien kopieren')
        def do_copy():
            try:QApplication.clipboard().setMimeData(file_mime(self.selected_paths()))
            except ValueError as error:QMessageBox.information(self,'Ablage',str(error))
        copy.triggered.connect(do_copy)
        menu.exec(self.mapToGlobal(point))

class Shelf(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('OrbitDrop · Dateiablage')
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(330,420);self.setMinimumSize(280,260)
        from ui_theme import STYLE
        from editor_chrome import heading
        self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self)
        heading(layout,'Dateiablage','Dateien parken und später weiterziehen')
        top=QHBoxLayout();top.addStretch()
        pin=QPushButton('Andocken');pin.clicked.connect(self.pin_right);top.addWidget(pin)
        layout.addLayout(top)
        info=QLabel('Dateien hier parken und in andere Apps ziehen.\nOriginale bleiben an ihrem Speicherort.')
        info.setWordWrap(True);layout.addWidget(info)
        self.list=ShelfList(self);layout.addWidget(self.list)
        bottom=QHBoxLayout();self.count_label=QLabel();bottom.addWidget(self.count_label);bottom.addStretch()
        clear=QPushButton('Leeren');clear.clicked.connect(self.clear);bottom.addWidget(clear);layout.addLayout(bottom)
        self.update_count()

    def update_count(self):self.count_label.setText(f'{self.list.count()} Einträge')
    def clear(self):self.list.clear();self.update_count()
    def pin_right(self):
        screen=QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen();rect=screen.availableGeometry()
        self.move(rect.right()-self.width()+1,rect.top()+max(0,(rect.height()-self.height())//2))
    def open(self,files=None):
        if files:self.list.add_paths(files)
        if not self.isVisible():self.pin_right()
        self.show();self.raise_()
