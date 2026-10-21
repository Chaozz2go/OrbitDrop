import ctypes
import math
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRunnable, QThreadPool, QRectF, QPointF, QStandardPaths
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QCursor, QIcon, QPixmap, QAction
from PySide6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu, QMessageBox, QFileDialog
from converter import convert
from filetypes import common_actions,inspect_file,FileInfo
from file_actions import FILE_ACTIONS, available_file_actions, DESCRIPTIONS, file_mime, copy_paths_text, validate_paths, plan_moves, execute_moves, open_terminals, show_in_explorer
from shelf import Shelf
from archives import create_zip, extract_archive
from task_runtime import TaskControl, Cancelled, checkpoint
from preferences import Preferences,KEY_CODES
from app_ui import SettingsDialog,TasksWindow
from single_instance import SingleInstance
from tools import tool_outputs
from tools_ui import ToolsDialog
from circle_menu import home_actions,edit_actions,MENU_LABELS,action_color
from link_selection import media_link

class Signals(QObject):
    done = Signal(object, object)
    progress = Signal(int,str)

class ManagedJob(QRunnable):
    def __init__(self):
        super().__init__();self.signals=Signals();self.control=TaskControl(self.signals.progress.emit)
        self.outputs=[];self.was_cancelled=False
    def run(self):
        errors=[]
        try:
            with self.control.activate():
                self.control.check();self.work()
        except Cancelled:pass
        except Exception as error:errors.append(str(error))
        self.was_cancelled=self.control.cancelled.is_set()
        errors+=getattr(self,'errors',[])
        self.signals.done.emit(self.outputs,errors)

class Conversion(ManagedJob):
    def __init__(self,files,target,options=None):
        super().__init__();self.files,self.target,self.options=files,target,dict(options or {});self.errors=[]
    def work(self):
        count=len(self.files)
        for index,file in enumerate(self.files):
            self.control.base=index/max(1,count)*100;self.control.span=100/max(1,count)
            checkpoint(0,f'{index+1}/{count}: {Path(file).name}')
            try:self.outputs.append(str(convert(file,self.target,self.options)))
            except Cancelled:raise
            except Exception as error:self.errors.append(f'{Path(file).name}: {error}')

class Inspection(QRunnable):
    def __init__(self, files):
        super().__init__()
        self.files = files
        self.reports=[]
        self.signals = Signals()

    def run(self):
        try:
            infos=[]
            for file in self.files:
                try:info=inspect_file(file)
                except Exception as error:info=FileInfo('Nicht lesbar',(),str(error))
                infos.append(info)
                if not info.actions and Path(file).is_file():
                    self.reports.append((str(file),info))
            actions, kind, message = common_actions(self.files,infos)
            self.signals.done.emit(actions, (kind, message))
        except Exception as error:
            self.signals.done.emit((), ('Nicht lesbar', str(error)))

class DiagnosticJob(QRunnable):
    def __init__(self,items):super().__init__();self.items=items;self.signals=Signals()
    def run(self):
        from diagnostics import recognition_report
        reports=[]
        for path,info in self.items:
            try:reports.append(recognition_report(path,info))
            except Exception:pass
        self.signals.done.emit(reports,None)

class MoveJob(ManagedJob):
    def __init__(self,plans):super().__init__();self.plans=plans
    def work(self):self.outputs,self.errors=execute_moves(self.plans)

class ArchiveJob(ManagedJob):
    def __init__(self,files,target,output):
        super().__init__();self.files,self.target,self.output=files,target,Path(output)
    def work(self):
        if self.target=='ZIP':self.outputs.append(str(create_zip(self.files,self.output)));return
        for index,file in enumerate(self.files):
            self.control.base=index/max(1,len(self.files))*100;self.control.span=100/max(1,len(self.files))
            checkpoint(0,'Archiv wird geöffnet …');source=Path(file);name=source.name
            for suffix in ('.tar.gz','.tar.bz2','.tar.xz','.tgz','.zip','.rar','.tar','.gz'):
                if name.lower().endswith(suffix):name=name[:-len(suffix)];break
            number=0
            while True:
                target=self.output/(name+'_entpackt'+('' if number==0 else f'_{number}'))
                try:
                    self.outputs.append(str(extract_archive(source,target)));break
                except FileExistsError:
                    if target.exists():number+=1;continue
                    raise

class ToolJob(ManagedJob):
    def __init__(self,action,files,parameters,options):
        super().__init__();self.action,self.files,self.parameters,self.options=action,files,parameters,dict(options)
    def work(self):self.outputs=tool_outputs(self.action,self.files,self.parameters,self.options)

class DownloadJob(ManagedJob):
    def __init__(self,url,mode,folder,height):super().__init__();self.url,self.download_mode,self.folder,self.height=url,mode,folder,height
    def work(self):
        from downloader import download_link
        self.outputs=download_link(self.url,self.download_mode,self.folder,self.height)

class SelectionJob(QRunnable):
    def __init__(self):super().__init__();self.signals=Signals()
    def run(self):
        from link_selection import selected_link
        self.signals.done.emit(selected_link(),None)

class MediaInstallJob(ManagedJob):
    def work(self):
        from media_setup import install_media
        self.outputs=[str(install_media())]

class BackendCheck(QRunnable):
    def __init__(self):super().__init__();self.signals=Signals()
    def run(self):
        from filetypes import backend,run
        from extended import soffice
        status=[];missing=[]
        for name in ('ffmpeg','ffprobe','pandoc','LibreOffice'):
            executable=soffice() if name=='LibreOffice' else backend(name)
            if not executable:missing.append(name);status.append(name+': fehlt');continue
            try:
                result=run([executable,'-version' if name.startswith('ff') else '--version'],timeout=12)
                if result.returncode:raise OSError(result.stderr[:160] or 'Start fehlgeschlagen')
                line=result.stdout.splitlines()[0] if result.stdout else 'Gefunden'
                status.append(name+': '+executable+'\n'+line)
            except Exception as error:missing.append(name);status.append(name+': '+str(error))
        self.signals.done.emit(status,missing)

class Wheel(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.resize(380, 410)
        self.selected = -1
        self.labels = []
        self.all_actions = []
        self.page = 0
        self.page_timer = QTimer(self)
        self.page_timer.setSingleShot(True)
        self.page_timer.timeout.connect(self.next_page)
        self.mode = 'home'
        self.node = 'home'
        self.formats = []
        self.link = None
        self.latched = False
        self.kind = 'OrbitDrop'
        self.message = 'Datei in den Kreis ziehen'
        self.files = []
        self.revision = 0
        self.probes = set()
        self.checking = False
        self.paths = []
        self.colors = ['#7ed9ba', '#ffbe83', '#aaa3ff']
        self.receiving = False
        self.automatic = False

    def open(self, automatic=False, mode='home'):
        mode='home' if mode=='convert' else mode
        self.node='files' if mode=='files' else 'home'
        self.formats=[]
        self.link=None
        self.latched=False

        self.mode = mode
        self.automatic = automatic
        self.page_timer.stop()
        self.all_actions = []
        self.page = 0
        self.receiving = False
        self.selected = -1
        self.labels = []
        self.files = []
        self.kind = 'Dateiaktionen' if self.mode == 'files' else 'OrbitDrop'
        self.message = 'Dateien oder Ordner hineinziehen' if self.mode == 'files' else 'Datei in den Kreis ziehen'
        self.all_actions=list(available_file_actions())+['ZURÜCK'] if self.mode=='files' else home_actions([],None,[])
        self.display_page()
        self.revision += 1
        self.checking = False
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(cursor.x()-190, area.right()-379)),
                  max(area.top(), min(cursor.y()-190, area.bottom()-409)))
        self.show()
        self.raise_()
        self.update()

    def switch_mode(self,mode):
        mode='home' if mode=='convert' else mode
        if mode == self.mode:
            return
        files=self.files[:]
        self.mode=mode
        self.node='files' if mode=='files' else 'home'
        self.latched=False
        self.revision+=1
        self.page_timer.stop()
        self.files=[]
        self.all_actions=[]
        self.labels=[]
        self.page=0
        self.checking=False
        self.selected=-1
        self.kind='Dateiaktionen' if mode=='files' else 'OrbitDrop'
        self.message='Dateien oder Ordner hineinziehen' if mode=='files' else 'Datei hineinziehen'
        if mode=='files':
            self.all_actions=list(available_file_actions())+['ZURÜCK'];self.display_page()
        if files:self.inspect(files)
        self.repaint()

    def segment(self, pos):
        if not self.labels or self.checking:
            return -1
        for index, path in enumerate(self.paths):
            if path.contains(QPointF(pos)):
                return index
        return -1

    def open_link(self,url):
        if not media_link(url):return
        self.open();self.link=url;self.kind='Link';self.message='Download wählen · Audio oder Video';self.automatic=False;self.latched=True
        self.all_actions=['AUDIO LADEN','VIDEO LADEN','TOOLS'];self.display_page()

    def inspect(self, files):
        if self.files == files:
            return
        self.files = files
        self.link=None
        self.revision += 1
        revision = self.revision
        if self.mode == 'files':
            self.checking = False
            self.kind = 'Dateiaktionen'
            self.message = f'{len(files)} Datei(en)/Ordner'
            self.all_actions = list(available_file_actions(files))+['ZURÜCK']
            self.page = 0
            self.display_page()
            return
        self.labels = []
        self.selected = -1
        self.kind = 'Prüfe Dateien …'
        self.message = 'Bitte kurz halten'
        self.checking = True
        job = Inspection(files)
        self.probes.add(job)
        job.signals.done.connect(lambda actions, details: self.inspected(job, revision, actions, details))
        QThreadPool.globalInstance().start(job)
        self.repaint()

    def inspected(self, job, revision, actions, details):
        self.probes.discard(job)
        if getattr(job,'reports',None) and hasattr(self.controller,'record_diagnostics'):self.controller.record_diagnostics(job.reports)
        if revision != self.revision:
            return
        self.checking = False
        self.formats = list(actions)
        self.kind, self.message = details
        self.node='home'
        self.all_actions=home_actions(self.files,self.kind,self.formats)
        self.message='Grün: Konvertieren · Orange: Bearbeiten · Blau: Tools' if actions else self.message
        self.page = 0
        self.display_page()
        self.repaint()
        self.selected = self.segment(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def navigate(self,node):
        previous=self.node
        self.page_timer.stop();self.automatic=False;self.latched=True;self.node=node;self.page=0
        if node=='formats':
            self.all_actions=self.formats+['ZURÜCK']
            self.message='Zielformat wählen' if self.formats else ('Datei in den Kreis ziehen' if not self.files else 'Keine gemeinsame Konvertierung verfügbar. '+self.message)
        elif node=='edit':
            self.all_actions=edit_actions(self.files,self.kind)+['ZURÜCK']
            self.message='Bearbeitung wählen' if len(self.all_actions)>1 else 'Für diese Auswahl ist keine Bearbeitung verfügbar.'
        elif node in ('files','tools'):
            self.all_actions=(list(available_file_actions(self.files)) if self.files else [])+['LINK LADEN','PROGRAMM','ZURÜCK']
            self.message='Dateiaktionen und Hilfsfunktionen'
        elif node=='rotate':self.all_actions=['90° LINKS','90° RECHTS','180°','ZURÜCK'];self.message='Drehung wählen'
        elif node=='more':self.all_actions=['AUFTRÄGE','EINSTELLUNGEN','KONVERTER','DEBUGGING','HILFE','ZURÜCK'];self.message='OrbitDrop verwalten'
        else:
            self.all_actions=['AUDIO LADEN','VIDEO LADEN','TOOLS'] if self.link else home_actions(self.files,self.kind,self.formats)
            self.message='Grün: Konvertieren · Orange: Bearbeiten · Blau: Tools' if not self.link else 'Download wählen · Audio oder Video'
        self.display_page();self.show();self.raise_()

    def select_action(self,target):
        if target=='WEITER':self.next_page();return
        if target=='ZURÜCK':self.navigate('edit' if self.node=='rotate' else 'tools' if self.node=='more' else 'home');return
        branches={'KONVERTIEREN':'formats','UMWANDELN':'formats','BEARBEITEN':'edit','TOOLS':'tools','DATEIEN':'tools','PROGRAMM':'more','MEHR':'more','DREHEN':'rotate'}
        if target in branches:self.navigate(branches[target]);return
        files=self.files[:];kind=self.kind;node=self.node;url=self.link
        self.hide()
        if target in ('AUDIO LADEN','VIDEO LADEN','LINK LADEN'):
            QTimer.singleShot(0,lambda:self.controller.download_dialog(url,'video' if target=='VIDEO LADEN' else 'audio'))
        elif node=='formats':QTimer.singleShot(0,lambda:self.controller.convert_files(files,target))
        elif node in ('files','tools') and target in FILE_ACTIONS:QTimer.singleShot(0,lambda:self.controller.file_action(files,target))
        else:QTimer.singleShot(0,lambda:self.controller.circle_action(files,target,kind))

    def display_page(self):
        if len(self.all_actions) <= 6:
            self.labels = self.all_actions[:]
        else:
            self.labels = self.all_actions[self.page*5:(self.page+1)*5] + ['WEITER']
        self.selected = -1
        self.repaint()

    def next_page(self):
        if not self.isVisible() or len(self.all_actions) <= 6:
            return
        pages = math.ceil(len(self.all_actions)/5)
        self.page = (self.page+1) % pages
        self.display_page()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawEllipse(QRectF(18, 22, 344, 344))
        self.paths = []
        outer, inner = QRectF(24, 24, 332, 332), QRectF(107, 107, 166, 166)
        labels = self.labels or ['PRÜFE …' if self.checking else 'KONVERTER FEHLT' if 'konverter fehlt' in self.message.lower() else 'KEINE AKTION' if self.files else 'DATEI ZIEHEN']
        step = 360 / len(labels)
        for i, label in enumerate(labels):
            start = 88-i*step
            path = QPainterPath()
            path.arcMoveTo(outer, start)
            path.arcTo(outer, start, -(step-4))
            end = math.radians(start-(step-4))
            path.lineTo(190+83*math.cos(end), 190-83*math.sin(end))
            path.arcTo(inner, start-(step-4), step-4)
            path.closeSubpath()
            self.paths.append(path)
            accent=QColor(action_color(self.node,label))
            color=QColor(accent)
            if self.selected != i:color=QColor(round(accent.red()*.22),round(accent.green()*.22),round(accent.blue()*.22))
            p.setBrush(color)
            p.setPen(QPen(accent, 1))
            p.drawPath(path)
            angle = math.radians(-90+step/2+i*step)
            x, y = 190+125*math.cos(angle), 190+125*math.sin(angle)
            p.setPen(QColor('#14221e' if self.selected == i else '#f1f3fa'))
            p.setFont(QFont('Segoe UI', 10 if len(label) > 7 else 14, QFont.Weight.Bold))
            p.drawText(QRectF(x-48, y-22, 96, 44), Qt.AlignmentFlag.AlignCenter, MENU_LABELS.get(label,label))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#151925'))
        p.drawEllipse(inner.adjusted(6, 6, -6, -6))
        p.setPen(QColor('#f2f3fa'))
        p.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        p.drawText(QRectF(113, 155, 154, 30), Qt.AlignmentFlag.AlignCenter, {'formats':'Konvertieren','edit':'Bearbeiten','tools':'Tools','files':'Tools','more':'Programm','rotate':'Drehen','home':'Link laden' if self.link else 'OrbitDrop'}.get(self.node,self.kind))
        p.setFont(QFont('Segoe UI', 9))
        p.setPen(QColor('#aab4c9'))
        text = ('Kurz halten' if self.labels[self.selected] == 'WEITER' else 'Anklicken' if self.latched else 'Loslassen') if self.selected >= 0 else ('Bitte kurz halten' if self.checking else (('Anklicken' if self.latched else 'Aktion wählen') if self.labels else 'Konverter fehlt' if 'konverter fehlt' in self.message.lower() else 'Keine Aktion' if self.files else 'Datei hineinziehen'))
        p.drawText(QRectF(113, 188, 154, 45), Qt.AlignmentFlag.AlignCenter, text)
        p.setFont(QFont('Segoe UI', 8))
        p.setPen(QColor('#d5dbea'))
        p.drawText(QRectF(18, 358, 344, 48), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, (f'Seite {self.page+1}/{math.ceil(len(self.all_actions)/5)} · Auf WEITER kurz halten\n' if len(self.all_actions)>6 else '') + (DESCRIPTIONS.get(self.labels[self.selected], self.message) if self.node == 'files' and self.selected >= 0 else self.message))
        p.end()

    def dropped_link(self,mime):
        if mime.hasUrls() and len(mime.urls())==1 and not mime.urls()[0].isLocalFile():return media_link(mime.urls()[0].toString())
        return media_link(mime.text()) if mime.hasText() and not mime.hasUrls() else None

    def accept_files(self, event):
        mime = event.mimeData()
        valid = bool(self.dropped_link(mime)) or mime.hasUrls() and bool(mime.urls()) and all(u.isLocalFile() and (Path(u.toLocalFile()).is_file() or (self.node in ('home','files','tools') and Path(u.toLocalFile()).is_dir())) for u in mime.urls())
        if valid and event.possibleActions() & Qt.DropAction.CopyAction:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return True
        event.ignore()
        return False

    def dragEnterEvent(self, event):
        self.receiving = self.accept_files(event)
        if self.receiving:
            url=self.dropped_link(event.mimeData())
            if url:
                if self.link!=url:self.revision+=1;self.link=url;self.checking=False;self.files=[];self.kind='Link';self.node='home';self.all_actions=['AUDIO LADEN','VIDEO LADEN','TOOLS'];self.message='Download wählen · Audio oder Video';self.display_page()
            else:self.inspect([u.toLocalFile() for u in event.mimeData().urls()])
        self.selected = self.segment(event.position()) if self.receiving else -1
        self.update()

    def dragMoveEvent(self, event):
        if self.accept_files(event):
            url=self.dropped_link(event.mimeData())
            if not url:self.inspect([u.toLocalFile() for u in event.mimeData().urls()])
            self.selected = self.segment(event.position())
            if self.selected >= 0 and self.labels[self.selected] == 'WEITER':
                if not self.page_timer.isActive():
                    self.page_timer.start(650)
                event.ignore()
            else:
                self.page_timer.stop()
                if self.selected < 0:
                    event.ignore()
        self.update()

    def dragLeaveEvent(self, event):
        self.page_timer.stop()
        self.receiving = False
        self.selected = -1
        self.update()

    def dropEvent(self, event):
        self.page_timer.stop()
        index = self.segment(event.position())
        if index < 0 or not self.accept_files(event):
            event.ignore()
            return
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files != self.files and not self.dropped_link(event.mimeData()):
            event.ignore();return
        self.select_action(self.labels[index])

    def mousePressEvent(self,event):
        index=self.segment(event.position())
        if index>=0:self.select_action(self.labels[index])
        elif self.node!='home' and 83>((event.position().x()-190)**2+(event.position().y()-190)**2)**.5:self.navigate('home')
        else:self.hide()

class Controller:
    def __init__(self, app, prefs=None):
        self.app = app
        self.prefs=prefs or Preferences(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        from diagnostics import DiagnosticStore
        self.diagnostics=DiagnosticStore(self.prefs)
        self.diagnostic_jobs=set()
        self.tasks=TasksWindow(self.prefs)
        self.was_keys={key:False for key in KEY_CODES}
        self.selection_job=None;self.selection_pending=False;self.selection_revision=0
        self.backend_check=None
        self.backend_status=[]
        self.backend_missing=[]
        self.wheel = Wheel(self)
        self.shelf = Shelf()
        self.jobs = set()
        self.pool = QThreadPool.globalInstance()
        icon = QPixmap(64, 64)
        icon.fill(Qt.GlobalColor.transparent)
        p = QPainter(icon)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor('#7ed9ba'))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(5, 5, 54, 54)
        p.setPen(QPen(QColor('#151925'), 5))
        p.drawEllipse(20, 20, 24, 24)
        p.end()
        self.tray = QSystemTrayIcon(QIcon(icon), app)
        self.tray.setToolTip(f"OrbitDrop · {self.prefs.values['convert_key']}: Aktionskreis · {self.prefs.values['files_key']}: Dateiaktionen")
        menu = QMenu()
        for label, callback in [('Aktionskreis', lambda: self.wheel.open()),
                                ('Dateiaktionen (Strg)', lambda: self.wheel.open(mode='files')),
                                ('Dateiablage öffnen', lambda: self.shelf.open()),
                                ('Aufträge & Verlauf', self.show_tasks),
                                ('Einstellungen', self.settings),
                                ('Werkzeuge: Bilder / PDF / Video', self.tools),
                                ('Konverter prüfen / einrichten', self.media_status),
                                ('Anleitung', self.help), ('Beenden', self.quit)]:
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.activated)
        self.tray.show()
        self.released = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(25)
        self.tray.showMessage('OrbitDrop bereit', 'Datei ziehen: Shift für den Aktionskreis, Strg für Dateiaktionen. Hilfe findest du unter Tools → Programm.')
        if '--preview' in sys.argv:self.wheel.open()
        if self.prefs.values['check_backends']:QTimer.singleShot(300,lambda:self.check_backends(False))

    def activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.wheel.open()

    def poll(self):
        if sys.platform != 'win32':
            return
        key = ctypes.windll.user32.GetAsyncKeyState
        states={name:bool(key(code)&0x8000) for name,code in KEY_CODES.items()}
        left,escape=bool(key(0x01)&0x8000),bool(key(0x1B)&0x8000)
        convert_key=self.prefs.values['convert_key'];files_key=self.prefs.values['files_key']
        mode='files' if states[files_key] and not self.was_keys[files_key] else 'home' if states[convert_key] and not self.was_keys[convert_key] else None
        if mode and left:
            if self.wheel.isVisible():self.wheel.switch_mode(mode)
            else:self.wheel.open(automatic=True,mode=mode)
        if mode=='home':
            self.selection_pending=True
            if not left:self.request_selection()
        self.was_keys=states
        if self.selection_pending and not left:
            self.selection_pending=False
            if self.wheel.isVisible() and self.wheel.files:pass
            elif not self.selection_job:self.request_selection()
        if escape:
            self.selection_pending=False;self.selection_revision+=1;self.wheel.hide()
        if self.wheel.isVisible() and self.wheel.automatic and not left:
            # Let the OLE drop event finish before hiding a canceled palette.
            self.released += 1
            if self.released > 12:
                self.wheel.hide()
        else:
            self.released = 0

    def request_selection(self):
        if self.selection_job:return
        self.selection_pending=False;self.selection_revision+=1;revision=self.selection_revision
        job=SelectionJob();self.selection_job=job
        job.signals.done.connect(lambda url,unused:self.selection_ready(job,revision,url));self.pool.start(job)
    def selection_ready(self,job,revision,url):
        if self.selection_job is job:self.selection_job=None
        if revision!=self.selection_revision or (self.wheel.isVisible() and self.wheel.files):return
        if url:self.wheel.open_link(url)
    def download_dialog(self,url=None,mode='audio'):
        from download_ui import DownloadDialog
        DownloadDialog(url,mode,self.prefs.values.get('output_dir',''),self.submit_download).exec()
    def submit_download(self,url,mode,folder,height):
        self.submit(DownloadJob(url,mode,folder,height),'Download · '+('Audio' if mode=='audio' else 'Video'))

    def show_tasks(self):self.tasks.show();self.tasks.raise_();self.tasks.activateWindow()
    def tools(self,files=None,action=None):
        dialog=ToolsDialog()
        if action:dialog.action.setCurrentText(action)
        for file in files or []:dialog.files.addItem(str(file))
        if dialog.exec():
            action,files,parameters=dialog.selection()
            if action=='Video kürzen':self.circle_action(files,'SCHNEIDEN','Video')
            else:self.submit(ToolJob(action,files,parameters,self.prefs.values),action)
    def circle_action(self,files,action,kind):
        try:
            if action=='AUFTRÄGE':self.show_tasks()
            elif action=='EINSTELLUNGEN':self.settings()
            elif action=='KONVERTER':self.media_status()
            elif action=='WERKZEUGE':self.tools(files)
            elif action=='HILFE':self.help()
            elif action=='DEBUGGING':
                from diagnostics_ui import DiagnosticsDialog
                DiagnosticsDialog(self.diagnostics).exec()
            elif action=='SCHNEIDEN':
                if kind=='Audio':
                    from audio_editor import AudioEditor
                    AudioEditor(files[0],self.submit_editor).exec()
                else:
                    from video_editor import VideoEditor
                    VideoEditor(files[0],self.submit_editor).exec()
            elif action=='ZUSCHNEIDEN':
                from image_editor import ImageEditor
                ImageEditor(files[0],self.submit_editor).exec()
            elif action in ('90° LINKS','90° RECHTS','180°'):
                angle={'90° LINKS':270,'90° RECHTS':90,'180°':180}[action]
                self.submit(ToolJob('Bild drehen' if kind=='Bild' else 'Video drehen',files,{'angle':angle},self.prefs.values),'Drehen: '+Path(files[0]).name)
            elif action=='GRÖSSE':self.tools(files,'Bildgröße ändern')
            elif action=='PDF TEILEN':self.tools(files,'PDF aufteilen')
            elif action=='PDF VERBINDEN':self.tools(files,'PDFs zusammenfügen')
        except Exception as error:QMessageBox.warning(None,'OrbitDrop · Bearbeiten',str(error))
    def record_diagnostics(self,items):
        job=DiagnosticJob(items);self.diagnostic_jobs.add(job)
        job.signals.done.connect(lambda reports,unused:self.diagnostics_ready(job,reports));self.pool.start(job)
    def diagnostics_ready(self,job,reports):
        self.diagnostic_jobs.discard(job)
        try:self.diagnostics.add(reports)
        except OSError as error:self.tray.showMessage('Debugging','Diagnose konnte nicht gespeichert werden: '+str(error))
    def submit_editor(self,action,files,parameters):
        self.submit(ToolJob(action,files,parameters,self.prefs.values),action+': '+Path(files[0]).name)

    def settings(self):
        if SettingsDialog(self.prefs).exec():
            self.tray.setToolTip(f"OrbitDrop · {self.prefs.values['convert_key']}: Aktionskreis · {self.prefs.values['files_key']}: Dateiaktionen")
    def quit(self):
        if self.tasks.has_running():
            self.tasks.cancel_all();self.show_tasks()
            self.tray.showMessage('Abbruch angefordert','OrbitDrop beendet sich, sobald die laufenden Aufträge gestoppt sind.')
            self.quit_timer=QTimer();self.quit_timer.timeout.connect(lambda:self.app.quit() if not self.tasks.has_running() else None);self.quit_timer.start(200)
        else:self.app.quit()
    def submit(self,job,title):
        key=self.tasks.add(job,title);self.jobs.add(job)
        job.signals.progress.connect(lambda percent,message:self.tasks.progress(key,percent,message))
        job.signals.done.connect(lambda outputs,errors:self.job_done(job,key,outputs,errors))
        self.pool.start(job)
    def job_done(self,job,key,outputs,errors):
        self.jobs.discard(job);self.tasks.finish(key,outputs,errors,job.was_cancelled)
        status='Abgebrochen' if job.was_cancelled else 'Fehler' if errors else 'Fertig'
        self.tray.showMessage(status,f'{len(outputs)} Ergebnis(se). Details unter Aufträge & Verlauf.')
        if isinstance(job,MediaInstallJob) and not errors and not job.was_cancelled:
            from filetypes import encoders
            from diagnostics import environment
            environment.cache_clear();encoders.cache_clear();self.check_backends(False)
    def media_status(self):self.check_backends(True)
    def check_backends(self,show=False):
        if self.backend_check:
            self.show_backend_when_ready=getattr(self,'show_backend_when_ready',False) or show
            return
        self.show_backend_when_ready=show;job=BackendCheck();self.backend_check=job
        job.signals.done.connect(self.backends_checked);self.pool.start(job)
    def backends_checked(self,status,missing):
        self.backend_check=None;self.backend_status=status;self.backend_missing=missing
        if self.show_backend_when_ready:self.show_backend_dialog()
        elif missing:self.tray.showMessage('Konverterprüfung',', '.join(missing)+' fehlt oder startet nicht. Einrichtung im Infobereich-Menü.')
    def show_backend_dialog(self):
        box=QMessageBox();box.setWindowTitle('OrbitDrop · Konverter');box.setText('\n\n'.join(self.backend_status));box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        install=box.addButton('Medien einrichten',QMessageBox.ButtonRole.ActionRole)
        office=box.addButton('LibreOffice-Download',QMessageBox.ButtonRole.ActionRole)
        pandoc=box.addButton('Pandoc-Download',QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close);box.exec()
        if box.clickedButton()==install:
            self.submit(MediaInstallJob(),'Medien einrichten')
        elif box.clickedButton() in (office,pandoc):
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl('https://www.libreoffice.org/download/download-libreoffice/' if box.clickedButton()==office else 'https://pandoc.org/installing.html'))

    def file_action(self,files,action):
        try:
            validate_paths(files)
            if action=='ABLAGE':
                self.shelf.open(files)
            elif action=='KOPIEREN':
                QApplication.clipboard().setMimeData(file_mime(files))
                self.tray.showMessage('Kopiert', 'Dateien/Ordner mit Strg+V am Ziel einfügen.')
            elif action=='PFAD':
                QApplication.clipboard().setText(copy_paths_text(files))
                self.tray.showMessage('Pfade kopiert', 'Ein vollständiger Pfad pro Zeile.')
            elif action=='TERMINAL':
                open_terminals(files)
            elif action=='EXPLORER':
                show_in_explorer(files)
            elif action in ('ZIP','ENTPACKEN'):
                if action=='ZIP':
                    suggested=Path(files[0]).parent/((Path(files[0]).stem if len(files)==1 else 'Auswahl')+'.zip')
                    output,_=QFileDialog.getSaveFileName(None,'Neue ZIP-Datei speichern',str(suggested),'ZIP-Archiv (*.zip)',options=QFileDialog.Option.DontConfirmOverwrite)
                    if not output:return
                    if not output.lower().endswith('.zip'):output+='.zip'
                    if Path(output).exists():
                        raise FileExistsError('Diese ZIP existiert bereits. Bitte einen neuen Namen wählen.')
                else:
                    output=QFileDialog.getExistingDirectory(None,'Zielordner zum Entpacken wählen')
                    if not output:return
                job=ArchiveJob(files,action,output)
                self.submit(job,'ZIP erstellen' if action=='ZIP' else 'Entpacken')
            elif action=='VERSCHIEBEN':
                folder=QFileDialog.getExistingDirectory(None,'Zielordner für die Originale wählen')
                if not folder:return
                plans=plan_moves(files,folder)
                job=MoveJob(plans)
                self.submit(job,'Verschieben')
        except Exception as error:
            QMessageBox.warning(None,'OrbitDrop · Dateiaktion',str(error))

    def convert_files(self,files,target):
        title=Path(files[0]).name+f' → {target}'+(f' (+{len(files)-1})' if len(files)>1 else '')
        self.submit(Conversion(files,target,self.prefs.values),title)

    def help(self):
        QMessageBox.information(None, 'OrbitDrop 0.8.1 · Prototyp',
            '1. Datei im Explorer mit linker Maustaste ziehen.\n'
            '2. Shift für den Aktionskreis oder Strg für Tools kurz antippen.\n'
            '3. Grün: Konvertieren · Orange: Bearbeiten · Blau: Tools.\n'
            '4. Auf der Aktion loslassen. Untermenüs anschließend anklicken.\n'
            'Einstellungen/Verlauf: Tools → Programm. Link markieren + Shift: Download auswählen.\n\n'
            'Falls kein Kreis erscheint: Kreis über das Infobereich-Symbol öffnen, '
            'danach das Bild auf ein Segment ziehen. Esc bricht ab.\n\n'
            'Konvertieren/Kopieren/Ablage erhalten Originale. VERSCHIEBEN versetzt sie ins gewählte Ziel.\n'
            'ZIP: Dateien/Ordner zusammenpacken. ENTPACKEN erscheint bei Archiven.\n'
            'Ablage: Fenster bleibt oben, Einträge in andere Apps ziehen; Leeren löscht keine Dateien.\n'
            'JPG bekommt bei Transparenz einen weißen Hintergrund. '
            'Animationen/mehrseitige Bilder werden abgelehnt.\n'
            'Audio/Video benötigen ffmpeg.exe und ffprobe.exe im Ordner bin oder PATH.\n'
            'Office/E-Books benötigen je nach Format LibreOffice und Pandoc.\n'
            'Bei vielen Formaten auf WEITER kurz halten.\n'
            'PDF: Bilder als ZIP, PPTX als Seitenbilder, DOCX als Text; keine OCR.\n'
            'Bitte ohne Administratorrechte starten, genauso wie den Explorer.')

if __name__ == '__main__':
    if '--download-worker' in sys.argv:
        from downloader import worker_main
        sys.exit(worker_main(sys.argv[sys.argv.index('--download-worker')+1]))
    if '--setup-media' in sys.argv:
        from media_setup import main
        result=main()
        if getattr(sys,'frozen',False):
            # A windowed EXE has no console; display a final result instead.
            setup_app=QApplication([])
            QMessageBox.information(None,'Medien-Setup','Einrichtung abgeschlossen. OrbitDrop neu starten.' if not result else 'Einrichtung fehlgeschlagen. Bitte FFmpeg/FFprobe manuell in bin ablegen.')
        sys.exit(result)
    app = QApplication(sys.argv)
    app.setApplicationName('OrbitDrop')
    app.setQuitOnLastWindowClosed(False)
    state_root=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    single=SingleInstance(state_root)
    if not single.acquire():sys.exit(0)
    controller = Controller(app,Preferences(state_root))
    single.activated.connect(controller.show_tasks)
    app.aboutToQuit.connect(single.release)
    sys.exit(app.exec())
