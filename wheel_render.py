"""Native painted menu matching the approved OrbitDrop concept; no bitmap UI assets."""
import math
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QPainterPath,QPen,QColor,QFont,QLinearGradient,QFontMetrics,QPixmap
from circle_menu import HOME,action_color,MENU_LABELS

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
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(0,0,0,55));p.drawEllipse(QRectF(20,23,342,342))
    outer,inner=QRectF(24,24,332,332),QRectF(107,107,166,166);paths=[];step=360/len(labels)
    for i,label in enumerate(labels):
        start=88-i*step;path=QPainterPath();path.arcMoveTo(outer,start);path.arcTo(outer,start,-(step-4));end=math.radians(start-(step-4));path.lineTo(190+83*math.cos(end),190-83*math.sin(end));path.arcTo(inner,start-(step-4),step-4);path.closeSubpath();paths.append(path)
        accent=QColor(action_color('home',label));selected=w.node=='home' and w.selected==i
        gradient=QLinearGradient(30,24,330,350);gradient.setColorAt(0,accent.lighter(128));gradient.setColorAt(1,accent.darker(122 if selected else 145));p.setBrush(gradient);p.setPen(QPen(accent.lighter(130),1.3));p.drawPath(path)
        angle=math.radians(-90+step/2+i*step);x,y=190+125*math.cos(angle),190+125*math.sin(angle)
        p.setPen(QPen(QColor('#f5fffa'),2.3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        if label in HOME or label in ('AUDIO LADEN','VIDEO LADEN'):icon(p,label,x,y,38)
        else:
            p.setFont(QFont('Segoe UI',10,QFont.Weight.Bold));p.drawText(QRectF(x-48,y-22,96,44),Qt.AlignmentFlag.AlignCenter,MENU_LABELS.get(label,label))
    return paths

def pill(p,rect,text,color):
    p.setPen(QPen(color,1));p.setBrush(QColor(color.red()//4,color.green()//4,color.blue()//4,245));p.drawRoundedRect(rect,14,14);p.setPen(QColor('#f4f8ff'));p.setFont(QFont('Segoe UI',10,QFont.Weight.DemiBold));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,text)

def paint_wheel(w):
    p=QPainter(w);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);p.fillRect(w.rect(),Qt.GlobalColor.transparent);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver);p.setRenderHint(QPainter.RenderHint.Antialiasing);w.paths=[]
    roots=w.labels if w.node=='home' and w.labels else list(HOME);roots=roots if w.node=='home' else list(HOME)
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
    p.setFont(QFont('Segoe UI',9));p.setPen(QColor('#c4d0e1'));p.drawText(QRectF(5,374,410,42),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,'Datei prüfen …' if w.checking else 'Bereich wählen' if w.node=='home' else TITLES.get(w.node,'OrbitDrop'))
    pill(p,QRectF(96,416,190,27),'Esc  ·  Menü schließen',QColor('#526178'))
    if w.node!='home':
        rect=QRectF(428,20,434,478);p.setPen(QPen(QColor('#39475b'),1));p.setBrush(QColor('#151e2c'));p.drawRoundedRect(rect,18,18)
        accent=QColor(action_color(w.node,''));p.setPen(QPen(accent,4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.drawLine(430,38,430,97)
        p.setPen(accent);p.setFont(QFont('Segoe UI',11,QFont.Weight.DemiBold));p.drawText(QRectF(448,35,390,25),TITLES.get(w.node,'OrbitDrop'))
        p.setPen(QColor('#f3f7ff'));p.setFont(QFont('Segoe UI',14,QFont.Weight.Bold));p.drawText(QRectF(448,66,395,32),'Wie möchtest du starten?' if w.node=='svg' else 'Was möchtest du machen?')
        y=112
        for i,label in enumerate(w.labels):
            large=w.node=='svg' and label!='ZURÜCK';height=100 if large else 45
            box=QRectF(448,y,394,height);path=QPainterPath();path.addRoundedRect(box,10,10);w.paths.append(path)
            gradient=QLinearGradient(box.topLeft(),box.bottomRight());gradient.setColorAt(0,accent.darker(320 if i==w.selected else 550));gradient.setColorAt(1,QColor('#1b2635'));p.setBrush(gradient);p.setPen(QPen(accent if i==w.selected else QColor('#3b4d61'),1.4));p.drawPath(path)
            title,subtitle=CAPTIONS.get(label,(label.title() if len(label)>5 else label,''))
            textx=box.left()+15
            if large:
                p.setPen(QPen(accent,2.1,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));icon(p,label,box.left()+32,box.center().y(),30);textx+=45
            p.setPen(QColor('#f3f7ff'));p.setFont(QFont('Segoe UI',13 if large else 10,QFont.Weight.DemiBold));p.drawText(QRectF(textx,y+12 if large else y+4,box.right()-textx-12,28),Qt.AlignmentFlag.AlignVCenter,title)
            if subtitle:
                p.setFont(QFont('Segoe UI',9 if large else 8));p.setPen(QColor('#acbdcf'));p.drawText(QRectF(textx,y+43 if large else y+24,box.right()-textx-12,45 if large else 18),Qt.TextFlag.TextWordWrap,subtitle)
            y+=height+8
        p.setPen(QColor('#acbdcf'));p.setFont(QFont('Segoe UI',9));file=Path(w.files[0]).name if len(w.files)==1 else f'{len(w.files)} Dateien' if w.files else 'Link' if w.link else 'OrbitDrop'
        if len(w.all_actions)>6:file+=f' · Seite {w.page+1}/{math.ceil(len(w.all_actions)/5)}'
        p.drawText(QRectF(448,463,394,23),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(p.font()).elidedText(file,Qt.TextElideMode.ElideMiddle,390))
    p.end()
