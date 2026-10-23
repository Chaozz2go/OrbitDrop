"""Explicit, local webcam and microphone checks; never records media."""
import array
import math
import sys
from PySide6.QtCore import QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QMediaDevices,QCamera,QMediaCaptureSession,QAudioSource,QAudioFormat
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QProgressBar
from ui_theme import STYLE


def audio_peak(data, sample_format):
    """Normalized peak from a bounded block of interleaved PCM samples."""
    formats={QAudioFormat.SampleFormat.Int16:('h',32768),QAudioFormat.SampleFormat.Int32:('i',2147483648),QAudioFormat.SampleFormat.Float:('f',1)}
    data=bytes(data[:65536])
    if sample_format==QAudioFormat.SampleFormat.UInt8:
        return max((abs(v-128)/128 for v in data),default=0)
    if sample_format not in formats:return 0
    code,scale=formats[sample_format];values=array.array(code);values.frombytes(data[:len(data)//values.itemsize*values.itemsize])
    if sys.byteorder!='little':values.byteswap()
    return min(1,max((abs(v)/scale for v in values if math.isfinite(v)),default=0))


class DeviceTestDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('Webcam & Mikrofon testen');self.resize(730,650);self.setStyleSheet(STYLE)
        self.camera=None;self.audio=None;self.audio_io=None;self.peak=0
        self.devices=QMediaDevices(self);self.session=QMediaCaptureSession(self)
        layout=QVBoxLayout(self)
        title=QLabel('Webcam & Mikrofon');title.setObjectName('editorTitle');layout.addWidget(title)
        hint=QLabel('Wähle ein Gerät und starte den Test. Keine Aufnahme, keine Speicherung, keine Übertragung.');hint.setWordWrap(True);layout.addWidget(hint)
        self.camera_choice=QComboBox();self.camera_button=QPushButton('Kamera starten');self.camera_button.clicked.connect(self.toggle_camera)
        row=QHBoxLayout();row.addWidget(self.camera_choice,1);row.addWidget(self.camera_button);layout.addLayout(row)
        self.video=QVideoWidget();self.video.setMinimumHeight(260);layout.addWidget(self.video,1)
        self.camera_status=QLabel('Kamera ist ausgeschaltet.');self.camera_status.setWordWrap(True);layout.addWidget(self.camera_status)
        self.microphone_choice=QComboBox();self.microphone_button=QPushButton('Mikrofon starten');self.microphone_button.clicked.connect(self.toggle_microphone)
        row=QHBoxLayout();row.addWidget(self.microphone_choice,1);row.addWidget(self.microphone_button);layout.addLayout(row)
        self.level=QProgressBar();self.level.setRange(0,100);self.level.setFormat('Pegel: %p%');layout.addWidget(self.level)
        self.microphone_status=QLabel('Mikrofon ist ausgeschaltet.');self.microphone_status.setWordWrap(True);layout.addWidget(self.microphone_status)
        row=QHBoxLayout();refresh=QPushButton('Geräte neu suchen');refresh.clicked.connect(self.refresh);row.addWidget(refresh)
        for label,url in [('Kamera-Zugriff','ms-settings:privacy-webcam'),('Mikrofon-Zugriff','ms-settings:privacy-microphone')]:
            button=QPushButton(label);button.setVisible(sys.platform=='win32');button.clicked.connect(lambda checked=False,u=url:QDesktopServices.openUrl(QUrl(u)));row.addWidget(button)
        close=QPushButton('Schließen');close.clicked.connect(self.close);row.addWidget(close);layout.addLayout(row)
        self.meter_timer=QTimer(self);self.meter_timer.setInterval(50);self.meter_timer.timeout.connect(self.update_meter)
        self.devices.videoInputsChanged.connect(self.refresh);self.devices.audioInputsChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.stop_camera();self.stop_microphone()
        self.cameras=QMediaDevices.videoInputs();self.microphones=QMediaDevices.audioInputs()
        for choice,devices,button in [(self.camera_choice,self.cameras,self.camera_button),(self.microphone_choice,self.microphones,self.microphone_button)]:
            choice.clear();choice.addItems([d.description() for d in devices]);button.setEnabled(bool(devices))
        if not self.cameras:self.camera_status.setText('Keine Webcam gefunden. Verbindung und Windows-Zugriff prüfen.')
        if not self.microphones:self.microphone_status.setText('Kein Mikrofon gefunden. Verbindung und Windows-Zugriff prüfen.')

    def toggle_camera(self):
        if self.camera is not None:self.stop_camera();return
        index=self.camera_choice.currentIndex()
        if not 0<=index<len(self.cameras):return
        try:
            self.camera=QCamera(self.cameras[index],self);self.camera.errorOccurred.connect(self.camera_error)
            self.session.setCamera(self.camera);self.session.setVideoOutput(self.video)
            self.video.videoSink().videoFrameChanged.connect(self.frame_ready)
            self.camera_choice.setEnabled(False);self.camera_button.setText('Kamera stoppen');self.camera_status.setText('Kamera wird gestartet …')
            self.camera.start()
        except Exception as error:self.camera_error(None,str(error))

    def frame_ready(self,frame):
        if self.camera is not None and frame.isValid():self.camera_status.setText('Livebild empfangen · Kamera funktioniert.')

    def camera_error(self,error,message):
        self.stop_camera();self.camera_status.setText('Kamera konnte nicht verwendet werden: '+str(message)+' · Zugriff prüfen und andere Kamera-Apps schließen.')

    def stop_camera(self):
        camera=self.camera;self.camera=None
        if camera is not None:
            try:self.video.videoSink().videoFrameChanged.disconnect(self.frame_ready)
            except (RuntimeError,TypeError):pass
            camera.stop();self.session.setCamera(None);self.session.setVideoOutput(None);camera.deleteLater()
        self.camera_choice.setEnabled(True);self.camera_button.setText('Kamera starten');self.camera_status.setText('Kamera ist ausgeschaltet.')

    def toggle_microphone(self):
        if self.audio is not None:self.stop_microphone();return
        index=self.microphone_choice.currentIndex()
        if not 0<=index<len(self.microphones):return
        try:
            device=self.microphones[index];fmt=device.preferredFormat()
            self.audio=QAudioSource(device,fmt,self);self.audio.stateChanged.connect(self.audio_state)
            self.audio_format=fmt.sampleFormat();self.microphone_choice.setEnabled(False);self.microphone_button.setText('Mikrofon stoppen')
            self.microphone_status.setText('Sprich ins Mikrofon – warte auf ein Signal …')
            self.audio_io=self.audio.start()
            if self.audio is None:return
            if self.audio_io is None:raise RuntimeError('Kein Zugriff auf den Audioeingang.')
            self.audio_io.readyRead.connect(self.read_audio);self.meter_timer.start()
        except Exception as error:self.microphone_error(str(error))

    def audio_state(self,state):
        if self.audio is not None and self.audio.error().value!=0:self.microphone_error('Audiofehler '+str(self.audio.error()))

    def read_audio(self):
        if self.audio_io is not None:
            self.peak=max(self.peak,audio_peak(bytes(self.audio_io.readAll()),self.audio_format))
            if self.peak>.01:self.microphone_status.setText('Signal empfangen · Mikrofon funktioniert.')

    def update_meter(self):
        self.level.setValue(round(self.peak*100));self.peak*=.75

    def microphone_error(self,message):
        self.stop_microphone();self.microphone_status.setText('Mikrofon konnte nicht verwendet werden: '+message+' · Windows-Zugriff und Eingabegerät prüfen.')

    def stop_microphone(self):
        self.meter_timer.stop()
        if self.audio_io is not None:
            try:self.audio_io.readyRead.disconnect(self.read_audio)
            except (RuntimeError,TypeError):pass
        self.audio_io=None;audio=self.audio;self.audio=None
        if audio is not None:audio.stop();audio.deleteLater()
        self.peak=0;self.level.setValue(0);self.microphone_choice.setEnabled(True);self.microphone_button.setText('Mikrofon starten');self.microphone_status.setText('Mikrofon ist ausgeschaltet.')

    def done(self,result):
        self.stop_camera();self.stop_microphone();super().done(result)

    def closeEvent(self,event):
        self.stop_camera();self.stop_microphone();super().closeEvent(event)
