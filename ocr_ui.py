from pathlib import Path
import threading
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QSpinBox,QLabel,QTextEdit,QFileDialog,QMessageBox,QApplication
from editor_chrome import heading,EDITOR_STYLE,action_button
from ocr_data import find_tessdata,install_languages

class OcrSignals(QObject):done=Signal(object,str)
class OcrJob(QRunnable):
    def __init__(self,work):super().__init__();self.work=work;self.signals=OcrSignals()
    def run(self):
        try:self.signals.done.emit(self.work(),'')
        except Exception as error:self.signals.done.emit(None,str(error))

class OcrDialog(QDialog):
    def __init__(self,path,prefs,submit):
        super().__init__();self.path=str(path);self.prefs=prefs;self.submit=submit;self.job=None;self.stopped=threading.Event();self.setWindowTitle('OrbitDrop · Lokale Texterkennung');self.setStyleSheet(EDITOR_STYLE);self.resize(880,750)
        layout=QVBoxLayout(self);heading(layout,'Text erkennen · OCR',Path(path).name+' · Verarbeitung lokal auf diesem Computer')
        form=QFormLayout();layout.addLayout(form);self.language=QComboBox()
        for title,value in [('Deutsch + Englisch','deu+eng'),('Deutsch','deu'),('Englisch','eng')]:self.language.addItem(title,value)
        form.addRow('Sprache',self.language);self.dpi=QSpinBox();self.dpi.setRange(72,400);self.dpi.setValue(200);self.dpi.setSuffix(' dpi');form.addRow('Auflösung für PDF-Seiten',self.dpi)
        row=QHBoxLayout();layout.addLayout(row);self.setup=action_button('Deutsch/Englisch einrichten','download');self.setup.clicked.connect(self.install);row.addWidget(self.setup);self.recognize=action_button('Text erkennen',primary=True);self.recognize.clicked.connect(self.read);row.addWidget(self.recognize)
        self.text=QTextEdit();self.text.setPlaceholderText('Erkannter Text erscheint hier. Du kannst ihn korrigieren, kopieren oder als TXT speichern.');layout.addWidget(self.text,1)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        hint=QLabel('Durchsuchbares Scan-PDF rendert die Seiten neu und ergänzt eine Textschicht. Formulare, Vektoren und interaktive Elemente werden dabei nicht erhalten. Das Original bleibt unverändert. Die Einrichtung lädt nur Sprachdateien herunter, keine Dokumente hoch.');hint.setObjectName('editorSubtitle');hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout();layout.addLayout(row)
        for title,callback in [('Kopieren',self.copy),('TXT speichern',self.save_text)]:button=action_button(title);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch();close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);self.pdf=action_button('Scan-PDF erstellen','save',True);self.pdf.clicked.connect(self.export_pdf);row.addWidget(self.pdf)
        self.language.currentIndexChanged.connect(self.available);self.available()
    def available(self,*args):
        ready=bool(find_tessdata(self.language.currentData(),self.prefs.root));busy=self.job is not None;self.recognize.setEnabled(ready and not busy);self.pdf.setEnabled(ready and not busy);self.setup.setEnabled(not busy);self.language.setEnabled(not busy);self.dpi.setEnabled(not busy)
        self.status.setText('Sprachdaten bereit. Erkennung kann bei Scans einige Zeit dauern.' if ready else 'Sprachdaten fehlen. Deutsch/Englisch einmalig einrichten oder vorhandene Tesseract-Daten verwenden.')
    def run(self,work,setup=False):
        if self.job:return
        self.setup_running=setup;self.job=OcrJob(work);self.available();self.status.setText('Sprachdaten werden geladen und geprüft …' if setup else 'Text wird lokal erkannt …');self.job.signals.done.connect(self.ready);QThreadPool.globalInstance().start(self.job)
    def install(self):self.run(lambda:install_languages(self.prefs.root/'tessdata',self.stopped),True)
    def read(self):
        from local_ocr import recognize_text
        language=self.language.currentData();dpi=self.dpi.value();folder=find_tessdata(language,self.prefs.root)
        if folder:self.run(lambda:recognize_text(self.path,language,dpi,folder,self.stopped))
    def ready(self,result,error):
        self.job=None
        if self.stopped.is_set():return
        self.available()
        if error:self.status.setText(error)
        elif not self.setup_running:self.text.setPlainText(result);self.status.setText('Text erkannt. Bitte auf Erkennungsfehler prüfen.' if result else 'Kein Text erkannt. Sprache/Auflösung prüfen.')
    def copy(self):QApplication.clipboard().setText(self.text.toPlainText())
    def save_text(self):
        if not self.text.toPlainText():return
        filename,_=QFileDialog.getSaveFileName(self,'Erkannten Text speichern',str(Path(self.path).with_suffix('.txt')),'Text (*.txt)',options=QFileDialog.Option.DontConfirmOverwrite)
        if not filename:return
        try:
            with Path(filename).open('x',encoding='utf-8') as handle:handle.write(self.text.toPlainText())
        except Exception as error:QMessageBox.warning(self,'Text speichern',str(error))
    def export_pdf(self):
        folder=find_tessdata(self.language.currentData(),self.prefs.root)
        if folder and not self.job:self.submit('OCR PDF',[self.path],{'language':self.language.currentData(),'dpi':self.dpi.value(),'tessdata':str(folder)});self.accept()
    def done(self,result):self.stopped.set();super().done(result)
