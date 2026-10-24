"""Contextual admin tools in OrbitDrop's existing window style."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,QWidget,QPlainTextEdit,QLineEdit,QComboBox,QCheckBox,QSpinBox,QLabel,QMessageBox
from editor_chrome import EDITOR_STYLE,heading,action_button
from data_editor_ui import DataWork,ChangePreview,export_text
from preview_runtime import preview_pool
from data_formats import read_text,kind_for,CERT_EXT
from admin_tools import ENCODINGS,file_hashes,compare_files,text_transform,table_transform,log_lines,certificate_report,certificate_bytes
from task_runtime import checkpoint

class AdminToolsDialog(QDialog):
    def __init__(self,files,mode='text',output_dir=None,parent=None):
        super().__init__(parent);self.files=list(map(Path,files));self.output_dir=output_dir;self.job=None;self.closed=False
        self.setWindowTitle('OrbitDrop · Daten & Admin-Werkzeuge');self.setStyleSheet(EDITOR_STYLE);self.resize(1050,780)
        layout=QVBoxLayout(self);heading(layout,'Daten & Admin-Werkzeuge',' · '.join(p.name for p in self.files)+' · neue Ausgaben, Originale bleiben erhalten')
        self.tabs=QTabWidget();layout.addWidget(self.tabs);self.pages={}
        if len(files)==1:
            kind=kind_for(self.files[0])
            if kind and kind!='Zertifikat':self.text_page()
            if kind in ('CSV','TSV'):self.table_page()
            if kind in ('LOG','JSONL'):self.log_page()
            if self.files[0].suffix.lower() in CERT_EXT:self.certificate_page()
        self.hash_page()
        if len(files)==2:self.compare_page()
        self.tabs.setCurrentIndex(self.pages.get(mode,self.pages.get('hash',0)))
        self.view=QPlainTextEdit();self.view.setReadOnly(True);self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap);self.view.setPlaceholderText('Aktion wählen. Ergebnisse erscheinen hier.');layout.addWidget(self.view,1)
        self.status=QLabel('Bereit.');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row);self.cancel=action_button('Auftrag abbrechen');self.cancel.setEnabled(False);self.cancel.clicked.connect(self.cancel_job);row.addWidget(self.cancel);row.addStretch();close=action_button('Schließen');close.clicked.connect(self.close);row.addWidget(close)
    def page(self,key,title):
        widget=QWidget();form=QFormLayout(widget);self.pages[key]=self.tabs.addTab(widget,title);return form
    def combo(self,values):
        combo=QComboBox();combo.addItems(values);return combo
    def button(self,form,title,callback):
        button=action_button(title);button.clicked.connect(callback);form.addRow(button);return button
    def run(self,operation,ready=None):
        if self.job:self.status.setText('Ein Auftrag läuft bereits. Erst abschließen oder abbrechen.');return
        self.status.setText('Wird bearbeitet …');self.tabs.setEnabled(False);self.cancel.setEnabled(True);job=DataWork(operation);self.job=job
        def done(result,error):
            self.job=None
            if self.closed:return
            self.tabs.setEnabled(True);self.cancel.setEnabled(False)
            if error:self.status.setText(error);return
            self.status.setText('Fertig.')
            if ready:ready(result)
            else:self.view.setPlainText(str(result))
        job.signals.done.connect(done);job.signals.progress.connect(lambda percent,message:self.status.setText((str(percent)+' % · ' if percent>=0 else '')+message) if self.job is job and not self.closed else None);preview_pool().start(job)
    def cancel_job(self):
        if self.job:self.job.control.cancel();self.status.setText('Abbruch angefordert …')
    def text_page(self):
        form=self.page('text','Text & Kodierung');self.input_encoding=self.combo(('auto',)+ENCODINGS);form.addRow('Eingangskodierung · auto = UTF-8/BOM',self.input_encoding)
        self.output_encoding=self.combo(ENCODINGS);form.addRow('Ausgabekodierung',self.output_encoding);self.newlines=self.combo(['Beibehalten','Linux · LF','Windows · CRLF']);form.addRow('Zeilenumbrüche',self.newlines)
        self.find=QLineEdit();self.replace=QLineEdit();form.addRow('Suchen · wörtlich, keine regulären Ausdrücke',self.find);form.addRow('Ersetzen durch',self.replace)
        self.number=QCheckBox('Zeilen nummerieren');self.deduplicate=QCheckBox('Doppelte Zeilen entfernen');self.sort=QCheckBox('Zeilen alphabetisch sortieren')
        for field in (self.number,self.deduplicate,self.sort):form.addRow(field)
        self.button(form,'Vorschau / als neue Datei speichern',self.preview_text)
    def preview_text(self):
        source=self.files[0];encoding=self.input_encoding.currentText();out_encoding=self.output_encoding.currentText();newline=self.newlines.currentIndex();find=self.find.text();replace=self.replace.text();number=self.number.isChecked();dedup=self.deduplicate.isChecked();sort=self.sort.isChecked()
        def work():
            before,_=read_text(source,encoding);after=text_transform(before,find,replace,dedup,sort,number)
            if newline:after=after.replace('\r\n','\n').replace('\r','\n');after=after.replace('\n','\r\n') if newline==2 else after
            after.encode(out_encoding,errors='strict');return before,after
        def ready(result):
            before,after=result
            if ChangePreview(before,after,'Textänderung prüfen',self,'Neue Datei speichern').exec():self.run(lambda:export_text(source,after,source.suffix or '.txt',self.output_dir,out_encoding),lambda p:self.status.setText('Gespeichert: '+p))
        self.run(work,ready)
    def table_page(self):
        form=self.page('table','Tabelle');self.table_encoding=self.combo(('auto',)+ENCODINGS);form.addRow('Eingangskodierung',self.table_encoding)
        self.input_separator=self.combo(['Automatisch',',',';','Tab','|']);form.addRow('Eingangstrennzeichen',self.input_separator)
        self.output_separator=self.combo([',',';','Tab','|']);form.addRow('Ausgangstrennzeichen',self.output_separator)
        self.columns=QLineEdit();self.columns.setPlaceholderText('Leer = alle, sonst Name,Ort,…');form.addRow('Spalten auswählen',self.columns)
        self.sort_column=QLineEdit();form.addRow('Sortierspalte · Textsortierung, leer = unverändert',self.sort_column)
        self.table_dedup=QCheckBox('Doppelte Ergebniszeilen entfernen');form.addRow(self.table_dedup)
        self.table_target=self.combo(['CSV','TSV','JSON']);form.addRow('Zielformat',self.table_target);self.table_output_encoding=self.combo(ENCODINGS);form.addRow('Ausgabekodierung',self.table_output_encoding)
        note=QLabel('Erste Zeile = eindeutige Spaltennamen. Tabellenwerte bleiben Text. Spaltenauswahl/-sortierung verändert Daten; Vorschau prüfen. CSV-Inhalte werden nicht als Formeln ausgeführt.');note.setWordWrap(True);form.addRow(note)
        self.button(form,'Tabellenvorschau / exportieren',self.preview_table)
    def preview_table(self):
        source=self.files[0];kind=kind_for(source);encoding=self.table_encoding.currentText();input_delimiter=self.input_separator.currentText();input_delimiter=None if input_delimiter=='Automatisch' else '\t' if input_delimiter=='Tab' else input_delimiter
        delimiter=self.output_separator.currentText();delimiter='\t' if delimiter=='Tab' else delimiter;columns=self.columns.text();sort=self.sort_column.text();dedup=self.table_dedup.isChecked();target=self.table_target.currentText();output_encoding=self.table_output_encoding.currentText()
        def work():
            before,_=read_text(source,encoding);after=table_transform(before,kind,columns,sort,dedup,input_delimiter,delimiter,target);after.encode(output_encoding);return before,after
        def ready(result):
            before,after=result
            if ChangePreview(before,after,'Tabelle nach '+target,self,'Neue Datei speichern').exec():self.run(lambda:export_text(source,after,'.'+target.lower(),self.output_dir,output_encoding),lambda p:self.status.setText('Gespeichert: '+p))
        self.run(work,ready)
    def log_page(self):
        form=self.page('log','Logs & JSONL');self.log_encoding=self.combo(ENCODINGS);form.addRow('Zeichenkodierung',self.log_encoding);self.log_find=QLineEdit();form.addRow('Enthält · Groß-/Kleinschreibung ignorieren',self.log_find)
        self.log_start=QLineEdit();self.log_end=QLineEdit()
        for label,field in [('Ab ISO-Zeit · optional',self.log_start),('Bis ISO-Zeit · optional',self.log_end)]:field.setPlaceholderText('2026-10-24T08:00:00Z');form.addRow(label,field)
        self.tail=QSpinBox();self.tail.setRange(0,10000);self.tail.setValue(500);self.tail.setSpecialValueText('Gesamte Datei filtern · max. 512 MiB');form.addRow('Letzte Zeilen · maximal aus letzten 4 MiB',self.tail)
        note=QLabel('Zeitfilter erkennen ISO-Zeitstempel pro Zeile; Zeilen ohne Zeitstempel entfallen. Zeiten ohne Zeitzone gelten als UTC. Vorschau: höchstens 5000 Treffer / 2 MiB. Export verwendet dieselben Filter, aber alle Treffer (max. 100 MiB).');note.setWordWrap(True);form.addRow(note)
        self.button(form,'Filtern / anzeigen',self.preview_log);self.button(form,'Gefilterte Zeilen als neue Datei exportieren',self.export_log)
    def log_options(self):return dict(needle=self.log_find.text(),start=self.log_start.text(),end=self.log_end.text(),tail=self.tail.value(),encoding=self.log_encoding.currentText())
    def preview_log(self):
        options=self.log_options();source=self.files[0]
        def work():
            pieces=[];size=0
            for line in log_lines(source,**options):
                size+=len(line)
                if size>2*1024*1024:pieces.append('\n… Vorschau auf 2 MiB begrenzt.');break
                pieces.append(line)
            return ''.join(pieces) or 'Keine passenden Zeilen.'
        self.run(work)
    def export_log(self):
        options=self.log_options();source=self.files[0]
        def work():
            from converter import reserve
            path=reserve(source.with_name(source.stem+'_gefiltert.log'),'.log',self.output_dir)
            try:
                size=0
                with path.open('w',encoding='utf-8',newline='') as f:
                    for line in log_lines(source,**options,preview_limit=0):
                        size+=len(line.encode('utf-8'))
                        if size>100*1024*1024:raise ValueError('Export größer als 100 MiB. Filter enger einstellen.')
                        f.write(line)
                return str(path)
            except Exception:path.unlink(missing_ok=True);raise
        self.run(work,lambda p:self.status.setText('Gespeichert: '+p))
    def certificate_page(self):
        form=self.page('certificate','Zertifikat');self.password=QLineEdit();self.password.setEchoMode(QLineEdit.EchoMode.Password);form.addRow('PFX-Passwort · nur im Arbeitsspeicher',self.password)
        note=QLabel('X.509-Details, Gültigkeitszeit und Fingerabdruck. Keine Vertrauens-/Sperrlistenprüfung. Export enthält ausschließlich öffentliche Zertifikate, niemals private Schlüssel.');note.setWordWrap(True);form.addRow(note)
        self.button(form,'Zertifikat anzeigen',self.show_certificate);self.cert_target=self.combo(['PEM','DER']);form.addRow('Exportformat',self.cert_target);self.button(form,'Öffentliches Zertifikat exportieren',self.export_certificate)
    def show_certificate(self):
        source=self.files[0];password=self.password.text();self.run(lambda:certificate_report(source,password))
    def export_certificate(self):
        source=self.files[0];password=self.password.text();target=self.cert_target.currentText()
        def work():
            from converter import reserve
            data=certificate_bytes(source,target,password);path=reserve(source,'.'+target.lower(),self.output_dir)
            try:path.write_bytes(data);return str(path)
            except Exception:path.unlink(missing_ok=True);raise
        self.run(work,lambda p:self.status.setText('Öffentliches Zertifikat gespeichert: '+p))
    def hash_page(self):
        form=self.page('hash','SHA-256');self.expected=QLineEdit();self.expected.setPlaceholderText('Optional: erwartete SHA-256-Prüfsumme');form.addRow('Vergleichswert',self.expected)
        self.button(form,'Prüfsummen berechnen / vergleichen',self.hash_files)
    def hash_files(self):
        expected=self.expected.text();self.run(lambda:file_hashes(self.files,expected))
    def compare_page(self):
        form=self.page('compare','Dateivergleich');label=QLabel('Textvergleich mit −/+ Markierungen; bei Binärdateien Größen, SHA-256 und bytegenauer Gleichheitsvergleich. Maximal 8 MiB pro Textdatei und 50000 Zeilen insgesamt.');label.setWordWrap(True);form.addRow(label);self.button(form,'Beide Dateien vergleichen',lambda:self.run(lambda:compare_files(self.files)))
    def closeEvent(self,event):
        if self.job:
            QMessageBox.information(self,'Auftrag läuft','Bitte den Auftrag abschließen oder abbrechen und danach schließen.');event.ignore();return
        self.closed=True
        if hasattr(self,'password'):self.password.clear()
        super().closeEvent(event)
    def reject(self):self.close()
