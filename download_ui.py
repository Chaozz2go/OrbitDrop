from pathlib import Path
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool,QStandardPaths,Qt,QSignalBlocker
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QComboBox,QFileDialog,QMessageBox,QTreeWidget,QTreeWidgetItem,QWidget
from ui_theme import STYLE
from editor_chrome import heading
from link_selection import media_link
from downloader import inspect_link
from task_runtime import TaskControl

class InspectSignals(QObject):done=Signal(object,str)
class LinkInspect(QRunnable):
    def __init__(self,url):super().__init__();self.url=url;self.signals=InspectSignals();self.control=TaskControl()
    def run(self):
        try:
            with self.control.activate():info=inspect_link(self.url)
            self.signals.done.emit(info,'')
        except Exception as error:self.signals.done.emit(None,str(error))

class DownloadDialog(QDialog):
    def __init__(self,url,mode,folder,submit,parent=None):
        super().__init__(parent);self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True);self.submit=submit;self.inspection=None;self.inspected_url=None;self.info=None;self.closed=False;self.setWindowTitle('OrbitDrop · Link herunterladen');self.resize(650,380);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);heading(layout,'Link herunterladen','Audio oder Video lokal speichern')
        self.url=QLineEdit(url or '');self.url.setPlaceholderText('https://…');layout.addWidget(self.url)
        self.inspect_button=QPushButton('Link prüfen');self.inspect_button.clicked.connect(self.inspect);layout.addWidget(self.inspect_button)
        self.status=QLabel('Link prüfen, dann Audio oder Video wählen.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.playlist_panel=QWidget();playlist_layout=QVBoxLayout(self.playlist_panel);playlist_layout.setContentsMargins(0,0,0,0);layout.addWidget(self.playlist_panel);self.playlist_panel.hide()
        self.search=QLineEdit();self.search.setPlaceholderText('Titel suchen · filtert nur die Anzeige');self.search.textChanged.connect(self.filter_entries);playlist_layout.addWidget(self.search)
        self.entries=QTreeWidget();self.entries.setHeaderLabels(['Nr.','Titel','Dauer','Status']);self.entries.setRootIsDecorated(False);self.entries.setAlternatingRowColors(True);self.entries.setMinimumHeight(230);self.entries.setColumnWidth(0,55);self.entries.setColumnWidth(1,350);self.entries.setColumnWidth(2,75);self.entries.itemChanged.connect(self.update_enabled);playlist_layout.addWidget(self.entries)
        selection=QHBoxLayout();playlist_layout.addLayout(selection)
        for text,checked in [('Alle auswählen',True),('Keine auswählen',False)]:
            button=QPushButton(text);button.clicked.connect(lambda unused=False,checked=checked:self.select_entries(checked));selection.addWidget(button)
        self.counter=QLabel();selection.addWidget(self.counter);selection.addStretch()
        row=QHBoxLayout();layout.addLayout(row);self.mode=QComboBox();self.mode.addItem('Audio · MP3','audio');self.mode.addItem('Video · Originalqualität','video');self.mode.setCurrentIndex(1 if mode=='video' else 0);row.addWidget(self.mode)
        self.quality=QComboBox();self.quality.addItem('Beste verfügbare Qualität',0);row.addWidget(self.quality)
        self.folder=QLineEdit(folder or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation));layout.addWidget(self.folder)
        choose=QPushButton('Zielordner wählen');choose.clicked.connect(self.choose_folder);layout.addWidget(choose)
        self.notice=QLabel('Videos behalten das verfügbare Format; getrennte Bild-/Tonspuren werden als MKV gespeichert. Anschließend kannst du die Datei über Strg bearbeiten.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.start=QPushButton('Herunterladen');self.start.setObjectName('primaryAction');self.start.setEnabled(False);self.start.clicked.connect(self.download);layout.addWidget(self.start)
        self.url.textChanged.connect(self.invalidate);self.mode.currentIndexChanged.connect(self.update_enabled)
        if media_link(url):self.inspect()
    def invalidate(self):
        self.inspected_url=None;self.info=None;self.playlist_panel.hide();self.start.setEnabled(False)
    def inspect(self):
        url=media_link(self.url.text())
        if not url:QMessageBox.information(self,'Link','Bitte einen vollständigen http(s)-Link eingeben.');return
        if self.inspection:return
        self.start.setEnabled(False);self.inspect_button.setEnabled(False);self.status.setText('Link prüfen · Playlist-Titel werden gegebenenfalls vollständig eingelesen …')
        job=LinkInspect(url);self.inspection=job;job.signals.done.connect(lambda info,error:self.inspected(url,info,error));QThreadPool.globalInstance().start(job)
    def inspected(self,url,info,error):
        self.inspection=None
        if self.closed:return
        self.inspect_button.setEnabled(True)
        if url!=media_link(self.url.text()):self.status.setText('Link geändert. Bitte erneut prüfen.');return
        self.info=info;self.inspected_url=url if info else None
        if error:self.info=None;self.inspected_url=None;self.playlist_panel.hide();self.status.setText(error);return
        self.status.setText(info['title']);self.quality.clear();self.quality.addItem('Beste verfügbare Qualität',0)
        for height in info['heights']:self.quality.addItem(f'Bis {height}p',height)
        self.show_playlist(info)
        self.update_enabled()
    def show_playlist(self,info):
        blocker=QSignalBlocker(self.entries);self.entries.clear();self.search.clear()
        playlist=bool(info.get('playlist'));self.playlist_panel.setVisible(playlist)
        if playlist:
            self.resize(850,750)
            for entry in info.get('entries',[]):
                duration=entry.get('duration');seconds=int(duration) if duration is not None else None
                stamp=(f'{seconds//3600}:{seconds//60%60:02}:{seconds%60:02}' if seconds>=3600 else f'{seconds//60}:{seconds%60:02}') if seconds is not None else '—'
                item=QTreeWidgetItem([str(entry['index']),entry['title'],stamp,entry.get('reason') or 'Beim Download prüfen']);item.setData(0,Qt.ItemDataRole.UserRole,entry)
                if entry.get('available'):
                    item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(0,Qt.CheckState.Checked)
                else:item.setDisabled(True)
                self.entries.addTopLevelItem(item)
            self.status.setText(info['title']+' · Playlist erkannt. Verfügbarkeit und Qualität werden je Titel beim Download geprüft.')
            self.quality.clear()
            for title,height in [('Beste verfügbare Qualität',0),('Bis 2160p',2160),('Bis 1440p',1440),('Bis 1080p',1080),('Bis 720p',720),('Bis 480p',480)]:self.quality.addItem(title,height)
        del blocker
    def selected_entries(self):
        return [item.data(0,Qt.ItemDataRole.UserRole) for index in range(self.entries.topLevelItemCount()) if (item:=self.entries.topLevelItem(index)).checkState(0)==Qt.CheckState.Checked and not item.isDisabled()]
    def select_entries(self,checked):
        blocker=QSignalBlocker(self.entries)
        for index in range(self.entries.topLevelItemCount()):
            item=self.entries.topLevelItem(index)
            if not item.isDisabled():item.setCheckState(0,Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        del blocker;self.update_enabled()
    def filter_entries(self,text):
        for index in range(self.entries.topLevelItemCount()):
            item=self.entries.topLevelItem(index);item.setHidden(text.casefold() not in item.text(1).casefold())
    def update_enabled(self,*args):
        video=self.mode.currentData()=='video';self.quality.setEnabled(video)
        playlist=bool(self.info and self.info.get('playlist'));count=len(self.selected_entries()) if playlist else 0
        self.counter.setText(f'{count} / {self.entries.topLevelItemCount()} ausgewählt')
        self.start.setText(f'{count} Titel herunterladen' if playlist else 'Herunterladen')
        self.start.setEnabled(bool(self.inspected_url and self.info and self.info.get('video' if video else 'audio') and (not playlist or count)))
    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Downloadordner',self.folder.text())
        if folder:self.folder.setText(folder)
    def download(self):
        if self.inspected_url!=media_link(self.url.text()):return
        if not Path(self.folder.text()).is_dir():QMessageBox.information(self,'Download','Bitte einen existierenden Zielordner wählen.');return
        selected=self.selected_entries() if self.info and self.info.get('playlist') else None
        if selected is not None and not selected:return
        try:
            args=(self.inspected_url,self.mode.currentData(),self.folder.text(),self.quality.currentData())
            if selected is None:self.submit(*args)
            else:self.submit(*args,selected)
        except Exception as error:QMessageBox.warning(self,'Download',str(error));return
        self.accept()

    def done(self,result):
        self.closed=True
        if self.inspection:self.inspection.control.cancel()
        super().done(result)
