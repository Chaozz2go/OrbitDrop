"""Shared local data editor. Workers validate; edits and exports stay explicit."""
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QObject,Signal,QRunnable
from PySide6.QtGui import QColor,QTextCursor,QTextFormat,QFontDatabase
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QTextEdit,QLabel,QComboBox,QLineEdit,QPushButton,QSplitter,QTreeWidget,QTreeWidgetItem,QMessageBox,QApplication
from editor_chrome import EDITOR_STYLE,heading,action_button
from preview_runtime import preview_pool
from task_runtime import TaskControl,checkpoint
from data_formats import read_text,parse,serialize,json_repair,DataProblem,STRUCTURED,records,available_targets

class WorkSignals(QObject):
    done=Signal(object,str)
    progress=Signal(int,str)
class DataWork(QRunnable):
    def __init__(self,operation):super().__init__();self.operation=operation;self.signals=WorkSignals();self.control=TaskControl(self.signals.progress.emit)
    def run(self):
        try:
            with self.control.activate():
                checkpoint();result=self.operation()
            self.signals.done.emit(result,'')
        except Exception as e:self.signals.done.emit(None,str(e))

def export_text(source,text,suffix,output_dir=None,encoding='utf-8',newline=''):
    from converter import reserve
    out=reserve(Path(source),suffix,output_dir)
    try:out.write_text(text,encoding=encoding,newline=newline);return str(out)
    except Exception:out.unlink(missing_ok=True);raise

class ChangePreview(QDialog):
    def __init__(self,before,after,title,parent=None,apply_title='Übernehmen'):
        super().__init__(parent);self.setWindowTitle(title);self.setStyleSheet(EDITOR_STYLE);self.resize(1000,660)
        layout=QVBoxLayout(self);heading(layout,title,'Vorher / Nachher · Die Quelldatei bleibt unverändert')
        split=QSplitter();layout.addWidget(split,1)
        for text in (before,after):
            view=QPlainTextEdit();view.setReadOnly(True);view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont));view.setPlainText(text);split.addWidget(view)
        row=QHBoxLayout();layout.addLayout(row);cancel=action_button('Abbrechen');cancel.clicked.connect(self.reject);row.addWidget(cancel);row.addStretch();apply=action_button(apply_title,primary=True);apply.clicked.connect(self.accept);row.addWidget(apply)

class DataEditor(QDialog):
    def __init__(self,path,kind,output_dir=None,parent=None,target=None):
        super().__init__(parent);self.path=Path(path);self.output_dir=output_dir;self.closed=False;self.jobs=set();self.revision=0;self.issue=None;self.repair=None;self.value=None;self.busy=False;self.initial_target=target;self.writing=0
        self.setWindowTitle('OrbitDrop · Prüfen & Bearbeiten');self.setStyleSheet(EDITOR_STYLE);self.resize(1180,800)
        layout=QVBoxLayout(self);heading(layout,'Prüfen & Bearbeiten',self.path.name+' · lokal · Original bleibt erhalten')
        row=QHBoxLayout();layout.addLayout(row);self.kind=QComboBox();self.kind.addItems(sorted(STRUCTURED|{'CSV','TSV'}));self.kind.setCurrentText(kind if kind in STRUCTURED|{'CSV','TSV'} else 'JSON');row.addWidget(self.kind)
        self.find=QLineEdit();self.find.setPlaceholderText('Im Text suchen …');self.find.returnPressed.connect(self.find_next);row.addWidget(self.find,1)
        find=action_button('Weitersuchen');find.clicked.connect(self.find_next);row.addWidget(find)
        self.position=QLabel();row.addWidget(self.position)
        self.split=QSplitter();layout.addWidget(self.split,1);self.editor=QPlainTextEdit();self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont));self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap);self.editor.setPlaceholderText('Datei wird geladen …');self.editor.setEnabled(False);self.split.addWidget(self.editor)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Schlüssel / Index','Wert / Typ']);self.split.addWidget(self.tree);self.split.setSizes([760,400]);self.tree.itemExpanded.connect(self.expand_item);self.tree.itemDoubleClicked.connect(self.copy_tree_path)
        tree_row=QHBoxLayout();layout.addLayout(tree_row)
        for title,callback in [('Pfad kopieren',self.copy_tree_path),('Wert kopieren',self.copy_tree_value)]:
            button=action_button(title);button.clicked.connect(callback);tree_row.addWidget(button)
        tree_row.addStretch();self.goto=action_button('Zur Fehlerstelle');self.goto.clicked.connect(self.goto_error);tree_row.addWidget(self.goto)
        self.status=QLabel('Datei wird geladen …');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.context=QPlainTextEdit();self.context.setReadOnly(True);self.context.setMaximumHeight(105);self.context.hide();layout.addWidget(self.context)
        hint=QLabel('Neuformatierung/Umwandlung kann Kommentare, XML-Präfixe und Schreibweisen ändern. XML nutzt tag/attributes/text/tail/children; keine Prüfung gegen JSON-Schema/XSD. Doppelte Schlüssel müssen vor dem Export aufgelöst werden.');hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout();layout.addLayout(row);self.format_button=action_button('Lesbar formatieren');self.format_button.clicked.connect(lambda:self.transform(False,False));row.addWidget(self.format_button)
        self.compact=action_button('Kompakt');self.compact.clicked.connect(lambda:self.transform(True,False));row.addWidget(self.compact)
        self.sort=action_button('Schlüssel sortieren');self.sort.clicked.connect(lambda:self.transform(False,True));row.addWidget(self.sort)
        self.fix=action_button('Korrektur ansehen');self.fix.clicked.connect(self.preview_repair);row.addWidget(self.fix)
        row=QHBoxLayout();layout.addLayout(row);self.target=QComboBox();self.target.addItems(['JSON','YAML','TOML','XML','CSV','TSV','JSONL']);row.addWidget(self.target)
        self.pointer=QLineEdit();self.pointer.setPlaceholderText('CSV: optional JSON-Pointer, z. B. /daten');row.addWidget(self.pointer,1)
        convert=action_button('Umwandlung ansehen');convert.clicked.connect(self.convert_preview);row.addWidget(convert)
        self.save=action_button('Neue Datei speichern',primary=True);self.save.clicked.connect(self.save_current);row.addWidget(self.save)
        close=action_button('Schließen');close.clicked.connect(self.close);row.addWidget(close)
        for button in (self.goto,self.fix,self.save):button.setEnabled(False)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(350);self.timer.timeout.connect(self.validate)
        self.editor.textChanged.connect(self.changed);self.editor.cursorPositionChanged.connect(self.cursor_changed);self.kind.currentTextChanged.connect(self.changed)
        self.run(lambda:read_text(path)[0],self.loaded)

    def run(self,operation,callback):
        if self.closed:return
        job=DataWork(operation);self.jobs.add(job)
        def ready(value,error):
            self.jobs.discard(job)
            if not self.closed:callback(value,error)
        job.signals.done.connect(ready);preview_pool().start(job)
    def loaded(self,text,error):
        if error:self.status.setText(error);return
        self.editor.setEnabled(True);self.editor.setPlainText(text);self.editor.document().setModified(False)
        if self.initial_target:
            self.target.setCurrentText(self.initial_target);self.initial_target=None;QTimer.singleShot(0,self.convert_preview)
    def changed(self,*args):
        self.revision+=1;self.value=None;self.issue=None;self.repair=None;self.tree.clear();self.goto.setEnabled(False);self.fix.setEnabled(False);self.save.setEnabled(False);self.status.setText('Wird geprüft …');self.timer.start()
    def validate(self):
        if not self.editor.isEnabled():return
        revision=self.revision;text=self.editor.toPlainText();kind=self.kind.currentText()
        def check():
            try:return parse(text,kind),None,None
            except DataProblem as issue:return None,issue,json_repair(text) if kind=='JSON' else None
        self.run(check,lambda result,error:self.validated(revision,text,result,error))
    def validated(self,revision,text,result,error):
        if revision!=self.revision:return
        self.editor.setExtraSelections([]);self.context.hide()
        if error:self.status.setText(error);return
        self.value,self.issue,self.repair=result;self.fix.setEnabled(self.repair is not None);self.goto.setEnabled(self.issue is not None)
        if self.issue:
            issue=self.issue;self.status.setText(str(issue));lines=text.splitlines();start=max(0,issue.line-3);end=min(len(lines),issue.line+2)
            self.context.setPlainText('\n'.join(f'{n+1:>5} '+lines[n] for n in range(start,end)));self.context.show()
            selection=QTextEdit.ExtraSelection();selection.cursor=self.editor.textCursor();selection.cursor.setPosition(self.qt_position(text,issue.position));selection.cursor.select(QTextCursor.SelectionType.LineUnderCursor);selection.format.setBackground(QColor('#663e35'));selection.format.setProperty(QTextFormat.Property.FullWidthSelection,True);self.editor.setExtraSelections([selection])
        else:
            self.status.setText('Syntax gültig · Struktur ansehen oder als neue Datei speichern.');self.save.setEnabled(True);root=QTreeWidgetItem(['/','Objekt' if isinstance(self.value,dict) else 'Liste' if isinstance(self.value,list) else str(self.value)[:200]]);root.setData(0,Qt.ItemDataRole.UserRole,(self.value,''));self.tree.addTopLevelItem(root);self.add_placeholder(root,self.value);root.setExpanded(True)
    @staticmethod
    def qt_position(text,index):return len(text[:index].encode('utf-16-le'))//2
    def cursor_changed(self):
        c=self.editor.textCursor();self.position.setText(f'Zeile {c.blockNumber()+1} · Spalte {c.positionInBlock()+1}')
    def goto_error(self):
        if self.issue:
            c=self.editor.textCursor();c.setPosition(self.qt_position(self.editor.toPlainText(),self.issue.position));self.editor.setTextCursor(c);self.editor.centerCursor();self.editor.setFocus()
    def add_placeholder(self,item,value):
        if isinstance(value,(dict,list)) and value:item.addChild(QTreeWidgetItem(['…']))
    def expand_item(self,item):
        data=item.data(0,Qt.ItemDataRole.UserRole)
        if data is None or item.childCount()!=1 or item.child(0).data(0,Qt.ItemDataRole.UserRole) is not None:return
        item.takeChildren();value,path=data;entries=value.items() if isinstance(value,dict) else enumerate(value)
        for n,(key,v) in enumerate(entries):
            if n>=2000:item.addChild(QTreeWidgetItem(['Weitere Einträge im Text ansehen …']));break
            pointer=path+'/'+str(key).replace('~','~0').replace('/','~1');label=f'Objekt · {len(v)}' if isinstance(v,dict) else f'Liste · {len(v)}' if isinstance(v,list) else str(v)[:300]
            child=QTreeWidgetItem([str(key),label]);child.setData(0,Qt.ItemDataRole.UserRole,(v,pointer));item.addChild(child);self.add_placeholder(child,v)
    def copy_tree_path(self,*args):
        item=self.tree.currentItem();data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if data is not None:QApplication.clipboard().setText(data[1])
    def copy_tree_value(self):
        item=self.tree.currentItem();data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if data is not None:
            try:QApplication.clipboard().setText(serialize(data[0],'JSON'))
            except ValueError:self.status.setText('Dieser Wert ist kein JSON-Wert; bitte Textansicht verwenden.')
    def find_next(self):
        text=self.find.text()
        if text and not self.editor.find(text):self.editor.moveCursor(QTextCursor.MoveOperation.Start);self.editor.find(text)
    def apply_change(self,text):
        cursor=self.editor.textCursor();cursor.beginEditBlock();cursor.select(QTextCursor.SelectionType.Document);cursor.insertText(text);cursor.endEditBlock()
    def preview_repair(self):
        if self.repair:
            title,after=self.repair;before=self.editor.toPlainText()
            if ChangePreview(before,after,title,self).exec():self.apply_change(after)
    def transform(self,compact,sort):
        text=self.editor.toPlainText();kind=self.kind.currentText();revision=self.revision
        def operation():
            if compact and kind not in ('JSON','JSONL'):raise ValueError('Kompakt ist für JSON/JSONL verfügbar.')
            if sort and kind=='XML':raise ValueError('XML-Kinder werden nicht sortiert, da ihre Reihenfolge Bedeutung hat.')
            return serialize(parse(text,kind),kind,compact,sort)
        def ready(after,error):
            if revision!=self.revision:return
            if error:self.status.setText(error);return
            if ChangePreview(text,after,'Änderung prüfen',self).exec():self.apply_change(after)
        self.run(operation,ready)
    def convert_preview(self):
        text=self.editor.toPlainText();kind=self.kind.currentText();target=self.target.currentText();pointer=self.pointer.text();revision=self.revision
        def operation():
            value=parse(text,kind)
            if target in ('CSV','TSV'):value,_=records(value,pointer)
            return serialize(value,target)
        def ready(after,error):
            if revision!=self.revision:return
            if error:self.status.setText(error);return
            if ChangePreview(text,after,'Umwandlung nach '+target,self,'Neue Datei speichern').exec():self.write(after,target)
        self.run(operation,ready)
    def save_current(self):
        text=self.editor.toPlainText();kind=self.kind.currentText();revision=self.revision
        def operation():parse(text,kind);return text
        def ready(result,error):
            if revision!=self.revision:return
            if error:self.status.setText(error)
            else:self.write(result,kind)
        self.run(operation,ready)
    def write(self,text,kind):
        if self.writing:self.status.setText('Speichern läuft bereits …');return
        self.writing+=1;suffix='.'+kind.lower()
        revision=self.revision
        def saved(path,error):
            self.writing-=1
            self.status.setText(error or 'Neue Datei gespeichert: '+path)
            if not error and kind==self.kind.currentText() and revision==self.revision and text==self.editor.toPlainText():self.editor.document().setModified(False)
        self.run(lambda:export_text(self.path,text,suffix,self.output_dir),saved)
    def closeEvent(self,event):
        if self.writing:
            self.status.setText('Datei wird noch gespeichert. Danach schließen.');event.ignore();return
        if self.editor.document().isModified():
            if QMessageBox.question(self,'Änderungen verwerfen?','Nicht gespeicherte Änderungen verwerfen?',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:event.ignore();return
        self.closed=True;self.timer.stop()
        for job in self.jobs:job.control.cancel()
        super().closeEvent(event)
    def reject(self):self.close()
