"""Contextual command search and persistent favorites using the wheel's IDs."""
from pathlib import Path
from PySide6.QtCore import Qt,QObject,QRunnable,Signal,QThreadPool
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QListWidget,QListWidgetItem,QCheckBox,QLabel,QFileDialog
from editor_chrome import heading,EDITOR_STYLE,action_button
from direct_wheel import NAMES

GROUPS={'format':'Konvertieren','edit':'Bearbeiten','tool':'Tools','app':'Programm','download':'Download'}

def action_title(key,titles=None):
    label=key.split(':',1)[-1];return (titles or {}).get(key,NAMES.get(label,label)).replace('\n',' ')


def matching_actions(actions,query,favorites,titles=None,only_favorites=False):
    words=query.casefold().split();unique=list(dict.fromkeys(actions));result=[]
    for key in unique:
        if key in ('app:AKTIONSSUCHE',) or key.endswith(':ZURÜCK'):continue
        text=action_title(key,titles)+' '+GROUPS.get(key.split(':',1)[0],'')
        if only_favorites and key not in favorites or not all(word in text.casefold() for word in words):continue
        result.append(key)
    return sorted(result,key=lambda key:(key not in favorites,action_title(key,titles).casefold()))

class SearchSignals(QObject):done=Signal(object,str,str)
class SearchInspection(QRunnable):
    def __init__(self,files):super().__init__();self.files=files;self.signals=SearchSignals()
    def run(self):
        try:
            from filetypes import common_actions
            actions,kind,message=common_actions(self.files);self.signals.done.emit(actions,kind,message)
        except Exception as error:self.signals.done.emit([], 'Dateiaktionen',str(error))

class ActionSearchDialog(QDialog):
    def __init__(self,actions,prefs,titles=None,files=(),kind=None,formats=(),link=None):
        super().__init__();self.actions=actions;self.prefs=prefs;self.titles={'edit:quick:'+p['id']:p['name'] for p in prefs.values.get('quick_actions',[])};self.titles.update({'edit:flow:'+p['id']:p['name'] for p in prefs.values.get('workflows',[])});self.titles.update(titles or {});self.chosen=None;self.files=list(files);self.kind=kind;self.formats=list(formats);self.link=link;self.jobs=set();self.revision=0;self.closed=False
        self.setWindowTitle('OrbitDrop · Aktionssuche');self.setStyleSheet(EDITOR_STYLE);self.resize(650,620)
        layout=QVBoxLayout(self);heading(layout,'Aktion suchen','Nur Aktionen für die aktuelle Auswahl · Favoriten stehen zuerst und werden gespeichert')
        self.query=QLineEdit();self.query.setPlaceholderText('z. B. PNG, schneiden, PDF oder umbenennen …');layout.addWidget(self.query);choose=action_button('Dateien auswählen','folder');choose.clicked.connect(self.choose_files);layout.addWidget(choose);self.only=QCheckBox('Nur Favoriten');layout.addWidget(self.only)
        self.list=QListWidget();layout.addWidget(self.list,1);self.status=QLabel();layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row);self.favorite=action_button('Favorit setzen');self.favorite.clicked.connect(self.toggle_favorite);row.addWidget(self.favorite);row.addStretch();close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);self.start=action_button('Öffnen',primary=True);self.start.clicked.connect(self.run);row.addWidget(self.start)
        self.query.textChanged.connect(self.filter);self.only.toggled.connect(self.filter);self.list.currentRowChanged.connect(self.selection);self.list.itemDoubleClicked.connect(self.run);self.query.returnPressed.connect(self.run);self.filter();self.query.setFocus()
        if self.files and self.kind=='Dateiaktionen':self.inspect_files()
    def choose_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'Dateien für die Aktionssuche auswählen')
        if files:self.files=files;self.link=None;self.inspect_files()
    def inspect_files(self):
        self.revision+=1;revision=self.revision;self.actions=[];self.filter();self.status.setText('Dateien werden geprüft …');job=SearchInspection(self.files[:]);self.jobs.add(job)
        job.signals.done.connect(lambda actions,kind,message:self.inspected(job,revision,actions,kind,message));QThreadPool.globalInstance().start(job)
    def inspected(self,job,revision,formats,kind,message):
        self.jobs.discard(job)
        if self.closed or revision!=self.revision:return
        from circle_menu import direct_actions
        self.kind=kind;self.formats=list(formats);values=self.prefs.values
        self.actions=direct_actions(self.files,kind,formats,values.get('hidden_formats',[]),presets=values.get('quick_actions',[]),workflows=values.get('workflows',[]));self.filter()
        if not formats:self.status.setText(message or 'Keine Konvertierung verfügbar; Dateiaktionen bleiben nutzbar.')
    def done(self,result):self.closed=True;super().done(result)
    def selected(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
    def filter(self,*args):
        chosen=self.selected();self.list.clear();favorites=self.prefs.values.get('favorite_actions',[])
        from menu_visibility import visible_actions
        for key in matching_actions(visible_actions(self.actions,self.prefs.values),self.query.text(),favorites,self.titles,self.only.isChecked()):
            title=('★  ' if key in favorites else '')+action_title(key,self.titles)+' · '+GROUPS.get(key.split(':',1)[0],'')
            item=QListWidgetItem(title);item.setData(Qt.ItemDataRole.UserRole,key);self.list.addItem(item)
            if key==chosen:self.list.setCurrentItem(item)
        if not self.list.currentItem() and self.list.count():self.list.setCurrentRow(0)
        self.status.setText(f'{self.list.count()} passende Aktionen');self.selection()
    def selection(self,*args):
        key=self.selected();self.start.setEnabled(bool(key));self.favorite.setEnabled(bool(key));self.favorite.setText('Favorit entfernen' if key in self.prefs.values.get('favorite_actions',[]) else 'Favorit setzen')
    def toggle_favorite(self):
        key=self.selected()
        if not key:return
        favorites=list(self.prefs.values.get('favorite_actions',[]))
        if key in favorites:favorites.remove(key)
        else:favorites.append(key)
        self.prefs.update(dict(self.prefs.values,favorite_actions=favorites));self.filter()
    def run(self,*args):
        if self.selected():self.chosen=self.selected();self.accept()
