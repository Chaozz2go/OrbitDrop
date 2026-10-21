import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTreeWidget,QTreeWidgetItem,QTextEdit,QCheckBox,QPushButton,QFileDialog,QMessageBox
from app_ui import STYLE

class DiagnosticsDialog(QDialog):
    def __init__(self,store):
        super().__init__();self.store=store;self.setWindowTitle('OrbitDrop · Debugging · Dateierkennung');self.resize(900,620);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);notice=QLabel('Nicht erkannte oder nicht unterstützte Dateien, fehlende Konverter und Erkennungsfehler. Maximal 100 Einträge. Originaldateien werden weder gespeichert noch hochgeladen.');notice.setWordWrap(True);layout.addWidget(notice)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Datei (nur lokal)','Typ','Erkannt als','Anzahl']);self.tree.setColumnWidth(0,320);layout.addWidget(self.tree)
        self.detail=QTextEdit();self.detail.setReadOnly(True);layout.addWidget(self.detail)
        self.names=QCheckBox('Originaldateinamen in Export aufnehmen');self.names.setChecked(False);layout.addWidget(self.names)
        row=QHBoxLayout();layout.addLayout(row)
        for title,callback in [('Diagnose exportieren',self.export),('Liste leeren',self.clear),('Schließen',self.accept)]:
            button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
        self.tree.currentItemChanged.connect(self.selected);self.refresh()
    def refresh(self):
        self.tree.clear();self.detail.clear()
        for record in reversed(self.store.records):
            item=QTreeWidgetItem([record.get('name','Datei'),record.get('extension',''),record.get('kind',''),str(record.get('occurrences',1))]);item.setData(0,Qt.ItemDataRole.UserRole,record);self.tree.addTopLevelItem(item)
        if self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
        else:self.detail.setPlainText('Noch keine Erkennungsprobleme gespeichert.')
    def selected(self,item,previous=None):
        if item:self.detail.setPlainText(json.dumps(item.data(0,Qt.ItemDataRole.UserRole),ensure_ascii=False,indent=2))
    def clear(self):
        try:self.store.clear();self.refresh()
        except OSError as error:QMessageBox.warning(self,'Debugging',str(error))
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Diagnose speichern','OrbitDrop-Diagnose.json','JSON (*.json)',options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:return
        if not path.lower().endswith('.json'):path+='.json'
        try:self.store.export(path,self.names.isChecked());QMessageBox.information(self,'Debugging','Diagnose gespeichert. Diese JSON-Datei kannst du im Chat anhängen.')
        except FileExistsError:QMessageBox.warning(self,'Debugging','Datei existiert bereits. Bitte einen neuen Namen wählen.')
        except OSError as error:QMessageBox.warning(self,'Debugging',str(error))
