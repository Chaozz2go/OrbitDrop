"""One visual language for every OrbitDrop-owned window."""
import sys,gc
from PySide6.QtCore import Qt,QObject,QEvent,QTimer,QSize,QRectF,QPointF
from PySide6.QtGui import QColor,QPalette,QPainter,QPen,QPainterPath,QPixmap,QIcon,QBrush
from PySide6.QtWidgets import QApplication,QPushButton,QFrame,QHBoxLayout

BACKGROUND='#142131';SURFACE='#1b2b3f';CANVAS='#0e1928';BORDER='#344c66';TEXT='#eaf2fc';MUTED='#a3b7ce';MINT='#8ce8c9';APRICOT='#ffbe8a'
STYLE='''
QWidget{background:#142131;color:#eaf2fc;font-family:"Segoe UI";font-size:10pt;}
QDialog{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1b2c40,stop:1 #121e2d);}
QLabel{background:transparent;border:0;}
QLabel#previewSurface{background:#0e1928;color:#a3b7ce;border:1px solid #344c66;border-radius:12px;padding:4px;}
QLabel#editorTitle{font-size:19pt;font-weight:600;color:#f1f6ff;}
QLabel#editorSubtitle{color:#a3b7ce;font-size:9pt;}
QLabel#timeReadout{font-family:Consolas;font-size:11pt;color:#eaf2fc;}
QWidget#editorControls,QFrame#toolbar{background:#1b2b3f;border:1px solid #344c66;border-radius:12px;}
QFrame#toolbar{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #22364d,stop:1 #19293c);}
QTreeWidget,QListWidget,QTextEdit,QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox{
 background:#152438;color:#eaf2fc;border:1px solid #354e69;border-radius:8px;padding:7px;selection-background-color:#53483e;selection-color:#fff2e7;}
QTreeWidget,QListWidget,QTextEdit{alternate-background-color:#1b2c42;outline:0;}
QListWidget::item,QTreeWidget::item{padding:7px;border:1px solid transparent;border-radius:6px;}
QListWidget::item:hover,QTreeWidget::item:hover{background:#263c53;}
QListWidget::item:selected,QTreeWidget::item:selected{background:#4a4039;border:1px solid #ffbe8a;color:#fff2e7;}
QHeaderView::section{background:#1c2e44;color:#a3b7ce;padding:9px;border:0;border-bottom:1px solid #344c66;}
QPushButton,QToolButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #263b53,stop:1 #1c2d42);color:#e2edf9;border:1px solid #3c5775;border-radius:8px;padding:9px 12px;font-weight:500;}
QPushButton:hover,QToolButton:hover{background:#304c67;border-color:#7598b9;}
QPushButton:pressed,QToolButton:pressed,QPushButton:checked{background:#354f66;border-color:#ffbe8a;}
QPushButton:focus,QToolButton:focus{border-color:#ffbe8a;}
QPushButton#primaryAction{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #a0f0d6,stop:1 #7ddcbb);color:#102e27;border:1px solid #b0f5df;font-weight:600;}
QPushButton#primaryAction:hover{background:#b3f7e1;}
QPushButton#primaryAction:pressed{background:#6bcbac;}
QPushButton#originalPreview:pressed{background:#8ce8c9;color:#102e27;}
QPushButton:disabled,QPushButton#primaryAction:disabled{background:#203247;color:#718aa3;border-color:#30475f;}
QProgressBar{background:#152438;border:1px solid #344c66;border-radius:7px;text-align:center;min-height:16px;}
QProgressBar::chunk{background:#7ddcbb;border-radius:6px;}
QSlider::groove:horizontal{height:6px;background:#30465d;border-radius:3px;}
QSlider::sub-page:horizontal{background:#8ce8c9;border-radius:3px;}
QSlider::handle:horizontal{width:16px;height:16px;margin:-6px 0;background:#b5f7df;border:1px solid #7bc9ae;border-radius:8px;}
QSlider::sub-page:horizontal:disabled{background:#415266;}QSlider::handle:horizontal:disabled{background:#65768a;border-color:#415266;}
QCheckBox{spacing:8px;background:transparent;}
QCheckBox::indicator{width:17px;height:17px;border:1px solid #58748e;border-radius:4px;background:#152438;}
QCheckBox::indicator:checked{background:#8ce8c9;border-color:#b8f7e3;image:none;}
QComboBox QAbstractItemView{background:#1b2b3f;color:#eaf2fc;selection-background-color:#4a4039;}
QScrollArea{background:transparent;border:0;}
QScrollBar:vertical{background:#152438;width:10px;margin:2px;border-radius:5px;}
QScrollBar::handle:vertical{background:#455f78;min-height:26px;border-radius:4px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QScrollBar:horizontal{background:#152438;height:10px;margin:2px;border-radius:5px;}
QScrollBar::handle:horizontal{background:#455f78;min-width:26px;border-radius:4px;}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;}
QScrollBar::add-page,QScrollBar::sub-page{background:transparent;}
QSplitter::handle{background:#24384f;width:5px;height:5px;}
QMenu{background:#1b2b3f;color:#eaf2fc;border:1px solid #405e7b;border-radius:10px;padding:6px;}
QMenu::item{padding:9px 20px;border-radius:6px;}QMenu::item:selected{background:#344a5c;color:#fff2e7;}
QMenu::separator{height:1px;background:#344c66;margin:5px;}
QToolTip{background:#23384f;color:#eaf2fc;border:1px solid #577692;padding:6px;}
QTabWidget::pane{background:#17273b;border:1px solid #344c66;border-radius:10px;}
QTabBar::tab{background:#1c2d42;color:#a3b7ce;padding:10px 16px;border-bottom:2px solid transparent;}
QTabBar::tab:selected{background:#2a4056;color:#f5f8ff;border-bottom:2px solid #8ce8c9;}
'''


def icon(kind,color=TEXT,size=18):
    pixmap=QPixmap(size,size);pixmap.fill(Qt.GlobalColor.transparent);p=QPainter(pixmap);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.scale(size/24,size/24);p.setPen(QPen(QColor(color),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin));p.setBrush(Qt.BrushStyle.NoBrush)
    def line(a,b,c,d):p.drawLine(QPointF(a,b),QPointF(c,d))
    if kind=='play':
        path=QPainterPath(QPointF(7,4));path.lineTo(20,12);path.lineTo(7,20);path.closeSubpath();p.fillPath(path,QColor(color))
    elif kind in ('previous','next'):
        if kind=='previous':p.translate(24,0);p.scale(-1,1)
        path=QPainterPath(QPointF(5,5));path.lineTo(15,12);path.lineTo(5,19);path.closeSubpath();p.drawPath(path);line(19,5,19,19)
    elif kind=='cut':
        p.drawEllipse(QRectF(2,15,5,5));p.drawEllipse(QRectF(17,15,5,5));line(5,15,19,3);line(19,15,5,3)
    elif kind=='delete':
        line(4,6,20,6);line(9,3,15,3);path=QPainterPath(QPointF(6,6));path.lineTo(7,21);path.lineTo(17,21);path.lineTo(18,6);p.drawPath(path);line(10,10,10,17);line(14,10,14,17)
    elif kind in ('undo','reset','rotate_left','rotate_right'):
        if kind=='rotate_right':p.translate(24,0);p.scale(-1,1)
        p.drawArc(QRectF(5,5,15,15),-70*16,280*16);line(4,5,4,11);line(4,11,10,11)
    elif kind in ('save','download'):
        line(12,3,12,15);line(7,10,12,15);line(12,15,17,10);line(4,14,4,21);line(4,21,20,21);line(20,21,20,14)
    elif kind=='folder':
        path=QPainterPath(QPointF(2,6));path.lineTo(10,6);path.lineTo(13,9);path.lineTo(22,9);path.lineTo(22,21);path.lineTo(2,21);path.closeSubpath();p.drawPath(path)
    elif kind=='compare':
        p.drawRoundedRect(QRectF(3,4,18,16),3,3);line(12,2,12,22)
    else:
        p.drawRoundedRect(QRectF(3,3,18,18),3,3);line(7,8,17,8);line(7,13,17,13);line(7,17,13,17)
    p.end();return QIcon(pixmap)


def action_button(text,kind=None,primary=False,tooltip=None):
    button=QPushButton(text)
    if primary:button.setObjectName('primaryAction')
    if kind:button.setIcon(icon(kind,'#102e27' if primary else TEXT));button.setIconSize(QSize(18,18))
    if tooltip:button.setToolTip(tooltip)
    return button


def toolbar():
    frame=QFrame();frame.setObjectName('toolbar');layout=QHBoxLayout(frame);layout.setContentsMargins(9,7,9,7);layout.setSpacing(7);return frame,layout


def paint_excluded(p,rect):
    p.fillRect(rect,QColor(12,18,29,205));p.fillRect(rect,QBrush(QColor(192,99,115,55),Qt.BrushStyle.BDiagPattern))


def native_frame(window):
    if sys.platform!='win32':return
    # DWM rounding can add a rectangular outline around a per-pixel-alpha
    # overlay. Native frame styling belongs only to decorated app windows.
    try:
        if window.windowFlags() & Qt.WindowType.FramelessWindowHint or window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):return
        import ctypes
        dwm=ctypes.WinDLL('dwmapi');handle=int(window.winId());enabled=ctypes.c_int(1)
        if dwm.DwmSetWindowAttribute(ctypes.c_void_p(handle),20,ctypes.byref(enabled),4):dwm.DwmSetWindowAttribute(ctypes.c_void_p(handle),19,ctypes.byref(enabled),4)
        rounded=ctypes.c_int(2);dwm.DwmSetWindowAttribute(ctypes.c_void_p(handle),33,ctypes.byref(rounded),4)
    except (OSError,RuntimeError,AttributeError):pass

class ThemeFilter(QObject):
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Show and hasattr(obj,'isWindow') and obj.isWindow():QTimer.singleShot(0,lambda:native_frame(obj))
        return False


class GuiGarbageCollector(QObject):
    """Collect Python/Qt reference cycles on the GUI thread, never a worker.

    Refcounting remains active. Only cyclic collection is moved to the event
    loop, since a worker can otherwise collect a closed widget and its signal
    closures while Shiboken is processing deferred native deletions.
    """
    def __init__(self,app):
        super().__init__(app);self.was_enabled=gc.isenabled();gc.disable()
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.collect_if_needed);self.timer.start()
        if self.was_enabled:app.destroyed.connect(lambda *_:gc.enable())
    def collect_if_needed(self):
        if gc.get_count()[0]>=gc.get_threshold()[0]:gc.collect()


def ensure_gui_lifetimes():
    app=QApplication.instance()
    if app is not None and not hasattr(app,'_orbit_gc'):app._orbit_gc=GuiGarbageCollector(app)


def install_theme(app):
    ensure_gui_lifetimes()
    app.setStyle('Fusion');palette=QPalette()
    for role,color in [(QPalette.ColorRole.Window,BACKGROUND),(QPalette.ColorRole.WindowText,TEXT),(QPalette.ColorRole.Base,CANVAS),(QPalette.ColorRole.AlternateBase,SURFACE),(QPalette.ColorRole.Text,TEXT),(QPalette.ColorRole.Button,SURFACE),(QPalette.ColorRole.ButtonText,TEXT),(QPalette.ColorRole.Highlight,'#56483c'),(QPalette.ColorRole.HighlightedText,'#fff3e8'),(QPalette.ColorRole.ToolTipBase,SURFACE),(QPalette.ColorRole.ToolTipText,TEXT)]:palette.setColor(role,QColor(color))
    app.setPalette(palette);app.setStyleSheet(STYLE);app._orbit_theme_filter=ThemeFilter(app);app.installEventFilter(app._orbit_theme_filter)
