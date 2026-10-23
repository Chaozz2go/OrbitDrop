"""Local first steps with a live demonstration; no downloads on opening."""
import html
from PySide6.QtCore import Qt,QTimer,QRectF,QPointF,Signal
from PySide6.QtGui import QPainter,QColor,QPen,QPainterPath
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QScrollArea,QWidget
from editor_chrome import heading
from ui_theme import STYLE,action_button


class DragDemo(QWidget):
    def __init__(self,key,parent=None):
        super().__init__(parent);self.key=key;self.frame=0
        self.setMinimumHeight(155)
        self.setAccessibleName('Bedienbeispiel: Datei greifen, ziehen, dann '+key+' drücken, Ziel wählen und loslassen.')
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.advance)
    def advance(self):self.frame=(self.frame+1)%150;self.update()
    def showEvent(self,event):super().showEvent(event);self.timer.start()
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor('#0e1928'))
        w=self.width();f=self.frame;drag=min(1,max(0,(f-20)/40));x=55+(w*.57-55)*drag;y=57
        p.setPen(QColor('#a3b7ce'));p.drawText(QRectF(15,6,w-30,25),Qt.AlignmentFlag.AlignCenter,'1  Greifen & ziehen     →     2  Taste drücken     →     3  Ziel wählen')
        if 65<=f<135:
            cx=w*.68;cy=82
            for i,color in enumerate(('#8ce8c9','#ffbe8a','#aaa3ff')):
                p.setBrush(QColor(color));p.setPen(QPen(QColor('#142131'),4));p.drawPie(QRectF(cx-43,cy-43,86,86),i*120*16,120*16)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#142131'));p.drawEllipse(QPointF(cx,cy),22,22)
        p.setPen(QPen(QColor('#8ce8c9'),2));p.setBrush(QColor('#243a50'));p.drawRoundedRect(QRectF(x-18,y-10,38,47),5,5)
        p.setPen(QColor('#eaf2fc'));p.drawText(QRectF(x-15,y+2,32,30),Qt.AlignmentFlag.AlignCenter,'Datei')
        cursor=QPainterPath(QPointF(x+13,y+15));cursor.lineTo(x+13,y+37);cursor.lineTo(x+19,y+32);cursor.lineTo(x+25,y+43);cursor.lineTo(x+30,y+40);cursor.lineTo(x+24,y+30);cursor.lineTo(x+32,y+30);cursor.closeSubpath();p.fillPath(cursor,QColor('#ffffff'))
        p.setPen(QColor('#8ce8c9' if 65<=f<135 else '#a3b7ce'))
        p.drawText(QRectF(12,119,w-24,30),Qt.AlignmentFlag.AlignCenter,self.key+(' gedrückt · Maustaste weiter halten' if 65<=f<135 else ' erst nach dem Greifen drücken'))
        p.end()


class WelcomeDialog(QDialog):
    check_requested=Signal()
    help_requested=Signal()
    def __init__(self,prefs,parent=None):
        super().__init__(parent);self.prefs=prefs
        self.setWindowTitle('OrbitDrop · Erste Schritte');self.setStyleSheet(STYLE);self.resize(690,740)
        layout=QVBoxLayout(self);layout.setContentsMargins(22,20,22,18)
        heading(layout,'Willkommen bei OrbitDrop','Dateien umwandeln, bearbeiten und organisieren – direkt an deiner Maus')
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();content=QVBoxLayout(body);scroll.setWidget(body);layout.addWidget(scroll)
        def text(value):
            label=QLabel(value);label.setWordWrap(True);label.setTextFormat(Qt.TextFormat.RichText);content.addWidget(label);return label
        v=prefs.values;convert=html.escape(v['convert_key']);edit=html.escape(v['edit_key']);tools=html.escape(v['files_key'])
        text('<b>So öffnest du das Menü</b><br>1. Eine Datei oder einen Ordner auf dem Desktop oder im Explorer mit der linken Maustaste greifen und etwas ziehen.<br>2. Maustaste halten und <b>danach</b> die gewünschte Taste drücken.<br>3. Das Ziel im Kreis mit der Datei ansteuern und dort loslassen. Mit Esc abbrechen.')
        self.demo=DragDemo(v['convert_key']);content.addWidget(self.demo)
        text(f'<span style="color:#8ce8c9"><b>{convert} · Konvertieren</b></span> &nbsp; <span style="color:#ffbe8a"><b>{edit} · Bearbeiten</b></span> &nbsp; <span style="color:#aaa3ff"><b>{tools} · Tools</b></span><br>Die Tasten und sichtbaren Menüpunkte kannst du in den Einstellungen ändern.')
        text('<b>Warum gibt es eine Konverter-Prüfung?</b><br>Einige Dateiformate brauchen spezialisierte Zusatzprogramme. Die Prüfung zeigt, was schon bereit ist und welche Funktionen noch ein Werkzeug benötigen. Du musst nicht alles installieren.')
        text('<b>FFmpeg + FFprobe:</b> Erkennen, Umwandeln, Schneiden und Komprimieren von Audio/Video sowie Ton aus Downloads. Beim Windows-Setup normalerweise enthalten; nur bei fehlenden Werkzeugen „Medien einrichten“ wählen.<br><br><b>LibreOffice (optional):</b> zusätzliche Office-Dateien und Präsentationen umwandeln.<br><br><b>Pandoc (optional):</b> zusätzliche Text-, Dokument- und E-Book-Formate umwandeln.<br><br>Die Windows-App enthält Python und die Python-Pakete bereits. Die Prüfung installiert nichts automatisch. Downloads und zusätzliche Installationen startest du selbst.')
        text(f'<b>YouTube-Link kopiert?</b><br>Link kopieren, <b>{convert}</b> halten und einmal links klicken, ohne zu ziehen. Dann „Audio“ oder „Video“ wählen. Das klappt auf dem Desktop, im Explorer und in unterstützten Browsern außerhalb des Vollbilds. Eine gezogene Datei hat Vorrang; Spiele lösen die Funktion nicht aus.')
        text('<b>Wo finde ich den Rest?</b><br>Rechtsklick auf das OrbitDrop-Symbol neben der Windows-Uhr: Einstellungen, Anleitung, Konverter-Prüfung, Updates und Verlauf. „Erste Schritte“ öffnet diese Hilfe erneut.')
        self.never=QCheckBox('Nicht mehr beim Start anzeigen');self.never.setChecked(not v.get('show_intro',True));layout.addWidget(self.never)
        self.notice=QLabel('');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        row=QHBoxLayout();layout.addLayout(row)
        check=action_button('Konverter prüfen / einrichten',primary=True);check.clicked.connect(self.open_check);row.addWidget(check)
        help_button=action_button('Anleitung');help_button.clicked.connect(self.open_help);row.addWidget(help_button)
        done=action_button('Los geht’s');done.clicked.connect(self.accept);row.addWidget(done)
    def done(self,result):
        try:self.prefs.update(dict(self.prefs.values,show_intro=not self.never.isChecked()))
        except (OSError,ValueError) as error:
            self.notice.setText('Einstellung konnte nicht gespeichert werden: '+str(error));return
        super().done(result)
    def open_check(self):
        self.accept()
        if not self.isVisible():self.check_requested.emit()
    def open_help(self):
        self.accept()
        if not self.isVisible():self.help_requested.emit()
