from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QListWidget,QPushButton,QFileDialog,
 QSpinBox,QCheckBox,QLineEdit,QDoubleSpinBox,QDialogButtonBox,QLabel,QMessageBox)
from app_ui import STYLE
from tools import TOOLS

class ToolsDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('OrbitDrop · Werkzeuge');self.resize(570,560);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);self.action=QComboBox();self.action.addItems(TOOLS);layout.addWidget(self.action)
        self.files=QListWidget();layout.addWidget(self.files)
        row=QHBoxLayout();layout.addLayout(row)
        for title,callback in [('Hinzufügen',self.add_files),('Entfernen',self.remove),('↑',lambda:self.reorder(-1)),('↓',lambda:self.reorder(1))]:
            button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
        form=QFormLayout();layout.addLayout(form)
        self.width=QSpinBox();self.width.setRange(0,30000);self.width.setValue(1280);self.width.setSuffix(' px');form.addRow('Breite (0 = automatisch)',self.width)
        self.height=QSpinBox();self.height.setRange(0,30000);self.height.setValue(0);self.height.setSuffix(' px');form.addRow('Höhe (0 = automatisch)',self.height)
        self.ratio=QCheckBox('Seitenverhältnis beibehalten');self.ratio.setChecked(True);form.addRow(self.ratio)
        self.angle=QComboBox();self.angle.addItems(['90° rechts','180°','270° rechts']);form.addRow('Drehung',self.angle)
        self.pages=QLineEdit();self.pages.setPlaceholderText('Alle Seiten oder z. B. 1-3,5');form.addRow('Seiten (ein PDF pro Seite)',self.pages)
        self.start=QDoubleSpinBox();self.start.setRange(0,86400);self.start.setDecimals(2);self.start.setSuffix(' s');form.addRow('Clip: Start',self.start)
        self.end=QDoubleSpinBox();self.end.setRange(0,86400);self.end.setDecimals(2);self.end.setValue(10);self.end.setSuffix(' s');form.addRow('Clip: Ende',self.end)
        self.notice=QLabel('PDFs werden in der Listenreihenfolge zusammengefügt. Bilder werden als PNG gespeichert. Ausgabeordner und Videoqualität kommen aus den Einstellungen. Originale bleiben erhalten.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Starten');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Abbrechen');buttons.accepted.connect(self.validate);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.form=form;self.action.currentTextChanged.connect(self.update_fields);self.update_fields()
    def update_fields(self):
        action=self.action.currentText()
        for widget,show in [(self.width,action=='Bildgröße ändern'),(self.height,action=='Bildgröße ändern'),(self.ratio,action=='Bildgröße ändern'),(self.angle,action=='Bild drehen'),(self.pages,action=='PDF aufteilen'),(self.start,False),(self.end,False)]:
            widget.setVisible(show)
            label=self.form.labelForField(widget)
            if label:label.setVisible(show)
    def add_files(self):
        filter='PDF (*.pdf)' if self.action.currentText().startswith('PDF') else 'Alle Dateien (*)'
        paths,_=QFileDialog.getOpenFileNames(self,'Dateien auswählen',filter=filter)
        existing=[self.files.item(i).text() for i in range(self.files.count())]
        for path in paths:
            if path not in existing:self.files.addItem(path);existing.append(path)
    def remove(self):
        row=self.files.currentRow()
        if row>=0:self.files.takeItem(row)
    def reorder(self,offset):
        row=self.files.currentRow();target=row+offset
        if row>=0 and 0<=target<self.files.count():
            item=self.files.takeItem(row);self.files.insertItem(target,item);self.files.setCurrentRow(target)
    def validate(self):
        if not self.files.count():QMessageBox.information(self,'Werkzeug','Bitte Dateien hinzufügen.');return
        if self.action.currentText()=='Video kürzen' and self.files.count()!=1:QMessageBox.information(self,'Werkzeug','Bitte genau ein Video wählen. Danach öffnet sich der Schnitteditor.');return
        self.accept()
    def selection(self):
        return self.action.currentText(),[self.files.item(i).text() for i in range(self.files.count())],{'width':self.width.value(),'height':self.height.value(),'keep_ratio':self.ratio.isChecked(),'angle':[90,180,270][self.angle.currentIndex()],'pages':self.pages.text(),'start':self.start.value(),'end':self.end.value()}
