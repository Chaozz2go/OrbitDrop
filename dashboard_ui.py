"""Persistent, modeless entry point; setup never changes the radial menu."""
import html
from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QStackedWidget,QScrollArea,QFrame,QCheckBox,QProgressBar,QPlainTextEdit,QMessageBox,QDialogButtonBox)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from app_ui import SettingsDialog
from help_ui import HelpDialog
from update_ui import UpdatePanel
from editor_chrome import heading
from ui_theme import STYLE,action_button
from setup_tools import TOOLS


class SettingsPanel(SettingsDialog):
    saved=Signal()
    reset_requested=Signal()
    def __init__(self,prefs,parent=None):
        super().__init__(prefs,parent);self.setWindowFlags(Qt.WindowType.Widget);self.setMinimumWidth(0)
        self.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel).setText('Änderungen verwerfen')
    def accept(self):self.saved.emit()
    def reject(self):self.reset_requested.emit()


class GuidePanel(HelpDialog):
    back_requested=Signal()
    def __init__(self,prefs,parent=None):
        super().__init__(prefs,parent);self.setWindowFlags(Qt.WindowType.Widget);self.setMinimumWidth(0)
    def accept(self):self.back_requested.emit()
    def reject(self):self.back_requested.emit()


class Dashboard(QWidget):
    PAGES=('Willkommen','Einrichtung','Anleitung','Einstellungen','Updates','Verwaltung')
    def __init__(self,controller):
        super().__init__();self.controller=controller;self.prefs=controller.prefs;self.install_key=None
        self.setWindowTitle('OrbitDrop · Dashboard');self.setStyleSheet(STYLE);self.resize(1140,800);self.setMinimumSize(820,540)
        layout=QVBoxLayout(self);heading(layout,'OrbitDrop · Dashboard','Dein Einstieg und alles für Einrichtung, Hilfe und Verwaltung')
        row=QHBoxLayout();layout.addLayout(row,1);self.nav=QListWidget();self.nav.addItems(self.PAGES);self.nav.setFixedWidth(175);row.addWidget(self.nav)
        self.pages=QStackedWidget();row.addWidget(self.pages,1)
        self.home=self.home_page();self.pages.addWidget(self.home)
        self.setup=self.setup_page();self.pages.addWidget(self.setup)
        self._guide=None;self._settings_panel=None;self._updates_panel=None;self._update_result=getattr(controller,'last_update',None)
        self.guide_container=QWidget();self.guide_layout=QVBoxLayout(self.guide_container);self.guide_layout.setContentsMargins(0,0,0,0);self.pages.addWidget(self.guide_container)
        self.settings_container=QWidget();self.settings_layout=QVBoxLayout(self.settings_container);self.settings_layout.setContentsMargins(0,0,0,0);self.pages.addWidget(self.settings_container)
        self.updates_container=QWidget();self.updates_layout=QVBoxLayout(self.updates_container);self.updates_layout.setContentsMargins(0,0,0,0);self.pages.addWidget(self.updates_container)
        self.pages.addWidget(self.management_page())
        self.nav.currentRowChanged.connect(self.page_changed);self.nav.setCurrentRow(0)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);self.progress.hide();layout.addWidget(self.progress)
        self.status=QLabel('OrbitDrop bleibt aktiv, wenn du das Dashboard schließt.');self.status.setWordWrap(True);layout.addWidget(self.status)
        bottom=QHBoxLayout();layout.addLayout(bottom)
        self.at_start=QCheckBox('Dashboard beim Start öffnen');self.at_start.setChecked(self.prefs.values['show_dashboard']);self.at_start.toggled.connect(self.save_start);bottom.addWidget(self.at_start)
        bottom.addStretch();self.cancel=action_button('Einrichtung abbrechen');self.cancel.clicked.connect(controller.cancel_setup);self.cancel.hide();bottom.addWidget(self.cancel)
        close=action_button('Dashboard schließen');close.clicked.connect(self.close);bottom.addWidget(close)
        self.refresh_bindings();self.update_results(controller.backend_status)
    @property
    def guide(self):
        if self._guide is None:
            self._guide=GuidePanel(self.prefs,self);self._guide.back_requested.connect(lambda:self.open_page(0));self.guide_layout.addWidget(self._guide)
        return self._guide
    @property
    def settings_panel(self):
        if self._settings_panel is None:self.load_settings()
        return self._settings_panel
    @property
    def updates_panel(self):
        if self._updates_panel is None:
            panel=UpdatePanel(self.prefs,self.controller.install_update,self);self._updates_panel=panel
            panel.back_requested.connect(lambda:self.open_page(0));panel.auto.toggled.connect(self.update_auto_changed);self.updates_layout.addWidget(panel)
            if self._update_result is not None:panel.ready(*self._update_result)
        return self._updates_panel
    def receive_update_result(self,info,error):
        self._update_result=(info,error);panel=self._updates_panel
        if panel is not None and panel.job is None and panel.installer is None:
            panel.downloading=False;panel.ready(info,error)
    def update_auto_changed(self,*unused):
        if self._settings_panel is not None:self._settings_panel.updates.setChecked(self.prefs.values['check_updates'])
    def page_changed(self,index):
        if index==2:self.guide
        elif index==3:self.settings_panel
        elif index==4:self.updates_panel
        self.pages.setCurrentIndex(index)
    def scroll_page(self):
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);scroll.setWidget(body);return scroll,layout
    def label(self,layout,text):
        label=QLabel(text);label.setWordWrap(True);label.setTextFormat(Qt.TextFormat.RichText);layout.addWidget(label);return label
    def card(self,layout,title,text):
        frame=QFrame();frame.setObjectName('toolbar');box=QVBoxLayout(frame);self.label(box,'<b>'+title+'</b>');self.label(box,text);layout.addWidget(frame);return box
    def home_page(self):
        page,layout=self.scroll_page()
        self.label(layout,'<h2>Willkommen! In wenigen Schritten startklar.</h2>')
        box=self.card(layout,'1 · Erst die Datei greifen, dann die Taste drücken','Eine Datei oder einen Ordner auf dem Desktop oder im Explorer mit der linken Maustaste greifen und etwas ziehen. <b>Maustaste halten</b> und <b>danach</b> die passende Bereichstaste kurz drücken. Die Datei auf die gewünschte Aktion im Kreis ziehen und dort loslassen. <b>Esc</b> bricht das Menü ab.')
        self.keys=self.label(box,'')
        self.card(layout,'2 · Nur einrichten, was du brauchst','Bilder, ZIP und viele Basisfunktionen funktionieren direkt. Python, die Python-Pakete, FFmpeg und OCR-Sprachdaten sind im Windows-Paket enthalten. Für manche Dokumentformate oder YouTube-Links helfen optionale Zusatzprogramme. Unter „Einrichtung“ siehst du, was bereits bereit ist und wofür etwas fehlt.')
        self.home_status=self.label(layout,'Noch nicht geprüft. Unter Einrichtung kannst du die Prüfung starten.')
        row=QHBoxLayout();layout.addLayout(row)
        start=action_button('Einrichtung öffnen',primary=True);start.clicked.connect(lambda:self.open_page(1));row.addWidget(start)
        help_button=action_button('Anleitung lesen');help_button.clicked.connect(lambda:self.open_page(2));row.addWidget(help_button)
        settings=action_button('Tasten & Menüs anpassen');settings.clicked.connect(lambda:self.open_page(3));row.addWidget(settings)
        self.card(layout,'3 · Danach direkt mit deinen Dateien arbeiten','Das Dashboard bleibt offen, bis du es selbst schließt. Du kannst gleichzeitig den Aktionskreis benutzen. Über Rechtsklick auf das OrbitDrop-Symbol neben der Uhr → <b>Dashboard</b> kommst du jederzeit zurück. Eine Prüfung oder Einrichtung schließt dieses Fenster nicht.')
        layout.addStretch();return page
    def setup_page(self):
        page,layout=self.scroll_page();self.label(layout,'<h2>Was brauche ich für welche Funktion?</h2>')
        self.label(layout,'Du musst <b>nicht alle Zusatzprogramme</b> installieren. Die Prüfung lädt nichts herunter und öffnet kein Terminal. „Einrichten“ lädt bzw. installiert erst nach deinem Klick. Für Windows-Installationen werden die Paket- und Quellenbedingungen des Windows-Paketmanagers akzeptiert; Windows kann nach Administratorrechten fragen. „Downloadseite“ öffnet nur die offizielle Webseite.')
        self.check=action_button('Alles erneut prüfen',primary=True);self.check.clicked.connect(lambda:self.controller.check_backends(False));layout.addWidget(self.check)
        self.tool_rows={}
        for key,tool in TOOLS.items():
            box=self.card(layout,tool['title']+(' · optional' if tool['optional'] else ''),tool['purpose'])
            state=self.label(box,'Noch nicht geprüft');row=QHBoxLayout();box.addLayout(row)
            install=action_button('Einrichten');install.clicked.connect(lambda checked=False,k=key:self.controller.setup_tool(k));row.addWidget(install)
            download=action_button('Downloadseite');download.clicked.connect(lambda checked=False,k=key:QDesktopServices.openUrl(QUrl(TOOLS[k]['url'])));row.addWidget(download)
            detail=QPlainTextEdit();detail.setReadOnly(True);detail.setMaximumHeight(82);detail.hide();box.addWidget(detail)
            details=action_button('Details');details.clicked.connect(lambda checked=False,w=detail:w.setVisible(not w.isVisible()));row.addWidget(details)
            self.tool_rows[key]={'state':state,'install':install,'detail':detail,'ready':False}
        self.label(layout,'<b>Schon installiert, aber nicht gefunden?</b> Nach der Installation „Alles erneut prüfen“ wählen. Bei einer portablen Installation FFmpeg/FFprobe bei Bedarf in den bin-Ordner neben OrbitDrop legen. Weitere Hinweise stehen in der Anleitung. Technische Fehler und gefundene Pfade siehst du jeweils unter Details.')
        layout.addStretch();return page
    def management_page(self):
        page,layout=self.scroll_page();self.label(layout,'<h2>Alles für den Hintergrundbetrieb</h2>')
        for title,text,actions in [
            ('Updates & Verlauf','Updates von GitHub prüfen, Aufträge kontrollieren und Ergebnisse wiederfinden.', [('Updates prüfen',self.controller.updates),('Aufträge & Verlauf',self.controller.show_tasks)]),
            ('Eigene Abläufe','Häufige Bearbeitungen vorbereiten und eigene Schnellaktionen verwalten.', [('Bildabläufe',lambda:self.controller.circle_action([],'BILDABLÄUFE','OrbitDrop')),('Schnellaktionen',lambda:self.controller.circle_action([],'SCHNELLAKTIONEN','OrbitDrop'))]),
            ('Weitere Werkzeuge','Downloader öffnen oder unbekannte Dateitypen für die Fehlersuche ansehen.', [('Audio/Video herunterladen',lambda:self.controller.download_dialog()),('Debugging',lambda:self.controller.circle_action([],'DEBUGGING','OrbitDrop'))])]:
            box=self.card(layout,title,text);row=QHBoxLayout();box.addLayout(row)
            for name,callback in actions:
                button=action_button(name);button.clicked.connect(lambda checked=False,cb=callback:cb());row.addWidget(button)
        box=self.card(layout,'Bedienung & weitere Werkzeuge','Kreis und Dateiablage öffnen oder die Tastenzugänge vorübergehend pausieren. Im Tray findest du Dashboard, Downloader, OrbitDrop pausieren und Beenden.')
        row=QHBoxLayout();box.addLayout(row)
        for name,callback in [('Aktionskreis',lambda:self.controller.wheel.open()),('Dateiablage',lambda:self.controller.shelf.open()),('Werkzeuge',self.controller.tools)]:
            button=action_button(name);button.clicked.connect(lambda checked=False,cb=callback:cb());row.addWidget(button)
        self.pause_keys=QCheckBox('Tastenzugänge pausieren');self.pause_keys.setChecked(getattr(self.controller,'shortcuts_paused',False));self.pause_keys.toggled.connect(self.controller.pause_shortcuts);box.addWidget(self.pause_keys)
        layout.addStretch();return page
    def open_page(self,page=0):
        if isinstance(page,str):page=self.PAGES.index(page)
        self.nav.setCurrentRow(page)
    def load_settings(self):
        old=self._settings_panel
        if old:self.settings_layout.removeWidget(old);old.hide();old.deleteLater()
        self._settings_panel=SettingsPanel(self.prefs,self);self._settings_panel.saved.connect(self.settings_saved)
        self.settings_panel.reset_requested.connect(lambda:QTimer.singleShot(0,self.load_settings));self.settings_layout.addWidget(self.settings_panel)
    def settings_saved(self):
        self.controller.refresh_settings();self.refresh_bindings();self.at_start.blockSignals(True);self.at_start.setChecked(self.prefs.values['show_dashboard']);self.at_start.blockSignals(False)
        if self._updates_panel is not None:
            self._updates_panel.auto.blockSignals(True);self._updates_panel.auto.setChecked(self.prefs.values['check_updates']);self._updates_panel.auto.blockSignals(False)
        self.status.setText('Einstellungen gespeichert. Das Dashboard bleibt geöffnet.')
        if self._guide is None:return
        index=self.guide.topics.currentRow();query=self.guide.query.text()
        from help_ui import handbook
        self.guide.sections=handbook(self.prefs.values,self.prefs.root);self.guide.show_section(index);self.guide.filter(query)
    def refresh_bindings(self):
        v=self.prefs.values
        self.keys.setText('<span style="color:#8ce8c9"><b>'+html.escape(v['convert_key'])+' · Konvertieren</b></span> &nbsp; <span style="color:#ffbe8a"><b>'+html.escape(v['edit_key'])+' · Bearbeiten</b></span> &nbsp; <span style="color:#83baff"><b>'+html.escape(v['files_key'])+' · Tools</b></span>')
    def save_start(self,enabled):
        try:
            self.prefs.update(dict(self.prefs.values,show_dashboard=enabled))
            if self._settings_panel is not None:self._settings_panel.dashboard_start.setChecked(enabled)
        except (OSError,ValueError) as error:
            self.at_start.blockSignals(True);self.at_start.setChecked(self.prefs.values['show_dashboard']);self.at_start.blockSignals(False);self.status.setText('Einstellung konnte nicht gespeichert werden: '+str(error))
    def set_checking(self):
        self.status.setText('Werkzeuge werden im Hintergrund geprüft …');self.set_controls(False);self.progress.setRange(0,0);self.progress.show()
    def set_controls(self,enabled):
        self.check.setEnabled(enabled)
        for row in self.tool_rows.values():row['install'].setEnabled(enabled)
    def update_results(self,results):
        for result in results:
            key=result['id'];row=self.tool_rows[key];tool=TOOLS[key];row['ready']=result['ready'];row['detail'].setPlainText(result['detail'])
            row['state'].setText('<b style="color:'+('#8ce8c9' if result['ready'] else '#ffbe8a')+'">'+('Bereit' if result['ready'] else 'Optional · noch nicht bereit' if tool['optional'] else 'Noch nicht bereit')+'</b>')
            row['install'].setText('Erneut einrichten' if result['ready'] else 'Einrichten')
        if results:
            ready=sum(row['ready'] for row in self.tool_rows.values());self.home_status.setText(f'<b>{ready} von {len(TOOLS)} Werkzeuggruppen bereit.</b> Fehlende optionale Programme brauchst du nur für die genannten Funktionen.')
            self.status.setText('Prüfung abgeschlossen. Details und Einrichtung findest du unter Einrichtung.')
        self.set_controls(self.controller.setup_job is None and self.controller.backend_check is None)
        if self.controller.setup_job is None:self.progress.hide()
    def setup_started(self,key):
        self.install_key=key;self.status.setText(TOOLS[key]['title']+' wird eingerichtet …');self.set_controls(False);self.progress.setRange(0,0);self.progress.show();self.cancel.show()
    def setup_progress(self,percent,message):
        self.status.setText(message)
        if percent<0:self.progress.setRange(0,0)
        else:self.progress.setRange(0,100);self.progress.setValue(percent)
    def setup_finished(self,error):
        self.cancel.hide();self.progress.hide();self.set_controls(True)
        self.status.setText(('Einrichtung abgebrochen. Du kannst sie später erneut starten.' if error.startswith('Einrichtung abgebrochen.') else 'Einrichtung nicht abgeschlossen. Hinweise findest du unter Einrichtung → Details.') if error else 'Einrichtung abgeschlossen. Werkzeuge werden erneut geprüft.')
        if error:
            row=self.tool_rows[self.install_key];row['detail'].setPlainText(error);row['detail'].show();row['state'].setText('Einrichtung nicht abgeschlossen · siehe Details')
