import threading
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QCheckBox,QLabel,QTextEdit,QProgressBar
from editor_chrome import heading,EDITOR_STYLE,action_button
from updater import VERSION,RELEASE_PAGE,latest_release,download_release

class UpdateSignals(QObject):done=Signal(object,str);progress=Signal(int)
class UpdateJob(QRunnable):
    def __init__(self,work):super().__init__();self.work=work;self.signals=UpdateSignals()
    def run(self):
        try:self.signals.done.emit(self.work(self.signals.progress.emit),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class UpdateDialog(QDialog):
    def __init__(self,prefs,install):
        super().__init__();self.prefs=prefs;self.install=install;self.info=None;self.installer=None;self.job=None;self.stopped=threading.Event();self.setWindowTitle('OrbitDrop · Updates');self.setStyleSheet(EDITOR_STYLE);self.resize(900,650)
        layout=QVBoxLayout(self);heading(layout,'Updates','Installierte Version: '+VERSION+' · Windows x64')
        self.auto=QCheckBox('Bei jedem Programmstart nach Updates suchen');self.auto.setChecked(prefs.values.get('check_updates',True));self.auto.toggled.connect(self.save_auto);layout.addWidget(self.auto)
        self.status=QLabel('Updateprüfung …');self.status.setWordWrap(True);layout.addWidget(self.status);self.notes=QTextEdit();self.notes.setReadOnly(True);layout.addWidget(self.notes,1)
        from changelog import notes_for
        self.notes.setMarkdown(notes_for(VERSION));self.notes.setAccessibleName('Änderungen der installierten oder angebotenen Version')
        self.progress=QProgressBar();self.progress.hide();layout.addWidget(self.progress)
        hint=QLabel('Updates werden von GitHub geladen und anhand SHA-256 geprüft. Installieren startet das normale Windows-Setup und beendet OrbitDrop, sobald keine Aufträge mehr laufen. Quelle: Chaozz2go/OrbitDrop. Nur veröffentlichte stabile Releases werden angeboten; Download und Installation startest du selbst.');hint.setWordWrap(True);hint.setObjectName('editorSubtitle');layout.addWidget(hint)
        row=QHBoxLayout();layout.addLayout(row);self.check_button=action_button('Erneut prüfen');self.check_button.clicked.connect(self.check);row.addWidget(self.check_button);browser=action_button('Releases im Browser');browser.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(RELEASE_PAGE)));row.addWidget(browser);history=action_button('Änderungsverlauf');history.clicked.connect(self.show_history);row.addWidget(history);row.addStretch();close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);self.download_button=action_button('Herunterladen','download',True);self.download_button.clicked.connect(self.download_or_install);self.download_button.setEnabled(False);row.addWidget(self.download_button);QTimer.singleShot(0,self.check)
    def show_history(self):
        from changelog_ui import ChangelogDialog
        ChangelogDialog(self).exec()
    def save_auto(self,value):
        try:self.prefs.update(dict(self.prefs.values,check_updates=value))
        except Exception as error:self.status.setText(str(error))
    def start(self,work,download=False):
        if self.job:return
        self.downloading=download;self.job=UpdateJob(work);self.check_button.setEnabled(False);self.download_button.setEnabled(False);self.progress.setVisible(download);self.progress.setValue(0);self.job.signals.progress.connect(self.progress.setValue);self.job.signals.done.connect(self.ready);QThreadPool.globalInstance().start(self.job)
    def check(self):
        if self.job:return
        self.status.setText('Nach freigegebenen Updates suchen …');self.installer=None;self.info=None;self.start(lambda progress:latest_release())
    def ready(self,result,error):
        self.job=None
        if self.stopped.is_set():return
        self.check_button.setEnabled(True)
        if error:self.status.setText(error);self.progress.hide();return
        if self.downloading:self.installer=result;self.status.setText('Setup vollständig geladen und Prüfsumme bestätigt.');self.progress.setValue(100);self.download_button.setText('Installieren');self.download_button.setEnabled(True)
        else:
            self.info=result;self.notes.setPlainText(result['notes']);self.status.setText('Neue Version '+result['version']+' verfügbar.' if result['newer'] else 'Kein neueres freigegebenes Update.');self.download_button.setText('Herunterladen');self.download_button.setEnabled(result['newer'])
    def download_or_install(self):
        if self.installer:
            try:self.install(self.installer)
            except Exception as error:self.status.setText(str(error))
        elif self.info:
            self.status.setText('Setup herunterladen und prüfen …');self.start(lambda progress:download_release(self.info,self.prefs.root,progress,self.stopped),True)
    def done(self,result):self.stopped.set();super().done(result)
