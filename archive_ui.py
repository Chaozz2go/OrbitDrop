from pathlib import Path
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QComboBox,QSpinBox,QCheckBox,QFileDialog,QTreeWidget,QTreeWidgetItem,QWidget,QScrollArea
from editor_chrome import EDITOR_STYLE,heading,action_button
from loading_ui import LoadingIndicator
from preview_runtime import preview_pool
from archive_options import LEVELS,sevenzip,list_archive,test_archive
from batch_rename import valid_name
from task_runtime import TaskControl,Cancelled

class ArchiveCreateDialog(QDialog):
    def __init__(self,files,submit,setup=None):
        super().__init__();self.files=list(files);self.submit=submit;self.setup=setup
        self.setWindowTitle('OrbitDrop · Archiv erstellen');self.setStyleSheet(EDITOR_STYLE);self.resize(810,650)
        layout=QVBoxLayout(self);heading(layout,'Archiv erstellen',f'{len(files)} ausgewählte Datei(en)/Ordner · Originale bleiben erhalten')
        form_body=QWidget();form=QFormLayout(form_body);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(form_body);layout.addWidget(scroll,1);self.format=QComboBox()
        for title,data in [('ZIP · kompatibel','ZIP'),('7z · kompakt','7Z'),('TAR.GZ','TAR.GZ')]:self.format.addItem(title,data)
        form.addRow('Format',self.format);self.level=QComboBox();self.level.addItems(LEVELS);self.level.setCurrentText('Ausgewogen');form.addRow('Kompression',self.level)
        self.name=QLineEdit(Path(files[0]).stem if len(files)==1 else 'Auswahl');form.addRow('Archivname ohne Endung',self.name)
        self.folder=QLineEdit(str(Path(files[0]).absolute().parent));row=QHBoxLayout();row.addWidget(self.folder);choose=action_button('Ordner wählen','folder');choose.clicked.connect(self.choose_folder);row.addWidget(choose);form.addRow('Speicherort',row)
        self.password=QLineEdit();self.confirm=QLineEdit()
        for title,field in [('Passwort · leer = ohne Verschlüsselung',self.password),('Passwort wiederholen',self.confirm)]:field.setEchoMode(QLineEdit.EchoMode.Password);form.addRow(title,field)
        self.show_password=QCheckBox('Passwort anzeigen');self.show_password.toggled.connect(self.show_secret);form.addRow(self.show_password)
        self.hide_names=QCheckBox('Auch Dateinamen verschlüsseln · nur 7z');form.addRow(self.hide_names)
        self.split=QSpinBox();self.split.setRange(0,100000);self.split.setSpecialValueText('Nicht aufteilen');self.split.setSuffix(' MiB pro Teil');form.addRow('In Teile aufteilen · benötigt 7-Zip',self.split)
        self.verify=QCheckBox('Archiv nach dem Erstellen auf Fehler prüfen');self.verify.setChecked(True);form.addRow(self.verify)
        note=QLabel('JPG, MP4 und andere bereits komprimierte Dateien werden meist kaum kleiner. ZIP-Passwortschutz nutzt AES-256; zum Öffnen eignet sich z. B. 7-Zip. TAR.GZ bietet hier keinen Passwortschutz und keine Aufteilung. Alle Teile eines geteilten Archivs zusammen aufbewahren und zum Öffnen den ersten Teil (.001) wählen. Passwörter werden nicht gespeichert.');note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.setup_button=action_button('7-Zip im Dashboard einrichten');self.setup_button.clicked.connect(self.open_setup);layout.addWidget(self.setup_button)
        refresh=action_button('7-Zip erneut erkennen');refresh.clicked.connect(self.changed);layout.addWidget(refresh)
        bottom=QHBoxLayout();layout.addLayout(bottom);close=action_button('Schließen');close.clicked.connect(self.reject);bottom.addWidget(close);bottom.addStretch();self.start=action_button('Archiv erstellen','save',True);self.start.clicked.connect(self.apply);bottom.addWidget(self.start)
        for box in (self.format,self.level):box.currentIndexChanged.connect(self.changed)
        for field in (self.name,self.folder,self.password,self.confirm):field.textChanged.connect(self.changed)
        self.split.valueChanged.connect(self.changed);self.hide_names.toggled.connect(self.changed);self.changed()
    def show_secret(self,enabled):
        for field in (self.password,self.confirm):field.setEchoMode(QLineEdit.EchoMode.Normal if enabled else QLineEdit.EchoMode.Password)
    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Archiv speichern in',self.folder.text())
        if path:self.folder.setText(path)
    def open_setup(self):
        if self.setup:self.reject();QTimer.singleShot(0,self.setup)
    def selection(self):
        format=self.format.currentData();suffix={'ZIP':'.zip','7Z':'.7z','TAR.GZ':'.tar.gz'}[format];name=valid_name(self.name.text().strip()+suffix);folder=Path(self.folder.text())
        if not folder.is_dir():raise ValueError('Bitte einen vorhandenen Speicherordner wählen.')
        password=self.password.text() if format!='TAR.GZ' else ''
        if password!=self.confirm.text() and format!='TAR.GZ':raise ValueError('Die Passwörter stimmen nicht überein.')
        options=dict(format=format,level=LEVELS[self.level.currentText()],password=password,hide_names=self.hide_names.isChecked() if format=='7Z' and password else False,split_mb=self.split.value() if format!='TAR.GZ' else 0,verify=self.verify.isChecked())
        if (format=='7Z' or options['split_mb']) and not sevenzip():raise ValueError('Für diese Auswahl wird 7-Zip benötigt. Über das Dashboard einrichten.')
        output=folder/name
        if output.exists() or options['split_mb'] and Path(str(output)+'.001').exists():raise ValueError('Dieser Archivname ist bereits belegt. Bitte einen anderen Namen wählen.')
        return output,options
    def changed(self,*unused):
        kind=self.format.currentData();encrypted=kind!='TAR.GZ'
        for field in (self.password,self.confirm,self.show_password):field.setEnabled(encrypted)
        self.hide_names.setEnabled(kind=='7Z' and bool(self.password.text()));self.split.setEnabled(encrypted)
        self.setup_button.setVisible(not sevenzip() and self.setup is not None)
        try:
            output,options=self.selection();self.status.setText('Ausgabe: '+str(output)+(' · mehrere Teile' if options['split_mb'] else ''));self.start.setEnabled(True)
        except ValueError as error:self.status.setText(str(error));self.start.setEnabled(False)
    def apply(self):
        try:
            output,options=self.selection();self.submit(self.files,str(output),options);self.accept()
        except Exception as error:self.status.setText(str(error))

class ListSignals(QObject):done=Signal(object,str)
class ArchiveListJob(QRunnable):
    def __init__(self,path,password,verify=False):super().__init__();self.path,self.password,self.verify=path,password,verify;self.control=TaskControl();self.signals=ListSignals()
    def run(self):
        try:
            with self.control.activate():
                rows=list_archive(self.path,self.password)
                if self.verify:test_archive(self.path,self.password)
            self.signals.done.emit(rows,'')
        except Exception as error:self.signals.done.emit(None,'' if isinstance(error,Cancelled) else str(error))

class ArchiveExtractDialog(QDialog):
    def __init__(self,files,submit):
        super().__init__();self.files=list(files);self.submit=submit;self.job=None;self.closed=False;self.rows=[]
        self.setWindowTitle('OrbitDrop · Archiv ansehen & entpacken');self.setStyleSheet(EDITOR_STYLE);self.resize(1000,740)
        layout=QVBoxLayout(self);heading(layout,'Archiv ansehen & entpacken','Inhalt prüfen und auswählen · maximal 2 GiB unkomprimierter Inhalt und 10000 Einträge pro Archiv')
        form=QFormLayout();layout.addLayout(form);self.archive=QComboBox()
        for path in files:self.archive.addItem(Path(path).name,str(path))
        form.addRow('Archiv',self.archive);self.password=QLineEdit();self.password.setEchoMode(QLineEdit.EchoMode.Password);form.addRow('Passwort · falls benötigt',self.password)
        self.folder=QLineEdit(str(Path(files[0]).absolute().parent));folder_row=QHBoxLayout();folder_row.addWidget(self.folder);choose=action_button('Ordner wählen','folder');choose.clicked.connect(self.choose_folder);folder_row.addWidget(choose);form.addRow('Zielordner',folder_row)
        self.subfolder=QCheckBox('Eigenen Unterordner je Archiv erstellen');self.subfolder.setChecked(True);form.addRow(self.subfolder)
        self.conflict=QComboBox()
        for title,value in [('Anhalten · nichts überschreiben','error'),('Vorhandene Dateien überspringen','skip'),('Neue Dateien mit Nummer umbenennen','rename'),('Vorhandene Dateien überschreiben','overwrite')]:self.conflict.addItem(title,value)
        form.addRow('Bei Namenskonflikten',self.conflict)
        self.all_archives=QCheckBox('Alle ausgewählten Archive vollständig entpacken');self.all_archives.setChecked(len(files)>1);self.all_archives.setVisible(len(files)>1);form.addRow(self.all_archives)
        buttons=QHBoxLayout();layout.addLayout(buttons);self.load=action_button('Inhalt laden');self.load.clicked.connect(lambda:self.inspect(False));buttons.addWidget(self.load);self.verify=action_button('Archiv auf Fehler prüfen');self.verify.clicked.connect(lambda:self.inspect(True));buttons.addWidget(self.verify)
        for title,state in [('Alles auswählen',True),('Nichts auswählen',False)]:button=action_button(title);button.clicked.connect(lambda checked=False,value=state:self.select_all(value));buttons.addWidget(button)
        self.loading=LoadingIndicator();layout.addWidget(self.loading);self.table=QTreeWidget();self.table.setHeaderLabels(['Datei im Archiv','Größe']);self.table.setColumnWidth(0,650);self.table.itemChanged.connect(self.item_changed);layout.addWidget(self.table,1)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);row=QHBoxLayout();layout.addLayout(row);close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);row.addStretch();self.start=action_button('Auswahl entpacken','save',True);self.start.clicked.connect(self.apply);row.addWidget(self.start)
        self.archive.currentIndexChanged.connect(self.invalidate);self.password.textChanged.connect(self.invalidate);self.all_archives.toggled.connect(self.update_enabled)
        QTimer.singleShot(0,self.inspect)
    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Ziel zum Entpacken',self.folder.text())
        if path:self.folder.setText(path)
    def invalidate(self,*unused):
        if self.job:self.job.control.cancel();self.job=None
        self.rows=[];self.table.clear();self.start.setEnabled(False);self.loading.finish();self.status.setText('Inhalt laden, um die Auswahl zu aktualisieren.')
    def inspect(self,verify=False):
        if self.closed or self.job:return
        self.rows=[];self.table.clear();self.start.setEnabled(False);self.loading.busy('Archiv wird geprüft …' if verify else 'Archivinhalt wird gelesen …')
        job=ArchiveListJob(self.archive.currentData(),self.password.text(),verify);self.job=job;job.signals.done.connect(lambda rows,error:self.ready(job,rows,error));preview_pool().start(job)
    def ready(self,job,rows,error):
        if self.closed or job is not self.job:return
        self.job=None;self.loading.finish()
        if error:self.status.setText(error);return
        self.rows=rows or [];self.table.blockSignals(True)
        for row in self.rows:
            item=QTreeWidgetItem([row['name']+(' /' if row['directory'] else ''),str(row['size'])+' Byte']);item.setData(0,Qt.ItemDataRole.UserRole,row);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(0,Qt.CheckState.Checked);self.table.addTopLevelItem(item)
        self.table.blockSignals(False);self.status.setText(('Archivprüfung erfolgreich. ' if job.verify else '')+f'{len(self.rows)} Einträge · {sum(r["size"] for r in self.rows)/1024/1024:.2f} MiB unkomprimiert.');self.update_enabled()
    def select_all(self,state):
        self.table.blockSignals(True)
        for i in range(self.table.topLevelItemCount()):self.table.topLevelItem(i).setCheckState(0,Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)
        self.table.blockSignals(False);self.update_enabled()
    def item_changed(self,item,*unused):
        row=item.data(0,Qt.ItemDataRole.UserRole)
        if row and row['directory']:
            prefix=row['name'].rstrip('/')+'/'
            self.table.blockSignals(True)
            for i in range(self.table.topLevelItemCount()):
                other=self.table.topLevelItem(i)
                if other.data(0,Qt.ItemDataRole.UserRole)['name'].startswith(prefix):other.setCheckState(0,item.checkState(0))
            self.table.blockSignals(False)
        self.update_enabled()
    def selected(self):return [self.table.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole)['name'] for i in range(self.table.topLevelItemCount()) if self.table.topLevelItem(i).checkState(0)==Qt.CheckState.Checked]
    def update_enabled(self,*unused):
        self.table.setEnabled(not self.all_archives.isChecked());self.start.setEnabled(self.job is None and bool(self.rows) and (self.all_archives.isChecked() or bool(self.selected())))
    def apply(self):
        try:
            folder=Path(self.folder.text())
            if not folder.is_dir():raise ValueError('Bitte einen vorhandenen Zielordner wählen.')
            files=self.files if self.all_archives.isChecked() else [self.archive.currentData()]
            options=dict(password=self.password.text(),selected=None if self.all_archives.isChecked() else self.selected(),conflict=self.conflict.currentData(),subfolder=self.subfolder.isChecked())
            self.submit(files,str(folder),options);self.accept()
        except Exception as error:self.status.setText(str(error))
    def done(self,result):
        self.closed=True
        if self.job:self.job.control.cancel()
        super().done(result)
