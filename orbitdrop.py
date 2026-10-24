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
from preferences import Preferences,KEY_CODES,pressed_mode,shortcut_hint,polling_keys
from app_ui import SettingsDialog,TasksWindow,STYLE
from single_instance import SingleInstance
from tools import tool_outputs
from tools_ui import ToolsDialog
from circle_menu import home_actions,edit_actions,MENU_LABELS,action_color,direct_actions
from link_selection import media_link
from window_focus import present

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
        self.preview=None
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
            if len(self.files)==1 and kind=='Bild':
                try:
                    from PIL import Image,ImageOps
                    from image_editor import pil_qimage
                    with Image.open(self.files[0]) as source:
                        if source.width*source.height<=40_000_000:
                            thumb=ImageOps.exif_transpose(source);thumb.thumbnail((160,160));self.preview=pil_qimage(thumb)
                except Exception:pass
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

class ArchiveOptionsJob(ManagedJob):
    def __init__(self,files,output,parameters,extract=False):
        super().__init__();self.files,self.output,self.parameters,self.extract=files,output,dict(parameters),extract;self.errors=[]
    def work(self):
        from archive_options import create_archive,extract_options
        if not self.extract:self.outputs=create_archive(self.files,self.output,**self.parameters);return
        for file in self.files:
            checkpoint(message='Archiv: '+Path(file).name)
            try:self.outputs.extend(extract_options(file,self.output,**self.parameters))
            except Cancelled:raise
            except Exception as error:self.errors.append(Path(file).name+': '+str(error))

class ToolJob(ManagedJob):
    def __init__(self,action,files,parameters,options):
        super().__init__();self.action,self.files,self.parameters,self.options=action,files,parameters,dict(options)
    def work(self):self.outputs=tool_outputs(self.action,self.files,self.parameters,self.options)

class DownloadJob(ManagedJob):
    def __init__(self,url,mode,folder,height,entries=None):
        super().__init__();self.url,self.download_mode,self.folder,self.height=url,mode,folder,height;self.entries=entries;self.errors=[]
    def work(self):
        from downloader import download_link
        entries=self.entries if self.entries is not None else [{'url':self.url,'title':'Download'}]
        for index,entry in enumerate(entries):
            self.control.base=index/max(1,len(entries))*100;self.control.span=100/max(1,len(entries))
            checkpoint(0,f"{index+1}/{len(entries)} · {entry['title']}")
            try:self.outputs.extend(download_link(entry['url'],self.download_mode,self.folder,self.height))
            except Cancelled:raise
            except Exception as error:self.errors.append(f"{index+1}/{len(entries)} · {entry['title']}: {error}")

class SelectionJob(QRunnable):
    def __init__(self):super().__init__();self.signals=Signals()
    def run(self):
        from link_selection import selected_link
        self.signals.done.emit(selected_link(),None)

class MediaInstallJob(ManagedJob):
    def work(self):
        from media_setup import install_media
        self.outputs=[str(install_media())]

class SetupJob(ManagedJob):
    def __init__(self,key,state_root):super().__init__();self.key=key;self.state_root=state_root
    def work(self):
        from setup_tools import install_tool
        self.outputs=[install_tool(self.key,self.state_root)]

class BackendCheck(QRunnable):
    def __init__(self,state_root):super().__init__();self.state_root=state_root;self.signals=Signals()
    def run(self):
        from setup_tools import check_tools
        status=check_tools(self.state_root)
        self.signals.done.emit(status,[row['id'] for row in status if not row['ready']])


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
        self.circle_size=700
        self.preview=None;self.ring_paths=[];self.action_titles={}
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
        self.node='home' if mode=='home' else 'direct'
        self.formats=[]
        self.preview=None
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
        self.display_mode()
        self.revision += 1
        self.checking = False
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(cursor.x()-(self.circle_size//2 if self.node=='direct' else 190), area.right()-self.width()+1)),
                  max(area.top(), min(cursor.y()-(self.circle_size//2 if self.node=='direct' else 190), area.bottom()-self.height()+1)))
        self.show()
        self.raise_()
        self.update()

    def switch_mode(self,mode):
        if mode == self.mode:
            self.display_mode();return
        files=self.files[:]
        self.mode=mode
        self.node='home' if mode=='home' else 'direct'
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
        self.formats=[];self.preview=None;self.link=None
        self.display_mode()
        if files:self.inspect(files)
        self.repaint()

    def display_mode(self):
        if self.mode=='home':
            self.node='home';self.all_actions=home_actions(self.files,self.kind,self.formats)
            self.message='Konvertieren · Bearbeiten · Tools'
        else:
            self.node='direct'
            actions=self.context_actions(files_only=self.mode=='files')
            prefixes={'convert':('format:',),'edit':('edit:',),'files':('tool:','app:')}[self.mode]
            self.all_actions=[action for action in actions if action.startswith(prefixes)]
            back='format:' if self.mode=='convert' else 'edit:' if self.mode=='edit' else 'app:'
            self.all_actions.append(back+'ZURÜCK')
            title={'convert':'Konvertieren','edit':'Bearbeiten','files':'Tools'}[self.mode]
            self.message=title+' · Datei hineinziehen' if not self.files else title+' · Aktion wählen'
            if self.files and len(self.all_actions)==1:self.message=title+' · Keine passenden Aktionen verfügbar'
        self.display_page()

    def context_actions(self,files_only=False):
        values=getattr(getattr(self.controller,'prefs',None),'values',{})
        presets=values.get('quick_actions',[])
        self.action_titles={'edit:quick:'+p['id']:p['name'] for p in presets};workflows=values.get('workflows',[])
        self.action_titles.update({'edit:flow:'+p['id']:p['name'] for p in workflows})
        actions=direct_actions(self.files,self.kind,self.formats,values.get('hidden_formats',[]),files_only=files_only,presets=presets,workflows=workflows)
        from menu_visibility import visible_actions
        actions=visible_actions(actions,values)
        favorites=values.get('favorite_actions',[])
        return sorted(actions,key=lambda key:key not in favorites)

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
        self.node='direct';self.all_actions=['download:AUDIO LADEN','download:VIDEO LADEN']+direct_actions([],None,[]);self.display_page()

    def inspect(self, files):
        if self.files == files:
            return
        self.files = files
        self.preview=None
        self.link=None
        self.revision += 1
        revision = self.revision
        if self.mode == 'files':
            self.checking = False
            self.kind = 'Dateiaktionen'
            self.message = f'{len(files)} Datei(en)/Ordner'
            self.formats=[];self.page=0;self.display_mode()
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
        self.preview=getattr(job,'preview',None)
        self.page=0
        self.display_mode()
        self.repaint()
        self.selected = self.segment(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def navigate(self,node):
        self.page_timer.stop();self.automatic=False;self.latched=True;self.page=0
        actions=self.context_actions()
        if node=='home':
            self.node='home';self.all_actions=home_actions(self.files,self.kind,self.formats)
            self.message='Grün: Konvertieren · Orange: Bearbeiten · Blau: Tools'
        else:
            self.node='direct'
            prefixes={'formats':('format:',),'edit':('edit:',),'rotate':('edit:90°','edit:180°'),'svg':('format:SVG ',),'more':('app:',)}.get(node,('tool:','app:'))
            self.all_actions=[action for action in actions if action.startswith(prefixes)]
            back='format:' if node in ('formats','svg') else 'edit:' if node in ('edit','rotate') else 'app:'
            self.all_actions.append(back+'ZURÜCK')
            self.message={'formats':'Konvertieren · Zielformat wählen','edit':'Bearbeiten · Aktion wählen'}.get(node,'Tools · Aktion wählen')
            if len(self.all_actions)==1:self.message='Keine passenden Aktionen verfügbar · Zurück wählen'
        self.display_page();self.show();self.raise_()

    def select_action(self,target):
        if self.node=='direct':
            category,action=target.split(':',1)
            if action=='ZURÜCK':self.navigate('home');return
            files=self.files[:];kind=self.kind;url=self.link;self.hide()
            if category=='download' or action=='LINK LADEN':QTimer.singleShot(0,lambda:self.controller.download_dialog(url,'video' if action=='VIDEO LADEN' else 'audio'))
            elif category=='format' and action not in ('SVG SCHNELL','SVG ERWEITERT'):QTimer.singleShot(0,lambda:self.controller.convert_files(files,action))
            elif category=='tool':QTimer.singleShot(0,lambda:self.controller.file_action(files,action))
            else:QTimer.singleShot(0,lambda:self.controller.circle_action(files,action,kind))
            return
        category_modes={'KONVERTIEREN':('convert','formats'),'UMWANDELN':('convert','formats'),'BEARBEITEN':('edit','edit'),'TOOLS':('files','tools'),'DATEIEN':('files','tools')}
        if target in category_modes:
            mode,node=category_modes[target]
            if self.files and self.kind=='Dateiaktionen' and mode!='files':
                self.switch_mode(mode);self.automatic=False;self.latched=True
            else:
                self.mode=mode;self.navigate(node)
            return
        if target=='WEITER':self.next_page();return
        if target=='ZURÜCK':self.navigate('edit' if self.node=='rotate' else 'formats' if self.node=='svg' else 'tools' if self.node=='more' else 'home');return
        branches={'KONVERTIEREN':'formats','UMWANDELN':'formats','BEARBEITEN':'edit','TOOLS':'tools','DATEIEN':'tools','PROGRAMM':'more','MEHR':'more','DREHEN':'rotate'}
        if target=='SVG' and self.node=='formats':self.navigate('svg');return
        if target in branches:self.navigate(branches[target]);return
        files=self.files[:];kind=self.kind;node=self.node;url=self.link
        self.hide()
        if target in ('AUDIO LADEN','VIDEO LADEN','LINK LADEN'):
            QTimer.singleShot(0,lambda:self.controller.download_dialog(url,'video' if target=='VIDEO LADEN' else 'audio'))
        elif node=='formats':QTimer.singleShot(0,lambda:self.controller.convert_files(files,target))
        elif node in ('files','tools') and target in FILE_ACTIONS:QTimer.singleShot(0,lambda:self.controller.file_action(files,target))
        else:QTimer.singleShot(0,lambda:self.controller.circle_action(files,target,kind))

    def display_page(self):
        from menu_visibility import visible_actions
        values=getattr(getattr(self.controller,'prefs',None),'values',{})
        self.all_actions=visible_actions(self.all_actions,values)
        if not self.all_actions:self.message='Alle Menüpunkte ausgeblendet · Einstellungen über das Tray öffnen'
        if self.node=='direct':
            self.labels=self.all_actions[:];self.selected=-1
            screen=QApplication.screenAt(self.pos()) or QApplication.primaryScreen();area=screen.availableGeometry()
            self.circle_size=max(320,min(720,area.width()-20,area.height()-90));self.resize(self.circle_size,self.circle_size+65)
            self.move(max(area.left(),min(self.x(),area.right()-self.width()+1)),max(area.top(),min(self.y(),area.bottom()-self.height()+1)));self.repaint();return
        if len(self.all_actions) <= 6:
            self.labels = self.all_actions[:]
        else:
            self.labels = self.all_actions[self.page*5:(self.page+1)*5] + ['WEITER']
        self.selected = -1
        self.resize(470,450) if self.node=='home' else self.resize(880,510)
        screen=QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        area=screen.availableGeometry()
        self.move(max(area.left(),min(self.x(),area.right()-self.width()+1)),max(area.top(),min(self.y(),area.bottom()-self.height()+1)))
        self.repaint()

    def next_page(self):
        if not self.isVisible() or len(self.all_actions) <= 6:
            return
        pages = math.ceil(len(self.all_actions)/5)
        self.page = (self.page+1) % pages
        self.display_page()
        self.update()

    def paintEvent(self,event):
        if self.node=='direct':
            from direct_wheel import paint_direct
            paint_direct(self);return
        from wheel_render import paint_wheel
        paint_wheel(self)

    def dropped_link(self,mime):
        if mime.hasUrls() and len(mime.urls())==1 and not mime.urls()[0].isLocalFile():return media_link(mime.urls()[0].toString())
        return media_link(mime.text()) if mime.hasText() and not mime.hasUrls() else None

    def accept_files(self, event):
        mime = event.mimeData()
        valid = bool(self.dropped_link(mime)) or mime.hasUrls() and bool(mime.urls()) and all(u.isLocalFile() and (Path(u.toLocalFile()).is_file() or (self.node in ('home','files','tools','direct') and Path(u.toLocalFile()).is_dir())) for u in mime.urls())
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
                if self.link!=url:self.revision+=1;self.link=url;self.checking=False;self.files=[];self.kind='Link';self.node='direct';self.all_actions=['download:AUDIO LADEN','download:VIDEO LADEN']+direct_actions([],None,[]);self.message='Download wählen · Audio oder Video';self.display_page()
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

    def mouseMoveEvent(self,event):
        self.selected=self.segment(event.position());self.update()

    def leaveEvent(self,event):
        self.selected=-1;self.update();super().leaveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton and not self.checking:
            self.hide();QTimer.singleShot(0,lambda:self.controller.circle_action(self.files[:],'AKTIONSSUCHE',self.kind));return
        index=self.segment(event.position())
        if index>=0:self.select_action(self.labels[index])
        elif self.node=='direct':self.hide()
        elif self.node!='home' and any(path.contains(event.position()) for path in self.ring_paths):
            index=next(i for i,path in enumerate(self.ring_paths) if path.contains(event.position()))
            self.navigate(('formats','edit','tools')[index])
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
        self.selection_job=None;self.selection_pending=False;self.selection_revision=0;self.selection_origin=None
        from activation_guard import ActivationGuard
        self.activation_guard=ActivationGuard();self.shortcuts_paused=False;self.update_job=None
        self.dashboard=None;self.setup_job=None;self.downloader_window=None
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
        self.tray.setToolTip('OrbitDrop · Tastenzugänge pausiert' if self.shortcuts_paused else 'OrbitDrop · '+shortcut_hint(self.prefs.values))
        menu = QMenu()
        for label, callback in [('Dashboard',lambda:self.show_dashboard()),
                                ('Audio/Video-Downloader',lambda:self.download_dialog()),
                                ('Nach Updates suchen',lambda:self.updates()),
                                ('Beenden',self.quit)]:
            action=QAction(label,menu);action.triggered.connect(callback);menu.addAction(action)
        self.pause_action=QAction('OrbitDrop pausieren',menu);self.pause_action.setCheckable(True);self.pause_action.toggled.connect(self.pause_shortcuts);menu.insertAction(menu.actions()[-1],self.pause_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.activated)
        self.tray.show()
        self.released = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(25)
        self.tray.showMessage('OrbitDrop bereit','Datei ziehen: '+shortcut_hint(self.prefs.values))
        if '--preview' in sys.argv:self.wheel.open()
        if self.prefs.values['show_dashboard']:QTimer.singleShot(100,lambda:self.show_dashboard())
        if self.prefs.values['check_backends']:QTimer.singleShot(300,lambda:self.check_backends(False))
        if self.prefs.values.get('check_updates',True):QTimer.singleShot(1500,self.auto_update_check)

    def activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.wheel.open()

    def pause_shortcuts(self,paused):
        self.shortcuts_paused=paused;self.selection_pending=False;self.selection_revision+=1
        if paused and self.wheel.automatic:self.wheel.hide()
        self.tray.setToolTip('OrbitDrop · pausiert' if paused else 'OrbitDrop · '+shortcut_hint(self.prefs.values))
        action=getattr(self,'pause_action',None)
        if action is not None:
            action.blockSignals(True);action.setChecked(paused);action.blockSignals(False)
        dashboard=getattr(self,'dashboard',None)
        if dashboard is not None:
            dashboard.pause_keys.blockSignals(True);dashboard.pause_keys.setChecked(paused);dashboard.pause_keys.blockSignals(False)

    def poll(self):
        if sys.platform != 'win32':
            return
        key = ctypes.windll.user32.GetAsyncKeyState
        states={name:bool(key(code)&0x8000) for name,code in polling_keys(self.prefs.values).items()}
        left,escape=bool(key(0x01)&0x8000),bool(key(0x1B)&0x8000)
        if self.shortcuts_paused:
            self.activation_guard.reset_drag(left)
            if escape:self.wheel.hide()
            self.was_keys=states;self.selection_pending=False;return
        if QApplication.activeModalWidget() is not None:
            self.activation_guard.reset_drag(left)
            self.was_keys=states;self.selection_pending=False;return
        mode=pressed_mode(self.prefs.values,states,self.was_keys)
        context=self.activation_guard.context(mouse_down=left)
        if mode and left and context.drag:
            if self.wheel.isVisible():
                self.wheel.automatic=mode!='files';self.wheel.switch_mode(mode)
            else:self.wheel.open(automatic=mode!='files',mode=mode)
        if mode=='convert' and not left and context.selection:self.request_selection()
        self.was_keys=states
        self.selection_pending=False
        if not context.drag and self.wheel.isVisible() and self.wheel.automatic:
            self.wheel.hide();self.released=0
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
        if self.selection_job or self.shortcuts_paused:return
        context=self.activation_guard.context()
        if not context.selection:return
        self.selection_origin=context.token
        self.selection_pending=False;self.selection_revision+=1;revision=self.selection_revision
        job=SelectionJob();self.selection_job=job
        job.signals.done.connect(lambda url,unused:self.selection_ready(job,revision,url));self.pool.start(job)
    def selection_ready(self,job,revision,url):
        if self.selection_job is job:self.selection_job=None
        if revision!=self.selection_revision or self.shortcuts_paused or (self.wheel.isVisible() and self.wheel.files):return
        context=self.activation_guard.context()
        if not context.selection or context.token!=self.selection_origin:return
        if url:self.wheel.open_link(url)
    def download_dialog(self,url=None,mode='audio'):
        if getattr(self,'downloader_window',None) is None:
            from download_manager import DownloadManager
            self.downloader_window=DownloadManager(self)
            area=(QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()).availableGeometry()
            self.downloader_window.resize(min(1130,area.width()-30),min(800,area.height()-45))
        self.downloader_window.open_link(url,mode);present(self.downloader_window)
    def submit_download(self,url,mode,folder,height,entries=None,show_tasks=True,observer=None):
        if entries is not None:
            if not entries or len(entries)>10000 or any(not media_link(entry.get('url')) or not entry.get('available') for entry in entries):raise ValueError('Bitte verfügbare Playlist-Titel auswählen.')
            entries=[dict(entry) for entry in entries]
        if not media_link(url) or mode not in ('audio','video') or not Path(folder).is_dir():raise ValueError('Bitte einen gültigen Link, Audio/Video und einen vorhandenen Ordner wählen.')
        self.prefs.update(dict(self.prefs.values,download_dir=str(Path(folder).resolve())))
        job=DownloadJob(url,mode,folder,height,entries)
        if observer:observer(job)
        self.submit(job,'Download · '+('Audio' if mode=='audio' else 'Video')+(f' · {len(entries)} Titel' if entries is not None else ''),show=show_tasks)
        return job

    def show_tasks(self):present(self.tasks)
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
            if action in ('DATEN PRÜFEN','TEXTWERKZEUGE','TABELLE','LOG ANSEHEN','SHA-256','VERGLEICHEN','ZERTIFIKAT'):
                from data_formats import kind_for
                if action=='DATEN PRÜFEN':
                    from data_editor_ui import DataEditor
                    DataEditor(files[0],kind_for(files[0]),self.prefs.values.get('output_dir') or None).exec()
                else:
                    from admin_tools_ui import AdminToolsDialog
                    mode={'TEXTWERKZEUGE':'text','TABELLE':'table','LOG ANSEHEN':'log','SHA-256':'hash','VERGLEICHEN':'compare','ZERTIFIKAT':'certificate'}[action]
                    AdminToolsDialog(files,mode,self.prefs.values.get('output_dir') or None).exec()
            elif action=='WEBCAM / MIKRO':
                from device_test_ui import DeviceTestDialog
                DeviceTestDialog().exec()
            elif action=='VERGRÖSSERN':
                from upscale_ui import UpscaleDialog
                if len(files)!=1:raise ValueError('Bitte genau ein Bild auswählen.')
                UpscaleDialog(files[0],self.submit_editor).exec()
            elif action=='TEXT ERKENNEN':
                from ocr_ui import OcrDialog
                if len(files)!=1:raise ValueError('Bitte ein Bild oder PDF wählen.')
                OcrDialog(files[0],self.prefs,self.submit_editor).exec()
            elif action=='AUDIO VERBESSERN':
                from audio_tools_ui import AudioToolsDialog
                AudioToolsDialog(files,self.submit_editor,self.prefs).exec()
            elif action=='UPDATES':self.updates()
            elif action=='AKTIONSSUCHE':self.search_actions(files,kind)
            elif action=='BILDABLÄUFE':
                from workflow_ui import WorkflowDialog
                WorkflowDialog(self.prefs).exec()
            elif action.startswith('flow:'):
                workflow=next((w for w in self.prefs.values.get('workflows',[]) if w['id']==action.split(':',1)[1]),None)
                if not workflow or kind!='Bild':raise ValueError('Bildablauf nicht für diese Auswahl verfügbar.')
                self.submit(ToolJob('Bildablauf',files,{'steps':workflow['steps']},self.prefs.values),workflow['name'])
            elif action=='PDF SEITEN':
                from pdf_pages_ui import PdfPagesDialog
                if len(files)!=1:raise ValueError('Bitte genau ein PDF wählen.')
                PdfPagesDialog(files[0],self.submit_editor).exec()
            elif action=='KOMPRIMIEREN':
                from compression_ui import CompressionDialog
                CompressionDialog(files,kind,self.submit_editor,self.prefs).exec()
            elif action=='MARKIEREN':
                from annotation_ui import AnnotationDialog
                if len(files)!=1:raise ValueError('Bitte ein Bild zum Markieren wählen.')
                AnnotationDialog(files[0],self.submit_editor).exec()
            elif action=='SCHNELLAKTIONEN':
                from compression_ui import QuickActionsDialog
                QuickActionsDialog(self.prefs).exec()
            elif action.startswith('quick:'):
                identifier=action.split(':',1)[1]
                preset=next((p for p in self.prefs.values.get('quick_actions',[]) if p['id']==identifier),None)
                if preset is None or preset['kind']!=kind:raise ValueError('Schnellaktion ist für diese Auswahl nicht verfügbar. Kreis erneut öffnen.')
                self.submit(ToolJob('Komprimieren',files,preset['parameters'],self.prefs.values),preset['name'])
            elif action=='AUFTRÄGE':self.show_tasks()
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
            elif action in ('SCHWARZWEISS','BITMAP','SVG ERWEITERT'):
                from image_processing_ui import ImageProcessingDialog
                target={'SCHWARZWEISS':'PNG','BITMAP':'BITMAP','SVG ERWEITERT':'SVG'}[action]
                if action=='SVG ERWEITERT' and len(files)!=1:raise ValueError('Für die erweiterte SVG-Vorschau bitte genau ein Bild wählen.')
                if len(files)==1:ImageProcessingDialog(files[0],target,self.submit_editor,initial='gray' if action=='SCHWARZWEISS' else None).exec()
                else:self.submit(ToolJob('Bild aufbereiten',files,{'target':target,'processing':{'mode':'gray' if action=='SCHWARZWEISS' else 'binary'}},self.prefs.values),'Bilder aufbereiten')
            elif action=='SVG SCHNELL':self.submit(Conversion(files,'SVG',self.prefs.values),'Bilder → SVG')
            elif action in ('ZUSCHNEIDEN','BILD EDITOR') or (action=='GRÖSSE' and len(files)==1):
                from image_editor import ImageEditor
                ImageEditor(files[0],self.submit_editor).exec()
            elif action in ('90° LINKS','90° RECHTS','180°'):
                angle={'90° LINKS':270,'90° RECHTS':90,'180°':180}[action]
                self.submit(ToolJob('Bild drehen' if kind=='Bild' else 'Video drehen',files,{'angle':angle},self.prefs.values),'Drehen: '+Path(files[0]).name)
            elif action=='GRÖSSE':self.tools(files,'Bildgröße ändern')
            elif action=='PDF TEILEN':self.tools(files,'PDF aufteilen')
            elif action=='PDF VERBINDEN':self.tools(files,'PDFs zusammenfügen')
        except Exception as error:QMessageBox.warning(None,'OrbitDrop · Bearbeiten',str(error))
    def updates(self):
        self.show_dashboard('Updates');self.dashboard.updates_panel.check()
    def install_update(self,installer):
        import subprocess
        from updater import verify_installer
        if sys.platform!='win32':raise OSError('Setup kann nur unter Windows gestartet werden.')
        if self.downloader_window and self.downloader_window.has_pending():raise ValueError('Bitte zuerst die Downloads abschließen oder die Warteschlange abbrechen.')
        from preview_runtime import previews_running
        if self.setup_job or self.jobs or self.tasks.has_running() or self.pool.activeThreadCount() or previews_running():raise ValueError('Noch Hintergrundaufträge aktiv. Bitte kurz warten oder laufende Aufträge beenden.')
        path=verify_installer(installer,self.prefs.root);subprocess.Popen([str(path)]);QTimer.singleShot(100,self.app.quit)
    def auto_update_check(self):
        if self.update_job or not self.prefs.values.get('check_updates',True):return
        from update_ui import UpdateJob
        from updater import latest_release
        self.update_job=UpdateJob(lambda progress:latest_release());self.update_job.signals.done.connect(self.update_checked);self.pool.start(self.update_job)
    def update_checked(self,info,error):
        self.update_job=None;self.last_update=(info,error)
        dashboard=getattr(self,'dashboard',None)
        if dashboard is not None:dashboard.receive_update_result(info,error)
        if info and info['newer']:self.tray.showMessage('OrbitDrop-Update',info['version']+' verfügbar. Dashboard → Updates.')
    def search_actions(self,files=None,kind=None):
        from action_search import ActionSearchDialog
        files=list(files or []);actions=self.wheel.context_actions()
        if self.wheel.link:actions=['download:AUDIO LADEN','download:VIDEO LADEN']+actions
        dialog=ActionSearchDialog(actions,self.prefs,self.wheel.action_titles,files,self.wheel.kind,self.wheel.formats,self.wheel.link)
        if dialog.exec() and dialog.chosen:
            self.wheel.files=dialog.files;self.wheel.kind=dialog.kind;self.wheel.formats=dialog.formats;self.wheel.link=dialog.link;self.wheel.node='direct';self.wheel.select_action(dialog.chosen)
    def record_diagnostics(self,items):
        job=DiagnosticJob(items);self.diagnostic_jobs.add(job)
        job.signals.done.connect(lambda reports,unused:self.diagnostics_ready(job,reports));self.pool.start(job)
    def diagnostics_ready(self,job,reports):
        self.diagnostic_jobs.discard(job)
        try:self.diagnostics.add(reports)
        except OSError as error:self.tray.showMessage('Debugging','Diagnose konnte nicht gespeichert werden: '+str(error))
    def submit_editor(self,action,files,parameters):
        self.submit(ToolJob(action,files,parameters,self.prefs.values),action+': '+Path(files[0]).name)

    def refresh_settings(self):
        self.tray.setToolTip('OrbitDrop · Tastenzugänge pausiert' if self.shortcuts_paused else 'OrbitDrop · '+shortcut_hint(self.prefs.values))
    def settings(self):self.show_dashboard('Einstellungen')
    def show_dashboard(self,page=0):
        if self.dashboard is None:
            from dashboard_ui import Dashboard
            self.dashboard=Dashboard(self)
            area=QApplication.primaryScreen().availableGeometry()
            self.dashboard.resize(min(1140,area.width()-30),min(800,area.height()-45))
        self.dashboard.open_page(page);present(self.dashboard)
        if self.backend_check:self.dashboard.set_checking()

    def quit(self):
        if self.dashboard and self.dashboard._updates_panel is not None:self.dashboard._updates_panel.stopped.set()
        if self.downloader_window:self.downloader_window.stop_for_exit()
        if self.setup_job:self.setup_job.control.cancel()
        if self.tasks.has_running():
            self.tasks.cancel_all();self.show_tasks()
            self.tray.showMessage('Abbruch angefordert','OrbitDrop beendet sich, sobald die laufenden Aufträge gestoppt sind.')
            self.quit_timer=QTimer();self.quit_timer.timeout.connect(lambda:self.app.quit() if not self.tasks.has_running() else None);self.quit_timer.start(200)
        else:self.app.quit()
    def submit(self,job,title,show=True):
        key=self.tasks.add(job,title) if show else self.tasks.add(job,title,show=False)
        self.jobs.add(job)
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
    def media_status(self):
        self.show_dashboard('Einrichtung');self.check_backends(False)
    def check_backends(self,show=False):
        if show:self.show_dashboard('Einrichtung')
        if self.backend_check or self.setup_job:return
        if self.dashboard:self.dashboard.set_checking()
        job=BackendCheck(self.prefs.root);self.backend_check=job
        job.signals.done.connect(self.backends_checked);self.pool.start(job)
    def backends_checked(self,status,missing):
        self.backend_check=None;self.backend_status=status;self.backend_missing=missing
        if self.dashboard:self.dashboard.update_results(status)
    def show_backend_dialog(self):self.show_dashboard('Einrichtung')
    def setup_tool(self,key):
        from setup_tools import TOOLS
        if key not in TOOLS or self.setup_job or self.backend_check:return
        self.show_dashboard('Einrichtung')
        job=SetupJob(key,self.prefs.root);self.setup_job=job;self.dashboard.setup_started(key)
        job.signals.progress.connect(self.dashboard.setup_progress)
        job.signals.done.connect(lambda outputs,errors:self.setup_finished(job,outputs,errors));self.pool.start(job)
    def cancel_setup(self):
        if self.setup_job:self.setup_job.control.cancel();self.dashboard.status.setText('Abbruch angefordert …')
    def setup_finished(self,job,outputs,errors):
        if self.setup_job is not job:return
        self.setup_job=None
        error='Einrichtung abgebrochen. Du kannst sie später erneut starten.' if job.was_cancelled else '\n'.join(errors)
        self.dashboard.setup_finished(error)
        if not error:
            from filetypes import encoders
            from diagnostics import environment
            encoders.cache_clear();environment.cache_clear();self.check_backends(False)


    def file_action(self,files,action):
        if action in ('SHA-256','VERGLEICHEN','ZERTIFIKAT','DATEN PRÜFEN'):
            self.circle_action(files,action,None);return
        try:
            validate_paths(files)
            if action=='UMBENENNEN':
                from rename_ui import RenameDialog
                RenameDialog(files,self.prefs.root).exec()
            elif action=='ABLAGE':
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
            elif action=='ZIP':
                from archive_ui import ArchiveCreateDialog
                ArchiveCreateDialog(files,lambda selected,output,options:self.submit(ArchiveOptionsJob(selected,output,options),'Archiv erstellen'),lambda:self.show_dashboard('Einrichtung')).exec()
            elif action=='ENTPACKEN':
                from archive_ui import ArchiveExtractDialog
                ArchiveExtractDialog(files,lambda selected,output,options:self.submit(ArchiveOptionsJob(selected,output,options,True),'Archiv entpacken')).exec()
            elif action=='VERSCHIEBEN':
                folder=QFileDialog.getExistingDirectory(None,'Zielordner für die Originale wählen')
                if not folder:return
                plans=plan_moves(files,folder)
                job=MoveJob(plans)
                self.submit(job,'Verschieben')
        except Exception as error:
            QMessageBox.warning(None,'OrbitDrop · Dateiaktion',str(error))

    def convert_files(self,files,target):
        from data_formats import kind_for,STRUCTURED
        if len(files)==1 and kind_for(files[0]) in STRUCTURED|{'CSV','TSV'} and target in ('JSON','YAML','TOML','XML','JSONL','CSV','TSV'):
            from data_editor_ui import DataEditor
            DataEditor(files[0],kind_for(files[0]),self.prefs.values.get('output_dir') or None,target=target).exec();return
        if len(files)==1 and kind_for(files[0])=='Zertifikat':
            from admin_tools_ui import AdminToolsDialog
            dialog=AdminToolsDialog(files,'certificate',self.prefs.values.get('output_dir') or None);dialog.cert_target.setCurrentText(target);dialog.exec();return
        title=Path(files[0]).name+f' → {target}'+(f' (+{len(files)-1})' if len(files)>1 else '')
        self.submit(Conversion(files,target,self.prefs.values),title)

    def help(self):self.show_dashboard('Anleitung')

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
    from ui_theme import install_theme
    install_theme(app)
    app.setApplicationName('OrbitDrop')
    app.setQuitOnLastWindowClosed(False)
    if '--self-test' in sys.argv:
        from desktop_smoke import self_test
        sys.exit(self_test(sys.argv[sys.argv.index('--self-test')+1]))
    state_root=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    single=SingleInstance(state_root)
    if not single.acquire():sys.exit(0)
    controller = Controller(app,Preferences(state_root))
    single.activated.connect(lambda:controller.show_dashboard())
    app.aboutToQuit.connect(single.release)
    sys.exit(app.exec())
