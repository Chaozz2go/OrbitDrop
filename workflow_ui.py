import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QListWidget,QListWidgetItem,QComboBox,QLineEdit,QSpinBox,QLabel,QMessageBox,QInputDialog
from editor_chrome import heading,EDITOR_STYLE,action_button
from workflows import LABELS,validate_steps,validate_workflows

class WorkflowDialog(QDialog):
    def __init__(self,prefs):
        super().__init__();self.prefs=prefs;self.identifier=None;self.setWindowTitle('OrbitDrop · Bildabläufe');self.setStyleSheet(EDITOR_STYLE);self.resize(780,740)
        layout=QVBoxLayout(self);heading(layout,'Eigene Bildabläufe','Schritte werden in Listenreihenfolge ausgeführt. Ausgabe sind neue Dateien; Originale bleiben erhalten.')
        top=QHBoxLayout();layout.addLayout(top);self.saved=QComboBox();top.addWidget(self.saved,1)
        for text,callback in [('Laden',self.load),('Neu',self.clear),('Löschen',self.delete)]:button=action_button(text);button.clicked.connect(callback);top.addWidget(button)
        self.name=QLineEdit();self.name.setMaxLength(28);self.name.setPlaceholderText('Name, z. B. Bilder fürs Web');layout.addWidget(self.name)
        self.steps=QListWidget();layout.addWidget(self.steps,1)
        row=QHBoxLayout();layout.addLayout(row)
        for text,callback in [('↑',lambda:self.move(-1)),('↓',lambda:self.move(1)),('Schritt entfernen',self.remove)]:button=action_button(text);button.clicked.connect(callback);row.addWidget(button)
        form=QFormLayout();layout.addLayout(form);self.kind=QComboBox()
        for key,label in LABELS.items():self.kind.addItem(label,key)
        form.addRow('Neuer Schritt',self.kind);self.edge=QSpinBox();self.edge.setRange(1,16000);self.edge.setValue(1600);form.addRow('Längste Kante · nur verkleinern',self.edge)
        self.angle=QComboBox()
        for value in (90,180,270):self.angle.addItem(str(value)+'° rechts',value)
        form.addRow('Drehung',self.angle);self.format=QComboBox();self.format.addItems(['WEBP','JPG','PNG','TIFF','BMP']);form.addRow('Format',self.format)
        self.quality=QSpinBox();self.quality.setRange(10,95);self.quality.setValue(82);form.addRow('Qualität',self.quality);self.pattern=QLineEdit('{name}_{n}');form.addRow('Name · {name}, {n} · Endung automatisch',self.pattern);self.form=form
        add=action_button('Schritt hinzufügen');add.clicked.connect(self.add);layout.addWidget(add)
        self.hint=QLabel('Benennen gehört ans Ende. Metadaten entfernen erzeugt eine frische PNG-Kopie. Mehrere verlustbehaftete Komprimierungsschritte können die Qualität verschlechtern.');self.hint.setWordWrap(True);layout.addWidget(self.hint)
        row=QHBoxLayout();layout.addLayout(row);close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);row.addStretch();save=action_button('Ablauf speichern','save',True);save.clicked.connect(self.save);row.addWidget(save)
        self.kind.currentIndexChanged.connect(self.fields);self.fields();self.reload()
    def fields(self,*args):
        kind=self.kind.currentData()
        choices=['WEBP','JPG','PNG'] if kind=='compress' else ['WEBP','JPG','PNG','TIFF','BMP']
        if [self.format.itemText(i) for i in range(self.format.count())]!=choices:
            current=self.format.currentText();self.format.clear();self.format.addItems(choices)
            if current in choices:self.format.setCurrentText(current)
        for widget,visible in [(self.edge,kind=='resize'),(self.angle,kind=='rotate'),(self.format,kind in ('compress','convert')),(self.quality,kind=='compress'),(self.pattern,kind=='rename')]:widget.setVisible(visible);self.form.labelForField(widget).setVisible(visible)
    def reload(self):
        self.saved.clear()
        for item in self.prefs.values.get('workflows',[]):self.saved.addItem(item['name'],item['id'])
    def append(self,step):
        details=' · '.join(str(v) for k,v in step.items() if k!='type');item=QListWidgetItem(LABELS[step['type']]+(' · '+details if details else ''));item.setData(Qt.ItemDataRole.UserRole,step);self.steps.addItem(item)
    def values(self):return [self.steps.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.steps.count())]
    def add(self):
        kind=self.kind.currentData();step={'type':kind}
        if kind=='resize':step['edge']=self.edge.value()
        elif kind=='rotate':step['angle']=self.angle.currentData()
        elif kind in ('compress','convert'):
            step['format']=self.format.currentText()
            if kind=='compress':step['quality']=self.quality.value()
        elif kind=='rename':step['pattern']=self.pattern.text()
        try:
            steps=self.values();position=len(steps)-1 if steps and steps[-1]['type']=='rename' and kind!='rename' else len(steps);steps.insert(position,step);validate_steps(steps);self.append(step)
            if position<self.steps.count()-1:item=self.steps.takeItem(self.steps.count()-1);self.steps.insertItem(position,item)
        except Exception as error:QMessageBox.warning(self,'Ablauf',str(error))
    def remove(self):
        if self.steps.currentRow()>=0:self.steps.takeItem(self.steps.currentRow())
    def move(self,offset):
        row=self.steps.currentRow();target=row+offset
        if row>=0 and 0<=target<self.steps.count():item=self.steps.takeItem(row);self.steps.insertItem(target,item);self.steps.setCurrentRow(target)
    def load(self):
        item=next((item for item in self.prefs.values.get('workflows',[]) if item['id']==self.saved.currentData()),None)
        if not item:return
        self.clear();self.identifier=item['id'];self.name.setText(item['name'])
        for step in item['steps']:self.append(step)
    def clear(self):self.identifier=None;self.name.clear();self.steps.clear()
    def save(self):
        try:
            identifier=self.identifier or str(uuid.uuid4());items=[item for item in self.prefs.values.get('workflows',[]) if item['id']!=identifier];items.append({'id':identifier,'name':self.name.text(),'steps':self.values()});items=validate_workflows(items);self.prefs.update(dict(self.prefs.values,workflows=items));self.identifier=identifier;self.reload();self.saved.setCurrentIndex(self.saved.findData(identifier));self.hint.setText('Gespeichert. Mit einem Bild im Bearbeiten-Kreis oder in der Aktionssuche verfügbar.')
        except Exception as error:QMessageBox.warning(self,'Ablauf',str(error))
    def delete(self):
        identifier=self.saved.currentData()
        if identifier:self.prefs.update(dict(self.prefs.values,workflows=[w for w in self.prefs.values['workflows'] if w['id']!=identifier]));self.reload();self.clear()
