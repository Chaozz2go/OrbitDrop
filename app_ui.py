"""Settings, job history and result actions; all widgets stay on the GUI thread."""
from pathlib import Path
import sys
import uuid
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTreeWidget,QTreeWidgetItem,QProgressBar,
 QDialog,QFormLayout,QLineEdit,QSpinBox,QComboBox,QCheckBox,QDialogButtonBox,QFileDialog,QMessageBox,QInputDialog,QTextEdit,QListWidget,QListWidgetItem,QTabWidget)
from preferences import set_autostart
from window_focus import present

from ui_theme import STYLE,action_button
from editor_chrome import heading



class SettingsDialog(QDialog):
    def __init__(self,prefs,parent=None):
        super().__init__(parent);self.prefs=prefs;self.setWindowTitle('OrbitDrop · Einstellungen');self.setMinimumWidth(620);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);heading(layout,'Einstellungen','OrbitDrop an deine Arbeitsweise anpassen');tabs=QTabWidget();layout.addWidget(tabs);general=QWidget();tabs.addTab(general,'Allgemein');form=QFormLayout(general);v=prefs.values
        row=QHBoxLayout();self.output=QLineEdit(v['output_dir']);self.output.setPlaceholderText('Leer = neben der Originaldatei');row.addWidget(self.output)
        browse=QPushButton('Wählen');browse.clicked.connect(self.choose_folder);row.addWidget(browse);form.addRow('Ausgabeordner',row)
        self.quality=QSpinBox();self.quality.setRange(10,100);self.quality.setValue(v['image_quality']);self.quality.setSuffix(' %');form.addRow('Bildqualität',self.quality)
        self.profile=QComboBox();self.profile.addItems(['Hohe Qualität','Ausgewogen','Kleine Datei']);self.profile.setCurrentText(v['video_profile']);form.addRow('Videoqualität',self.profile)
        self.height=QComboBox()
        for label,value in [('Originalgröße',0),('Maximal 480p',480),('Maximal 720p',720),('Maximal 1080p',1080),('Maximal 1440p',1440),('Maximal 2160p',2160)]:self.height.addItem(label,value)
        self.height.setCurrentIndex(self.height.findData(v['video_height']));form.addRow('Videogröße (MP4/MOV/MKV/WebM)',self.height)
        self.convert=QComboBox();self.convert.addItems(['Shift','Strg','Alt']);self.convert.setCurrentText(v['convert_key']);form.addRow('Konvertieren direkt',self.convert)
        self.edit=QComboBox();self.edit.addItems(['Shift','Strg','Alt']);self.edit.setCurrentText(v['edit_key']);form.addRow('Bearbeiten direkt',self.edit)
        self.files=QComboBox();self.files.addItems(['Shift','Strg','Alt']);self.files.setCurrentText(v['files_key']);form.addRow('Tools (direkter Zugang)',self.files)
        self.startup=QCheckBox('Beim Windows-Anmelden starten');self.startup.setChecked(v['autostart']);self.startup.setEnabled(sys.platform=='win32');self.startup.setToolTip('Gilt für diesen Installationspfad. Nach Verschieben des Programms erneut einstellen.');form.addRow(self.startup)
        self.backends=QCheckBox('Konverter beim Start prüfen');self.backends.setChecked(v['check_backends']);form.addRow(self.backends)
        formats=QWidget();tabs.addTab(formats,'Formate im Kreis');format_layout=QVBoxLayout(formats)
        format_layout.addWidget(QLabel('Haken = im Kreis anzeigen. Ausblenden entfernt nur die Menüoption.'))
        self.format_list=QListWidget();format_layout.addWidget(self.format_list)
        from converter import EXTENSIONS
        for name in sorted(EXTENSIONS):
            item=QListWidgetItem(name);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked if name in v['hidden_formats'] else Qt.CheckState.Checked);self.format_list.addItem(item)
        restore=QPushButton('Alle Formate anzeigen');restore.clicked.connect(lambda:[self.format_list.item(i).setCheckState(Qt.CheckState.Checked) for i in range(self.format_list.count())]);format_layout.addWidget(restore)
        notice=QLabel('Gilt für neue Aufträge. ZIP-/Entpack-Ziele wählst du weiterhin direkt.');notice.setWordWrap(True);layout.addWidget(notice)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Save).setText('Speichern');buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName('primaryAction');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Abbrechen');buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Ausgabeordner wählen',self.output.text())
        if path:self.output.setText(path)
    def save(self):
        try:
            values=dict(self.prefs.values,hidden_formats=[self.format_list.item(i).text() for i in range(self.format_list.count()) if self.format_list.item(i).checkState()==Qt.CheckState.Unchecked],output_dir=self.output.text().strip(),image_quality=self.quality.value(),video_profile=self.profile.currentText(),video_height=self.height.currentData(),convert_key=self.convert.currentText(),edit_key=self.edit.currentText(),files_key=self.files.currentText(),autostart=self.startup.isChecked(),check_backends=self.backends.isChecked())
            values=self.prefs.validate(values)
            if values['output_dir'] and not Path(values['output_dir']).is_dir():raise ValueError('Bitte einen vorhandenen Ausgabeordner wählen.')
            previous=self.prefs.values['autostart']
            set_autostart(values['autostart'])
            try:self.prefs.update(values)
            except Exception:
                set_autostart(previous);raise
            self.accept()
        except Exception as error:QMessageBox.warning(self,'Einstellungen',str(error))

class TasksWindow(QWidget):
    def __init__(self,prefs):
        super().__init__();self.prefs=prefs;self.rows={};self.setWindowTitle('OrbitDrop · Aufträge & Verlauf');self.resize(820,470);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);heading(layout,'Aufträge & Verlauf','Fortschritt, Ergebnisse und zuletzt bearbeitete Dateien')
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Auftrag','Status','Fortschritt / Zeit']);self.tree.setColumnWidth(0,290);self.tree.setColumnWidth(1,260);layout.addWidget(self.tree)
        self.detail=QLabel('Abbrechen stoppt den laufenden Verarbeitungsschritt möglichst früh. Fertige Ergebnisse bleiben erhalten.');self.detail.setWordWrap(True);layout.addWidget(self.detail)
        row=QHBoxLayout();layout.addLayout(row)
        self.cancel=QPushButton('Abbrechen');self.cancel.clicked.connect(self.cancel_selected);row.addWidget(self.cancel)
        self.open=action_button('Ergebnis öffnen','folder',True);self.open.clicked.connect(lambda:self.open_result(False));row.addWidget(self.open)
        self.folder=QPushButton('Ordner anzeigen');self.folder.clicked.connect(lambda:self.open_result(True));row.addWidget(self.folder)
        self.errors=QPushButton('Details');self.errors.clicked.connect(self.details);row.addWidget(self.errors)
        clear=QPushButton('Verlauf leeren');clear.clicked.connect(self.clear_history);row.addWidget(clear)
        self.tree.itemSelectionChanged.connect(self.selection_changed)
        for record in prefs.history[-50:]:self._history_row(record)
        self.selection_changed()
    def _history_row(self,record):
        key=uuid.uuid4().hex;item=QTreeWidgetItem([record.get('title','Auftrag'),record.get('status',''),record.get('time','')]);item.setData(0,Qt.ItemDataRole.UserRole,key);self.tree.insertTopLevelItem(0,item)
        self.rows[key]={'item':item,'record':record,'job':None,'bar':None}
    def add(self,job,title):
        key=uuid.uuid4().hex;item=QTreeWidgetItem([title,'Wird gestartet …','']);item.setData(0,Qt.ItemDataRole.UserRole,key);self.tree.insertTopLevelItem(0,item)
        bar=QProgressBar();bar.setRange(0,0);self.tree.setItemWidget(item,2,bar)
        self.rows[key]={'item':item,'job':job,'bar':bar,'record':{'title':title,'outputs':[],'errors':[],'status':'Läuft'}}
        self.tree.setCurrentItem(item);present(self)
        return key
    def progress(self,key,percent,message):
        data=self.rows.get(key)
        if not data or not data['job']:return
        data['item'].setText(1,message)
        bar=data['bar']
        if percent<0:bar.setRange(0,0)
        else:bar.setRange(0,100);bar.setValue(percent)
    def finish(self,key,outputs,errors,cancelled=False):
        data=self.rows[key];status='Abgebrochen' if cancelled else 'Fehler' if errors and not outputs else 'Teilweise fertig' if errors else 'Fertig'
        data['job']=None;data['item'].setText(1,status)
        data['bar'].setRange(0,100);data['bar'].setValue(100 if status=='Fertig' else data['bar'].value())
        record=data['record'];record.update(outputs=list(outputs),errors=list(errors),status=status)
        try:self.prefs.record(record['title'],outputs,errors,status)
        except OSError as error:record['errors'].append('Verlauf konnte nicht gespeichert werden: '+str(error))
        self.selection_changed()
    def selected(self):
        item=self.tree.currentItem();return self.rows.get(item.data(0,Qt.ItemDataRole.UserRole)) if item else None
    def selection_changed(self):
        data=self.selected();running=bool(data and data['job']);outputs=data['record']['outputs'] if data else []
        self.cancel.setEnabled(running and not data['job'].control.cancelled.is_set());self.open.setEnabled(bool(outputs));self.folder.setEnabled(bool(outputs));self.errors.setEnabled(bool(data))
    def cancel_selected(self):
        data=self.selected()
        if data and data['job']:
            data['job'].control.cancel();data['item'].setText(1,'Abbruch angefordert …');self.cancel.setEnabled(False)
    def open_result(self,folder):
        data=self.selected()
        if not data:return
        outputs=data['record']['outputs']
        if not outputs:return
        choice=outputs[0]
        if len(outputs)>1:
            choice,ok=QInputDialog.getItem(self,'Ergebnis auswählen','Datei/Ordner',outputs,0,False)
            if not ok:return
        path=Path(choice)
        if not path.exists():QMessageBox.information(self,'Ergebnis','Diese Ausgabe ist nicht mehr an ihrem ursprünglichen Ort.');return
        if folder:
            if sys.platform=='win32':
                from file_actions import show_in_explorer
                try:show_in_explorer([str(path)])
                except OSError as error:QMessageBox.warning(self,'Explorer',str(error))
                return
            path=path if path.is_dir() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    def details(self):
        data=self.selected()
        if not data:return
        record=data['record'];box=QMessageBox(self);box.setWindowTitle(record['title']);box.setText(record['status']);box.setDetailedText('\n'.join(record['outputs']+record['errors']) or 'Noch keine Ergebnisse.');box.exec()
    def clear_history(self):
        try:self.prefs.clear_history()
        except OSError as error:QMessageBox.warning(self,'Verlauf',str(error));return
        for key in list(self.rows):
            data=self.rows[key]
            if not data['job']:
                index=self.tree.indexOfTopLevelItem(data['item']);self.tree.takeTopLevelItem(index);del self.rows[key]
        self.selection_changed()
    def has_running(self):return any(data['job'] is not None for data in self.rows.values())
    def cancel_all(self):
        for data in self.rows.values():
            if data['job']:data['job'].control.cancel()
