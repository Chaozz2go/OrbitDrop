from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QCheckBox,QComboBox,QDoubleSpinBox,QLabel,QMessageBox
from editor_chrome import heading,EDITOR_STYLE,action_button
from slider_field import SliderField
from audio_tools import audio_settings

class AudioToolsDialog(QDialog):
    def __init__(self,files,submit):
        super().__init__();self.files=list(files);self.submit=submit;self.setWindowTitle('OrbitDrop · Audio verbessern');self.setStyleSheet(EDITOR_STYLE);self.resize(680,650)
        layout=QVBoxLayout(self);heading(layout,'Audio verbessern',f'{len(files)} Datei(en) · neue Ausgabe · Originale bleiben erhalten')
        form=QFormLayout();layout.addLayout(form);self.normalize=QCheckBox('Lautstärke mit zwei Durchläufen angleichen');self.normalize.setChecked(True);form.addRow(self.normalize);self.lufs=QComboBox();self.lufs.addItem('−16 LUFS · Sprache / allgemeine Nutzung',-16);self.lufs.addItem('−23 LUFS · zurückhaltender',-23);form.addRow('Lautheitsziel',self.lufs)
        self.trim=QCheckBox('Stille nur am Anfang und Ende entfernen');form.addRow(self.trim)
        self.threshold=QDoubleSpinBox();self.threshold.setRange(-80,-20);self.threshold.setValue(-45);self.threshold.setSuffix(' dB');self.threshold_field=SliderField(self.threshold,1);form.addRow('Schwelle für Stille',self.threshold_field)
        self.padding=QDoubleSpinBox();self.padding.setRange(0,2);self.padding.setSingleStep(.05);self.padding.setValue(.1);self.padding.setSuffix(' s');form.addRow('Rand an erkannter Stille behalten',self.padding)
        self.fade_in=QDoubleSpinBox();self.fade_out=QDoubleSpinBox()
        for title,widget in [('Einblenden',self.fade_in),('Ausblenden',self.fade_out)]:widget.setRange(0,30);widget.setSingleStep(.1);widget.setSuffix(' s');form.addRow(title,widget)
        self.format=QComboBox();self.format.addItems(['FLAC','WAV','MP3']);form.addRow('Ausgabeformat',self.format)
        hint=QLabel('Interne Sprechpausen bleiben erhalten. Stille-Erkennung kann sehr leise Anfänge/Enden erfassen; bei Bedarf eine niedrigere dB-Schwelle wählen. Ausgabe mit 48 kHz; MP3 mit 192 kbit/s. Das Lautheitsziel ist kein Lautstärkeregler für die Wiedergabe.');hint.setObjectName('editorSubtitle');hint.setWordWrap(True);layout.addWidget(hint);layout.addStretch()
        row=QHBoxLayout();layout.addLayout(row);close=action_button('Schließen');close.clicked.connect(self.reject);row.addWidget(close);row.addStretch();start=action_button('Neue Audiodateien erstellen','save',True);start.clicked.connect(self.save);row.addWidget(start)
        self.trim.toggled.connect(self.fields);self.normalize.toggled.connect(self.fields);self.fields()
    def fields(self,*args):self.threshold_field.setEnabled(self.trim.isChecked());self.padding.setEnabled(self.trim.isChecked());self.lufs.setEnabled(self.normalize.isChecked())
    def save(self):
        try:p=audio_settings({'normalize':self.normalize.isChecked(),'lufs':self.lufs.currentData(),'trim':self.trim.isChecked(),'threshold':self.threshold.value(),'padding':self.padding.value(),'fade_in':self.fade_in.value(),'fade_out':self.fade_out.value(),'format':self.format.currentText()});self.submit('Audio verbessern',self.files,p);self.accept()
        except Exception as error:QMessageBox.warning(self,'Audio verbessern',str(error))
