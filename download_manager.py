"""Persistent download workspace with explicit selection and a serial session queue."""
import uuid
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QListWidget,QTreeWidget,QTreeWidgetItem,QTabWidget,QSplitter,QScrollArea,QLabel,QPushButton,QInputDialog,QMessageBox)
from download_ui import DownloadDialog
from link_selection import media_link
from ui_theme import STYLE,action_button
from editor_chrome import heading


class DownloadComposer(DownloadDialog):
    def __init__(self,manager,folder):
        self.manager=manager
        super().__init__(None,'audio',folder,manager.enqueue,parent=manager)
        self.setWindowFlags(Qt.WindowType.Widget);self.setMinimumWidth(0);self.layout().addStretch()
        self.start.setText('Zur Warteschlange hinzufügen')
    def accept(self):
        # DownloadDialog calls accept after a successful submission. Keep the
        # editor and its inspected playlist visible for further work.
        self.manager.notice.setText('Zur Warteschlange hinzugefügt. Du kannst weitere Links vorbereiten.')
        self.manager.refresh_controls()
    def reject(self):pass
    def done(self,result):pass
    def update_enabled(self,*args):
        super().update_enabled(*args)
        count=len(self.selected_entries()) if self.info and self.info.get('playlist') else 0
        self.start.setText(f'{count} Titel zur Warteschlange hinzufügen' if count else 'Zur Warteschlange hinzufügen')


class DownloadManager(QWidget):
    def __init__(self,controller):
        super().__init__();self.controller=controller;self.records={};self.waiting=[];self.current=None;self.paused=False;self.inbox_urls=set()
        self.setWindowTitle('OrbitDrop · Audio/Video-Downloader');self.setStyleSheet(STYLE);self.resize(1130,800);self.setMinimumSize(820,560)
        layout=QVBoxLayout(self);heading(layout,'Audio/Video-Downloader','Links sammeln, Titel auswählen und Downloads übersichtlich verwalten')
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        work=QSplitter();self.tabs.addTab(work,'Links & Auswahl')
        left=QWidget();side=QVBoxLayout(left);work.addWidget(left)
        text=QLabel('Mehrere Links einfügen · ein Link pro Zeile');text.setWordWrap(True);side.addWidget(text)
        self.paste=QPlainTextEdit();self.paste.setPlaceholderText('https://…\nhttps://…');self.paste.setMaximumHeight(135);side.addWidget(self.paste)
        add=action_button('Links übernehmen',primary=True);add.clicked.connect(self.collect);side.addWidget(add)
        self.inbox=QListWidget();self.inbox.setToolTip('Link auswählen und rechts prüfen. Es startet noch kein Download.');self.inbox.currentItemChanged.connect(self.pick_link);side.addWidget(self.inbox,1)
        remove=action_button('Link aus Liste entfernen');remove.clicked.connect(self.remove_link);side.addWidget(remove)
        folder=controller.prefs.values.get('download_dir') or controller.prefs.values.get('output_dir','')
        if folder and not Path(folder).is_dir():folder=''
        self.composer=DownloadComposer(self,folder);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.composer);work.addWidget(scroll);work.setSizes([270,810])
        queue=QWidget();ql=QVBoxLayout(queue);self.tabs.addTab(queue,'Warteschlange & Verlauf')
        self.summary=QLabel();ql.addWidget(self.summary)
        self.queue=QTreeWidget();self.queue.setHeaderLabels(['Download / Link','Typ','Status','Fortschritt']);self.queue.setColumnWidth(0,475);self.queue.setColumnWidth(1,70);self.queue.setColumnWidth(2,170);self.queue.itemSelectionChanged.connect(self.refresh_controls);ql.addWidget(self.queue,1)
        row=QHBoxLayout();ql.addLayout(row)
        self.pause=action_button('Warteschlange pausieren');self.pause.setCheckable(True);self.pause.toggled.connect(self.set_paused);row.addWidget(self.pause)
        self.cancel=action_button('Abbrechen');self.cancel.clicked.connect(self.cancel_selected);row.addWidget(self.cancel)
        self.retry=action_button('Erneut einreihen');self.retry.clicked.connect(self.retry_selected);row.addWidget(self.retry)
        self.remove=action_button('Aus Liste entfernen');self.remove.clicked.connect(self.remove_selected);row.addWidget(self.remove)
        row2=QHBoxLayout();ql.addLayout(row2)
        for label,delta in [('Nach oben',-1),('Nach unten',1)]:
            button=action_button(label);button.clicked.connect(lambda checked=False,d=delta:self.move_selected(d));row2.addWidget(button)
        self.open=action_button('Ergebnis öffnen');self.open.clicked.connect(lambda:self.open_result(False));row2.addWidget(self.open)
        self.folder=action_button('Ordner anzeigen');self.folder.clicked.connect(lambda:self.open_result(True));row2.addWidget(self.folder)
        details=action_button('Details');details.clicked.connect(self.show_details);row2.addWidget(details)
        hint=QLabel('Downloads laufen nacheinander. Pausieren hält nur die wartenden Aufträge an. Schließen lässt laufende und wartende Downloads weiterlaufen. Die Warteschlange gilt für diese OrbitDrop-Sitzung; abgeschlossene Aufträge bleiben im Verlauf.');hint.setWordWrap(True);ql.addWidget(hint)
        self.notice=QLabel('Link prüfen, Audio oder Video wählen und zur Warteschlange hinzufügen.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        close=action_button('Fenster schließen');close.clicked.connect(self.close);layout.addWidget(close)
        for record in controller.prefs.history[-50:]:
            if record.get('title','').startswith('Download ·'):
                self.add_record(None,record['title'],record.get('status','Fertig'),record.get('outputs',[]),record.get('errors',[]))
        self.refresh_controls()
    def open_link(self,url=None,mode='audio'):
        if not url:return
        url=media_link(url)
        if not url:return
        self.tabs.setCurrentIndex(0);self.composer.mode.setCurrentIndex(1 if mode=='video' else 0)
        self.composer.url.setText(url)
        if url not in self.inbox_urls:self.inbox.addItem(url);self.inbox_urls.add(url)
        if self.composer.inspection is None:self.composer.inspect()
        self.notice.setText('Neuer Link übernommen. Auswahl und Warteschlange bleiben erhalten.')
    def collect(self):
        lines=[line.strip() for line in self.paste.toPlainText().splitlines() if line.strip()]
        if len(lines)>1000 or self.inbox.count()+len(lines)>2000:
            self.notice.setText('Bitte höchstens 1.000 Links auf einmal und 2.000 Links in der Liste sammeln.');return
        added=invalid=0
        for line in lines:
            url=media_link(line)
            if not url:invalid+=1;continue
            if url not in self.inbox_urls:self.inbox.addItem(url);self.inbox_urls.add(url);added+=1
        self.notice.setText(f'{added} neue Links gesammelt.'+(f' {invalid} ungültige Zeilen bitte korrigieren.' if invalid else ' Wähle einen Link und prüfe rechts die Auswahl.'))
        if not invalid:self.paste.clear()
    def pick_link(self,item,previous):
        if item:
            self.composer.url.setText(item.text());self.notice.setText('Rechts „Link prüfen“ wählen. Erst deine Download-Auswahl erstellt einen Auftrag.')
    def remove_link(self):
        row=self.inbox.currentRow()
        if row>=0:
            item=self.inbox.takeItem(row);self.inbox_urls.discard(item.text())
    def add_record(self,request,title,state='Wartet',outputs=(),errors=()):
        key=uuid.uuid4().hex;item=QTreeWidgetItem([title,('Audio' if request['mode']=='audio' else 'Video') if request else '',state,''])
        item.setData(0,Qt.ItemDataRole.UserRole,key);self.queue.addTopLevelItem(item)
        self.records[key]={'request':request,'title':title,'state':state,'outputs':list(outputs),'errors':list(errors),'job':None,'item':item}
        return key
    def enqueue(self,url,mode,folder,height,entries=None):
        if not media_link(url) or mode not in ('audio','video') or not Path(folder).is_dir():raise ValueError('Bitte gültigen Link, Audio/Video und einen vorhandenen Ordner wählen.')
        if height not in (0,480,720,1080,1440,2160,4320) and (not isinstance(height,int) or not 1<=height<=16384):raise ValueError('Ungültige Videoqualität.')
        if entries is not None:
            if not entries or len(entries)>10000 or any(not media_link(e.get('url')) or not e.get('available') for e in entries):raise ValueError('Bitte verfügbare Playlist-Titel wählen.')
            entries=[dict(e) for e in entries]
        if len(self.waiting)>=1000:raise ValueError('Bitte zuerst einen Teil der Warteschlange abarbeiten.')
        self.controller.prefs.update(dict(self.controller.prefs.values,download_dir=str(Path(folder).resolve())))
        request={'url':url,'mode':mode,'folder':str(Path(folder).resolve()),'height':height,'entries':entries}
        if any(record['request']==request and (record['state']=='Wartet' or record['job'] is not None) for record in self.records.values()):raise ValueError('Dieser Download läuft bereits oder steht in der Warteschlange.')
        title=(self.composer.info or {}).get('title') if self.composer.inspected_url==url else None
        title=title or url
        if entries is not None:title+=f' · {len(entries)} Titel'
        key=self.add_record(request,title);self.waiting.append(key);self.queue.setCurrentItem(self.records[key]['item']);self.refresh_controls()
        QTimer.singleShot(0,self.start_next)
        return key
    def start_next(self):
        if self.paused or self.current:return
        while self.waiting:
            key=self.waiting.pop(0);record=self.records.get(key)
            if not record or record['state']!='Wartet':continue
            self.current=key;record['state']='Läuft';record['item'].setText(2,'Läuft');request=record['request']
            def observe(job,k=key):
                self.records[k]['job']=job
                job.signals.progress.connect(lambda percent,message:self.progress(k,percent,message))
                job.signals.done.connect(lambda outputs,errors:self.finished(k,job,outputs,errors))
            try:self.controller.submit_download(request['url'],request['mode'],request['folder'],request['height'],request['entries'],show_tasks=False,observer=observe)
            except Exception as error:
                record['state']='Fehler';record['errors']=[str(error)];record['job']=None;record['item'].setText(2,'Fehler');self.current=None;QTimer.singleShot(0,self.start_next)
            self.refresh_controls();return
        self.refresh_controls()
    def progress(self,key,percent,message):
        record=self.records.get(key)
        if not record or record['job'] is None:return
        record['item'].setText(3,(f'{percent} % · ' if percent>=0 else '')+message)
    def finished(self,key,job,outputs,errors):
        record=self.records.get(key)
        if not record:return
        state='Abgebrochen' if job.was_cancelled else 'Teilweise fertig' if errors and outputs else 'Fehler' if errors else 'Fertig'
        record.update(state=state,outputs=list(outputs),errors=list(errors),job=None);record['item'].setText(2,state);record['item'].setText(3,'100 %' if state=='Fertig' else '')
        if self.current==key:self.current=None
        self.notice.setText(state+' · '+record['title']);self.refresh_controls();QTimer.singleShot(0,self.start_next)
    def selected(self):
        item=self.queue.currentItem();return self.records.get(item.data(0,Qt.ItemDataRole.UserRole)) if item else None
    def selected_key(self):
        item=self.queue.currentItem();return item.data(0,Qt.ItemDataRole.UserRole) if item else None
    def refresh_controls(self):
        record=self.selected();running=bool(record and record['job']);waiting=bool(record and record['state']=='Wartet')
        self.cancel.setEnabled(running or waiting);self.retry.setEnabled(bool(record and record['request'] and not running and not waiting));self.remove.setEnabled(bool(record and not running))
        self.open.setEnabled(bool(record and record['outputs']));self.folder.setEnabled(bool(record and record['outputs']))
        count=sum(self.records.get(k,{}).get('state')=='Wartet' for k in self.waiting)
        self.summary.setText(f'{1 if self.current else 0} läuft · {count} warten'+(' · Warteschlange pausiert' if self.paused else ''))
    def set_paused(self,value):
        self.paused=value;self.pause.setText('Warteschlange fortsetzen' if value else 'Warteschlange pausieren');self.refresh_controls()
        if not value:QTimer.singleShot(0,self.start_next)
    def cancel_selected(self):
        record=self.selected()
        if not record:return
        if record['job']:record['job'].control.cancel();record['item'].setText(2,'Abbruch angefordert …')
        elif record['state']=='Wartet':record['state']='Abgebrochen';record['item'].setText(2,'Abgebrochen')
        self.refresh_controls()
    def retry_selected(self):
        record=self.selected()
        if record and record['request'] and record['job'] is None and record['state']!='Wartet':
            request=record['request']
            try:self.enqueue(request['url'],request['mode'],request['folder'],request['height'],request['entries'])
            except Exception as error:self.notice.setText(str(error))
    def remove_selected(self):
        key=self.selected_key();record=self.records.get(key)
        if not record or record['job']:return
        self.records.pop(key);self.waiting=[k for k in self.waiting if k!=key];self.queue.takeTopLevelItem(self.queue.indexOfTopLevelItem(record['item']));self.refresh_controls()
    def move_selected(self,delta):
        key=self.selected_key()
        if key not in self.waiting:return
        index=self.waiting.index(key);other=index+delta
        if not 0<=other<len(self.waiting):return
        self.waiting[index],self.waiting[other]=self.waiting[other],self.waiting[index]
        a=self.records[self.waiting[index]]['item'];b=self.records[self.waiting[other]]['item'];ia=self.queue.indexOfTopLevelItem(a);ib=self.queue.indexOfTopLevelItem(b)
        self.queue.takeTopLevelItem(ia);self.queue.insertTopLevelItem(ib,a);self.queue.setCurrentItem(self.records[key]['item']);self.refresh_controls()
    def show_details(self):
        record=self.selected()
        if not record:return
        box=QMessageBox(self);box.setWindowTitle('Download · Details');box.setText(record['state']+' · '+record['title']);box.setDetailedText('\n'.join(record['outputs']+record['errors']) or 'Noch keine Ergebnisse.');box.exec()
    def open_result(self,folder):
        record=self.selected()
        if not record or not record['outputs']:return
        paths=record['outputs'];choice=paths[0]
        if len(paths)>1:
            choice,ok=QInputDialog.getItem(self,'Ergebnis wählen','Datei',paths,0,False)
            if not ok:return
        path=Path(choice)
        if not path.exists():self.notice.setText('Die Datei ist nicht mehr an ihrem ursprünglichen Ort.');return
        if folder:
            from file_actions import show_in_explorer
            show_in_explorer([path])
        else:QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    def has_pending(self):return bool(self.current or any(self.records.get(k,{}).get('state')=='Wartet' for k in self.waiting))
    def stop_for_exit(self):
        self.paused=True
        if self.composer.inspection:self.composer.inspection.control.cancel()
        for record in self.records.values():
            if record['job']:record['job'].control.cancel()
            elif record['state']=='Wartet':record['state']='Abgebrochen';record['item'].setText(2,'Abgebrochen')
        self.refresh_controls()
