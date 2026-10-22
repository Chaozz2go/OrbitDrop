"""Native painted menu matching the approved OrbitDrop concept; no bitmap UI assets."""
import math
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QPainterPath,QPen,QColor,QFont,QLinearGradient,QFontMetrics,QPixmap
from circle_menu import HOME,action_color,MENU_LABELS
from radial_style import rounded_sector,surface

TITLES={'formats':'Konvertieren','edit':'Bearbeiten','tools':'Tools','files':'Tools','more':'Programm','rotate':'Drehen','svg':'Konvertieren  /  SVG'}
CAPTIONS={'SVG SCHNELL':('Schnell','Automatisch vorbereiten und vektorisieren'),'SVG ERWEITERT':('Erweitert','Vorschau, Schwarzweiß und Konturen anpassen'),'SCHWARZWEISS':('Schwarzweiß','Graustufen oder zwei Farben mit Vorschau'),'BITMAP':('Bitmap','Echte 1-Bit-Datei erstellen'),'ZUSCHNEIDEN':('Zuschneiden','Bildausschnitt wählen'),'SCHNEIDEN':('Schneiden','Vorschau und Abschnitte bearbeiten'),'GRÖSSE':('Bildgröße','Breite und Höhe ändern'),'LINK LADEN':('Link einfügen','Audio oder Video herunterladen'),'PROGRAMM':('Programm','Aufträge, Einstellungen und Debugging'),'ZURÜCK':('Zurück',''),'WEITER':('Weitere Optionen','Nächste Seite')}

def icon(p,kind,x,y,size=34):
    p.save();p.translate(x-size/2,y-size/2);p.scale(size/40,size/40);p.setBrush(Qt.BrushStyle.NoBrush)
    if kind in ('KONVERTIEREN','AUDIO LADEN','SVG SCHNELL'):
        p.drawLine(5,12,34,12);p.drawLine(25,4,34,12);p.drawLine(25,20,34,12)
        p.drawLine(35,28,6,28);p.drawLine(15,20,6,28);p.drawLine(15,36,6,28)
    elif kind in ('BEARBEITEN','SVG ERWEITERT'):
        for yy,xx in [(9,14),(20,28),(31,10)]:p.drawLine(3,yy,37,yy);p.drawEllipse(QPointF(xx,yy),3.5,3.5)
    else:
        p.drawRoundedRect(QRectF(3,12,34,23),3,3);p.drawRoundedRect(QRectF(13,5,14,8),2,2);p.drawLine(4,22,36,22);p.drawLine(20,18,20,27)
    p.restore()

def ring(p,w,labels):
    if not labels:return []
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(0,0,0,55));p.drawEllipse(QRectF(20,23,342,342))
    outer,inner=QRectF(24,24,332,332),QRectF(107,107,166,166);paths=[];step=360/len(labels)
    for i,label in enumerate(labels):
        path=rounded_sector(QPointF(190,190),166,83,i*step+2,step-4,12);paths.append(path)
        accent=QColor(action_color('home',label));selected=w.node=='home' and w.selected==i
        surface(p,path,accent,selected)
        angle=math.radians(-90+step/2+i*step);x,y=190+125*math.cos(angle),190+125*math.sin(angle)
        p.setPen(QPen(accent if selected else QColor('#c9d8e8'),2.3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        if label in HOME or label in ('AUDIO LADEN','VIDEO LADEN'):
            icon(p,label,x,y,38)
            if len(labels)!=3 and label in HOME:
                p.setFont(QFont('Segoe UI',9,QFont.Weight.Bold));p.drawText(QRectF(x-65,y+23,130,25),Qt.AlignmentFlag.AlignCenter,{'KONVERTIEREN':'Konvertieren','BEARBEITEN':'Bearbeiten','TOOLS':'Tools'}[label])
        else:
            p.setFont(QFont('Segoe UI',10,QFont.Weight.Bold));p.drawText(QRectF(x-48,y-22,96,44),Qt.AlignmentFlag.AlignCenter,MENU_LABELS.get(label,label))
    return paths

def pill(p,rect,text,color):
    p.setPen(QPen(color,1));p.setBrush(QColor(color.red()//4,color.green()//4,color.blue()//4,245));p.drawRoundedRect(rect,14,14);p.setPen(QColor('#f4f8ff'));p.setFont(QFont('Segoe UI',10,QFont.Weight.DemiBold));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,text)

def paint_wheel(w):
    p=QPainter(w);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);p.fillRect(w.rect(),Qt.GlobalColor.transparent);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver);p.setRenderHint(QPainter.RenderHint.Antialiasing);w.paths=[]
    from menu_visibility import visible_actions
    roots=w.labels if w.node=='home' else visible_actions(list(HOME),getattr(getattr(w.controller,'prefs',None),'values',{}))
    w.ring_paths=ring(p,w,roots)
    if w.node=='home':w.paths=w.ring_paths[:]
    if len(roots)==3 and all(label in HOME for label in roots):
        pill(p,QRectF(278,71,138,32),'Konvertieren',QColor('#7ed9ba'));pill(p,QRectF(120,332,145,32),'Bearbeiten',QColor('#ffbe83'));pill(p,QRectF(0,71,93,32),'Tools',QColor('#83baff'))
        if w.node=='home':
            # The labels are also hit targets; the wedges remain the larger targets.
            for index,rect in enumerate([QRectF(278,71,138,32),QRectF(120,332,145,32),QRectF(0,71,93,32)]):
                label_path=QPainterPath();label_path.addRoundedRect(rect,14,14);w.paths[index]=w.paths[index].united(label_path)
    p.setPen(QPen(QColor('#3c4759'),1));p.setBrush(QColor('#141c29'));p.drawEllipse(QRectF(112,112,156,156))
    if w.preview is not None and not w.preview.isNull():
        p.save();clip=QPainterPath();clip.addEllipse(QRectF(145,124,90,90));p.setClipPath(clip);p.fillRect(QRectF(145,124,90,90),QColor('white'))
        pixmap=QPixmap.fromImage(w.preview).scaled(90,90,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation);p.drawPixmap(190-pixmap.width()//2,169-pixmap.height()//2,pixmap);p.restore()
        title=Path(w.files[0]).name if len(w.files)==1 else f'{len(w.files)} Dateien'
        p.setPen(QColor('#edf4ff'));p.setFont(QFont('Segoe UI',9,QFont.Weight.Bold));p.drawText(QRectF(118,220,144,22),Qt.AlignmentFlag.AlignCenter,QFontMetrics(p.font()).elidedText(title,Qt.TextElideMode.ElideMiddle,140))
        p.setFont(QFont('Segoe UI',8));p.setPen(QColor('#b6c4d6'));p.drawText(QRectF(118,242,144,18),Qt.AlignmentFlag.AlignCenter,w.kind+' · '+Path(w.files[0]).suffix[1:].upper())
    else:
        p.setPen(QColor('#edf4ff'));p.setFont(QFont('Segoe UI',13,QFont.Weight.Bold));p.drawText(QRectF(116,153,148,32),Qt.AlignmentFlag.AlignCenter,'OrbitDrop')
        title='Bitte kurz halten …' if w.checking else Path(w.files[0]).name if len(w.files)==1 else f'{len(w.files)} Dateien' if w.files else 'Link erkannt' if w.link else 'Datei hineinziehen'
        p.setFont(QFont('Segoe UI',9));p.setPen(QColor('#b6c4d6'));p.drawText(QRectF(116,194,148,42),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,QFontMetrics(p.font()).elidedText(title,Qt.TextElideMode.ElideMiddle,145))
    p.end()


def home_paths(labels):
    paths=[]
    if not labels:return paths
    step=360/len(labels)
    for index,label in enumerate(labels):
        path=rounded_sector(QPointF(190,190),166,83,index*step+2,step-4,12)
        if len(labels)==3 and all(key in HOME for key in labels):
            rect=[QRectF(278,71,138,32),QRectF(120,332,145,32),QRectF(0,71,93,32)][index]
            extra=QPainterPath();extra.addRoundedRect(rect,14,14);path=path.united(extra)
        paths.append(path)
    return paths
