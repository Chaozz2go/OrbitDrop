from pathlib import Path
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool,QStandardPaths,Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QComboBox,QFileDialog,QMessageBox
from ui_theme import STYLE
from editor_chrome import heading
from link_selection import media_link
from downloader import inspect_link

class InspectSignals(QObject):done=Signal(object,str)
class LinkInspect(QRunnable):
    def __init__(self,url):super().__init__();self.url=url;self.signals=InspectSignals()
    def run(self):
        try:self.signals.done.emit(inspect_link(self.url),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class DownloadDialog(QDialog):
    def __init__(self,url,mode,folder,submit,parent=None):
        super().__init__(parent);self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True);self.submit=submit;self.inspection=None;self.inspected_url=None;self.info=None;self.setWindowTitle('OrbitDrop · Link herunterladen');self.resize(650,380);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);heading(layout,'Link herunterladen','Audio oder Video lokal speichern')
        self.url=QLineEdit(url or '');self.url.setPlaceholderText('https://…');layout.addWidget(self.url)
        self.inspect_button=QPushButton('Link prüfen');self.inspect_button.clicked.connect(self.inspect);layout.addWidget(self.inspect_button)
        self.status=QLabel('Link prüfen, dann Audio oder Video wählen.');self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row);self.mode=QComboBox();self.mode.addItem('Audio · MP3','audio');self.mode.addItem('Video · Originalqualität','video');self.mode.setCurrentIndex(1 if mode=='video' else 0);row.addWidget(self.mode)
        self.quality=QComboBox();self.quality.addItem('Beste verfügbare Qualität',0);row.addWidget(self.quality)
        self.folder=QLineEdit(folder or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation));layout.addWidget(self.folder)
        choose=QPushButton('Zielordner wählen');choose.clicked.connect(self.choose_folder);layout.addWidget(choose)
        self.notice=QLabel('Videos behalten das verfügbare Format; getrennte Bild-/Tonspuren werden als MKV gespeichert. Anschließend kannst du die Datei über Strg bearbeiten.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.start=QPushButton('Herunterladen');self.start.setObjectName('primaryAction');self.start.setEnabled(False);self.start.clicked.connect(self.download);layout.addWidget(self.start)
        self.url.textChanged.connect(self.invalidate);self.mode.currentIndexChanged.connect(self.update_enabled)
        if media_link(url):self.inspect()
    def invalidate(self):self.inspected_url=None;self.start.setEnabled(False)
    def inspect(self):
        url=media_link(self.url.text())
        if not url:QMessageBox.information(self,'Link','Bitte einen vollständigen http(s)-Link eingeben.');return
        if self.inspection:return
        self.start.setEnabled(False);self.inspect_button.setEnabled(False);self.status.setText('Titel und verfügbare Qualitäten werden geprüft …')
        job=LinkInspect(url);self.inspection=job;job.signals.done.connect(lambda info,error:self.inspected(url,info,error));QThreadPool.globalInstance().start(job)
    def inspected(self,url,info,error):
        self.inspection=None;self.inspect_button.setEnabled(True)
        if url!=media_link(self.url.text()):self.status.setText('Link geändert. Bitte erneut prüfen.');return
        self.info=info;self.inspected_url=url if info else None
        if error:self.status.setText(error);return
        self.status.setText(info['title']);self.quality.clear();self.quality.addItem('Beste verfügbare Qualität',0)
        for height in info['heights']:self.quality.addItem(f'Bis {height}p',height)
        self.update_enabled()
    def update_enabled(self):
        video=self.mode.currentData()=='video';self.quality.setEnabled(video)
        self.start.setEnabled(bool(self.inspected_url and self.info and self.info.get('video' if video else 'audio')))
    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Downloadordner',self.folder.text())
        if folder:self.folder.setText(folder)
    def download(self):
        if self.inspected_url!=media_link(self.url.text()):return
        if not Path(self.folder.text()).is_dir():QMessageBox.information(self,'Download','Bitte einen existierenden Zielordner wählen.');return
        try:self.submit(self.inspected_url,self.mode.currentData(),self.folder.text(),self.quality.currentData())
        except Exception as error:QMessageBox.warning(self,'Download',str(error));return
        self.accept()
