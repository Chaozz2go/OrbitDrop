"""All options of the selected category in a large radial menu."""
import math
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QPainterPath,QPen,QColor,QFont,QFontMetrics,QPixmap,QLinearGradient
from circle_menu import direct_color

NAMES={'ZURÜCK':'Zurück','ZUSCHNEIDEN':'Zuschneiden','SCHWARZWEISS':'Schwarz\nweiß','GRÖSSE':'Bildgröße','90° LINKS':'90° links','90° RECHTS':'90° rechts','BITMAP':'Bitmap','SVG SCHNELL':'SVG\nSchnell','SVG ERWEITERT':'SVG\nErweitert','PDF VERBINDEN':'PDFs\nverbinden','PDF TEILEN':'PDF\nteilen','LINK LADEN':'Link\neinfügen','EINSTELLUNGEN':'Einstellungen','STANDBILD':'Standbild','AUFTRÄGE':'Aufträge','DEBUGGING':'Debugging','HILFE':'Hilfe','KONVERTER':'Konverter','VERSCHIEBEN':'Verschieben','KOPIEREN':'Kopieren','TERMINAL':'Terminal','EXPLORER':'Explorer','ABLAGE':'Ablage','ENTPACKEN':'Entpacken','SCHNEIDEN':'Schneiden','PFAD':'Pfad','ZIP':'ZIP','AUDIO LADEN':'Audio\nladen','VIDEO LADEN':'Video\nladen'}

def geometry(w):
    size=w.circle_size;center=size/2;outer=center-15;labels=w.labels
    groups=[[key for key in labels if key.startswith(('tool:','app:'))],[key for key in labels if key.startswith(('format:','download:'))],[key for key in labels if key.startswith('edit:')]]
    groups=[group for group in groups if group];rings=max(1,len(groups));width=(outer-76)/rings;layout=[]
    for ring,group in enumerate(groups):
        count=len(group)
        for index,key in enumerate(group):
            step=360/max(1,count);start=90-index*step-1;end=start-step+2;r1=outer-ring*width;r0=r1-width+5
            out=QRectF(center-r1,center-r1,r1*2,r1*2);inside=QRectF(center-r0,center-r0,r0*2,r0*2)
            path=QPainterPath();path.arcMoveTo(out,start);path.arcTo(out,start,-step+2);angle=math.radians(end);path.lineTo(center+r0*math.cos(angle),center-r0*math.sin(angle));path.arcTo(inside,end,step-2);path.closeSubpath()
            angle=math.radians(90-(index+.5)*step);radius=(r1+r0)/2;point=QPointF(center+radius*math.cos(angle),center-radius*math.sin(angle))
            layout.append((key,path,point,labels.index(key)))
    return sorted(layout,key=lambda entry:entry[3])


def paint_direct(w):
    p=QPainter(w);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);p.fillRect(w.rect(),Qt.GlobalColor.transparent);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w.paths=[];w.ring_paths=[];center=w.circle_size/2
    for key,path,point,index in geometry(w):
        w.paths.append(path);accent=QColor(direct_color(key));selected=w.selected==index
        gradient=QLinearGradient(path.boundingRect().topLeft(),path.boundingRect().bottomRight());gradient.setColorAt(0,accent.lighter(112 if selected else 100));gradient.setColorAt(1,accent.darker(125 if selected else 240));p.setBrush(gradient);p.setPen(QPen(accent.lighter(110),1.2));p.drawPath(path)
        label=key.split(':',1)[-1];text=NAMES.get(label,label);font=QFont('Segoe UI',9 if len(text.replace('\n',''))<14 else 8,QFont.Weight.DemiBold);p.setFont(font);p.setPen(QColor('#f3fffb'))
        radius=math.hypot(point.x()-center,point.y()-center);label_width=max(60,min(90,2*(radius-72)-8));line=max(text.split('\n'),key=len);advance=QFontMetrics(font).horizontalAdvance(line)
        if advance>label_width:font.setPointSizeF(max(7.5,font.pointSizeF()*label_width/advance));p.setFont(font)
        p.drawText(QRectF(point.x()-label_width/2,point.y()-28,label_width,56),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,text)
    p.setBrush(QColor('#141e2c'));p.setPen(QPen(QColor('#43556d'),1));p.drawEllipse(QRectF(center-70,center-70,140,140))
    if w.preview is not None and not w.preview.isNull():
        p.save();clip=QPainterPath();clip.addEllipse(QRectF(center-36,center-56,72,72));p.setClipPath(clip);p.fillRect(clip.boundingRect(),QColor('white'));pixmap=QPixmap.fromImage(w.preview).scaled(72,72,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation);p.drawPixmap(round(center-pixmap.width()/2),round(center-20-pixmap.height()/2),pixmap);p.restore()
    else:
        p.setPen(QColor('#e9f4ff'));p.setFont(QFont('Segoe UI',12,QFont.Weight.Bold));p.drawText(QRectF(center-64,center-36,128,36),Qt.AlignmentFlag.AlignCenter,'OrbitDrop')
    name=Path(w.files[0]).name if len(w.files)==1 else f'{len(w.files)} Dateien' if w.files else 'Link' if w.link else 'Datei ziehen'
    if w.checking:name='Prüfe Dateien …'
    p.setFont(QFont('Segoe UI',8,QFont.Weight.Bold));p.setPen(QColor('#e9f4ff'));p.drawText(QRectF(center-64,center+20,128,22),Qt.AlignmentFlag.AlignCenter,QFontMetrics(p.font()).elidedText(name,Qt.TextElideMode.ElideMiddle,125))
    p.setFont(QFont('Segoe UI',8));p.setPen(QColor('#a8bed6'));p.drawText(QRectF(center-64,center+43,128,20),Qt.AlignmentFlag.AlignCenter,'Loslassen' if w.selected>=0 else 'Aktion wählen')
    y=w.circle_size+3
    p.setPen(QPen(QColor('#34475d'),1));p.setBrush(QColor('#151e2b'));p.drawRoundedRect(QRectF(10,y-2,w.circle_size-20,60),12,12)
    p.setFont(QFont('Segoe UI',9))
    for index,(color,text) in enumerate([('#7ed9ba','Konvertieren'),('#ffbe83','Bearbeiten'),('#83baff','Tools')]):
        x=center-180+index*130;p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(color));p.drawEllipse(QPointF(x,y+10),4,4);p.setPen(QColor('#c2d4e6'));p.drawText(QRectF(x+10,y,115,22),Qt.AlignmentFlag.AlignVCenter,text)
    message=w.message+' · Esc: schließen' if w.selected<0 else w.labels[w.selected].split(':',1)[-1].replace('SVG ','SVG · ')
    p.drawText(QRectF(10,y+27,w.circle_size-20,23),Qt.AlignmentFlag.AlignCenter,message);p.end()
