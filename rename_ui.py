from pathlib import Path
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QSpinBox,QLabel,QTreeWidget,QTreeWidgetItem
from editor_chrome import heading,EDITOR_STYLE,action_button
from batch_rename import plan_renames,execute_renames,validate_pairs

class RenameSignals(QObject):done=Signal(object,str)
class RenameJob(QRunnable):
    def __init__(self,plans):super().__init__();self.plans=plans;self.signals=RenameSignals()
    def run(self):
        try:self.signals.done.emit(execute_renames(self.plans),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class RenameDialog(QDialog):
    def __init__(self,files):
        super().__init__();self.files=list(files);self.plans=[];self.job=None;self.undo_pairs=None;self.executing_undo=False
        self.setWindowTitle('OrbitDrop · Stapel umbenennen');self.setStyleSheet(EDITOR_STYLE);self.resize(840,650)
        layout=QVBoxLayout(self);heading(layout,'Stapel umbenennen','Ändert die Namen der Originaldateien. Erst die Vorschau prüfen; Dateiendungen bleiben erhalten.')
        form=QFormLayout();layout.addLayout(form);self.pattern=QLineEdit('{name}_{n}');self.number=QSpinBox();self.number.setRange(0,99_999_000);self.number.setValue(1);self.digits=QSpinBox();self.digits.setRange(1,8);self.digits.setValue(3)
        form.addRow('Muster · {name} = bisheriger Name · {n} = Nummer',self.pattern);form.addRow('Startnummer',self.number);form.addRow('Ziffern',self.digits)
        self.table=QTreeWidget();self.table.setHeaderLabels(['Bisher','Neuer Name']);layout.addWidget(self.table,1);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row);self.undo=action_button('Letzte Umbenennung zurücknehmen','undo');self.undo.setEnabled(False);self.undo.clicked.connect(self.restore);row.addWidget(self.undo);row.addStretch();close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);self.start=action_button('Wie angezeigt umbenennen','save',True);self.start.clicked.connect(self.apply);row.addWidget(self.start)
        self.pattern.textChanged.connect(self.preview);self.number.valueChanged.connect(self.preview);self.digits.valueChanged.connect(self.preview);self.preview()
    def preview(self,*args):
        self.table.clear();self.plans=[]
        try:
            self.plans=plan_renames(self.files,self.pattern.text(),self.number.value(),self.digits.value())
            for source,target,_ in self.plans:
                item=QTreeWidgetItem([source.name,target.name]);item.setToolTip(0,str(source));self.table.addTopLevelItem(item)
            self.status.setText(f'{len(self.plans)} Dateien · keine Namenskonflikte.');self.start.setEnabled(self.job is None and any(s!=t for s,t,_ in self.plans))
        except Exception as error:self.status.setText(str(error));self.start.setEnabled(False)
        self.table.resizeColumnToContents(0)
    def run(self,plans,undo=False):
        self.executing_undo=undo;self.job=RenameJob(plans);self.current_plan=plans;self.start.setEnabled(False);self.undo.setEnabled(False);self.pattern.setEnabled(False);self.number.setEnabled(False);self.digits.setEnabled(False);self.status.setText('Dateien werden umbenannt …');self.job.signals.done.connect(self.ready);QThreadPool.globalInstance().start(self.job)
    def apply(self):
        if self.plans and self.job is None:self.run(self.plans)
    def restore(self):
        if self.job or not self.undo_pairs:return
        try:self.run(self.undo_pairs,True)
        except Exception as error:self.status.setText('Rücknahme nicht möglich: '+str(error))
    def ready(self,outputs,error):
        self.job=None;self.pattern.setEnabled(True);self.number.setEnabled(True);self.digits.setEnabled(True)
        if outputs:
            self.files=outputs;self.undo_pairs=None
            if not self.executing_undo:
                try:self.undo_pairs=validate_pairs([(target,source) for source,target,_ in self.current_plan])
                except Exception:pass
        self.preview();self.undo.setEnabled(bool(self.undo_pairs));self.status.setText(error if error else 'Namen zurückgenommen.' if self.executing_undo else 'Umbenannt. Die Rücknahme ist bis zum Schließen dieses Fensters verfügbar.')
    def done(self,result):
        if self.job:self.status.setText('Umbenennung läuft. Bitte kurz warten.');return
        super().done(result)
