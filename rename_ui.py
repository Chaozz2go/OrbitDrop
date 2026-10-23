from pathlib import Path
from PySide6.QtCore import QObject,Signal,QRunnable,QTimer,QStandardPaths
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QSpinBox,QLabel,QTreeWidget,QTreeWidgetItem,QCheckBox,QComboBox,QFileDialog,QWidget,QScrollArea
from editor_chrome import heading,EDITOR_STYLE,action_button
from loading_ui import LoadingIndicator
from preview_runtime import preview_pool
from task_runtime import TaskControl,Cancelled
from photo_metadata import collect_files,metadata_plan
from batch_rename import rename_with_journal,undo_journal,latest_journal

class RenameSignals(QObject):done=Signal(object,str)
class RenamePreview(QRunnable):
    def __init__(self,inputs,options):super().__init__();self.files=inputs;self.options=options;self.control=TaskControl();self.signals=RenameSignals()
    def run(self):
        try:
            with self.control.activate():
                options=dict(self.options);files,ignored=collect_files(self.files,options.pop('recursive'),options.pop('images_only'));plans,rows=metadata_plan(files,**options)
                self.signals.done.emit((plans,rows,ignored),'')
        except Exception as error:self.signals.done.emit(None,'' if isinstance(error,Cancelled) else str(error))

class RenameJob(QRunnable):
    def __init__(self,plans,root,undo=None):super().__init__();self.plans=plans;self.root=root;self.undo=undo;self.signals=RenameSignals()
    def run(self):
        try:
            if self.undo:outputs=undo_journal(self.undo);journal=None
            else:outputs,journal=rename_with_journal(self.plans,self.root)
            self.signals.done.emit((outputs,journal),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class RenameDialog(QDialog):
    def __init__(self,files,state_root=None):
        super().__init__();self.files=list(files);self.plans=[];self.job=None;self.preview_job=None;self.revision=0;self.closed=False;self.last_result=''
        self.root=Path(state_root or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation));self.journal=latest_journal(self.root)
        self.setWindowTitle('OrbitDrop · Stapel umbenennen');self.setStyleSheet(EDITOR_STYLE);self.resize(990,760)
        layout=QVBoxLayout(self);heading(layout,'Stapel umbenennen','Benennt enthaltene Dateien um. Ordnernamen bleiben bestehen. Erst die Vorschau prüfen; Dateiendungen bleiben erhalten.')
        form_body=QWidget();form=QFormLayout(form_body);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(form_body);scroll.setMaximumHeight(370);layout.addWidget(scroll)
        self.pattern=QLineEdit('{name}_{n}');self.number=QSpinBox();self.number.setRange(0,99_999_000);self.number.setValue(1);self.digits=QSpinBox();self.digits.setRange(1,8);self.digits.setValue(3)
        self.template=QComboBox()
        for title,pattern in [('Eigener Name / Nummer','{name}_{n}'),('Aufnahmedatum und Uhrzeit','{date}_{time}'),('Datum mit Nummer','{date}_{n}'),('Datum und Originalname','{date}_{name}'),('Kamera und Datum','{camera}_{date}_{n}')]:self.template.addItem(title,pattern)
        form.addRow('Vorlage',self.template);form.addRow('Namensmuster',self.pattern)
        hint=QLabel('Bausteine: {name}, {n}, {date}, {time}, {year}, {month}, {day}, {camera}. Beispiel: Urlaub_{date}_{n}');hint.setWordWrap(True);form.addRow(hint)
        form.addRow('Startnummer',self.number);form.addRow('Ziffern',self.digits)
        self.date_format=QComboBox()
        for title,data in [('JJJJ-MM-TT','%Y-%m-%d'),('JJJJMMTT','%Y%m%d'),('TT-MM-JJJJ','%d-%m-%Y')]:self.date_format.addItem(title,data)
        form.addRow('Datumsdarstellung',self.date_format)
        self.missing=QComboBox()
        for title,data in [('Datei überspringen','skip'),('Originalnamen behalten','keep'),('Änderungsdatum der Datei verwenden','mtime')]:self.missing.addItem(title,data)
        form.addRow('Wenn EXIF-Aufnahmedatum fehlt',self.missing)
        self.collision=QComboBox();self.collision.addItem('Nummer anhängen (_2, _3 …)','number');self.collision.addItem('Anhalten und Konflikt anzeigen','error');form.addRow('Bei gleichen Zielnamen',self.collision)
        self.recursive=QCheckBox('Unterordner einbeziehen');self.images_only=QCheckBox('Nur Bilder berücksichtigen');self.images_only.setChecked(any(Path(p).is_dir() for p in self.files))
        form.addRow(self.recursive);form.addRow(self.images_only)
        choose=action_button('Ordner auswählen','folder');choose.clicked.connect(self.choose_folder);form.addRow(choose)
        self.controls=[self.template,self.pattern,self.number,self.digits,self.date_format,self.missing,self.collision,self.recursive,self.images_only,choose]
        self.loading=LoadingIndicator();layout.addWidget(self.loading)
        self.table=QTreeWidget();self.table.setHeaderLabels(['Bisher','Neuer Name','Datumsquelle / Hinweis']);layout.addWidget(self.table,1)
        self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status)
        note=QLabel('Aufnahmedatum: EXIF DateTimeOriginal, wie in der Kamera gespeichert. Änderungsdatum: lokale Windows-Zeit. Kameranamen werden für Windows-Dateinamen bereinigt.');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();layout.addLayout(row);self.undo=action_button('Letzte Umbenennung zurücknehmen','undo');self.undo.setEnabled(bool(self.journal));self.undo.clicked.connect(self.restore);row.addWidget(self.undo);row.addStretch()
        close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);self.start=action_button('Wie angezeigt umbenennen','save',True);self.start.clicked.connect(self.apply);row.addWidget(self.start)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.preview)
        self.template.currentIndexChanged.connect(lambda:self.pattern.setText(self.template.currentData()))
        for widget in (self.pattern,):widget.textChanged.connect(self.changed)
        for widget in (self.number,self.digits):widget.valueChanged.connect(self.changed)
        for widget in (self.date_format,self.missing,self.collision):widget.currentIndexChanged.connect(self.changed)
        self.recursive.toggled.connect(self.changed);self.images_only.toggled.connect(self.changed)
        self.changed()
    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Ordner mit umzubenennenden Dateien auswählen')
        if path:self.files=[path];self.changed()
    def changed(self,*unused):
        if self.closed or self.job:return
        self.revision+=1;self.plans=[];self.last_result='';self.start.setEnabled(False)
        if self.preview_job:self.preview_job.control.cancel()
        self.loading.busy('Ordner und Metadaten werden gelesen …');self.timer.start(180)
    def preview(self):
        if self.closed or self.job:return
        options=dict(pattern=self.pattern.text(),start=self.number.value(),digits=self.digits.value(),date_format=self.date_format.currentData(),missing=self.missing.currentData(),collision=self.collision.currentData(),recursive=self.recursive.isChecked(),images_only=self.images_only.isChecked())
        job=RenamePreview(self.files,options);revision=self.revision;self.preview_job=job
        job.signals.done.connect(lambda result,error:self.preview_ready(job,revision,result,error));preview_pool().start(job)
    def preview_ready(self,job,revision,result,error):
        if self.closed or revision!=self.revision or job is not self.preview_job:return
        self.preview_job=None;self.loading.finish();self.table.clear();self.plans=[]
        if error:self.status.setText(error);return
        if result is None:return
        self.plans,rows,ignored=result;self.table.setUpdatesEnabled(False)
        try:
            for source,target,origin in rows:
                item=QTreeWidgetItem([source.name,target.name,origin]);item.setToolTip(0,str(source));item.setToolTip(1,str(target));self.table.addTopLevelItem(item)
        finally:self.table.setUpdatesEnabled(True)
        changed=sum(str(s)!=str(t) for s,t,_ in self.plans)
        self.status.setText(f'{changed} Dateien werden umbenannt · {len(rows)-len(self.plans)} ohne Aufnahmedatum ausgelassen · {ignored} unpassende Einträge ausgelassen. Vorschau vor dem Start prüfen.')
        if self.last_result:self.status.setText(self.last_result+'\n'+self.status.text())
        self.start.setEnabled(bool(changed));self.table.resizeColumnToContents(0);self.table.resizeColumnToContents(1)
    def run(self,plans,undo=None):
        self.timer.stop();self.revision+=1
        if self.preview_job:self.preview_job.control.cancel()
        self.executing_undo=bool(undo);self.job=RenameJob(plans,self.root,undo)
        for widget in self.controls:widget.setEnabled(False)
        self.start.setEnabled(False);self.undo.setEnabled(False);self.loading.busy('Namen werden zurückgenommen …' if undo else 'Dateien werden umbenannt und protokolliert …')
        self.job.signals.done.connect(self.ready);preview_pool().start(self.job)
    def apply(self):
        if self.plans and self.job is None:self.run(list(self.plans))
    def restore(self):
        if not self.job and self.journal:self.run([],self.journal)
    def ready(self,result,error):
        self.job=None;self.loading.finish()
        for widget in self.controls:widget.setEnabled(True)
        if result:
            self.files,journal=result;self.journal=journal or latest_journal(self.root)
        self.undo.setEnabled(bool(self.journal));self.changed()
        self.last_result=error or ('Namen zurückgenommen.' if self.executing_undo else 'Umbenannt. Das lokale Protokoll ermöglicht die Rücknahme auch nach einem Neustart.');self.status.setText(self.last_result)
    def done(self,result):
        if self.job:self.status.setText('Umbenennung läuft. Bitte kurz warten, damit die Namen vollständig übernommen werden.');return
        self.closed=True;self.timer.stop()
        if self.preview_job:self.preview_job.control.cancel()
        super().done(result)
