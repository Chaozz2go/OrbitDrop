"""All options of the selected category in a large radial menu."""
import math
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QPainterPath,QPen,QColor,QFont,QFontMetrics,QPixmap,QLinearGradient
from circle_menu import direct_color
from radial_style import rounded_sector,surface
from menu_icons import draw_icon

NAMES={'AKTIONSSUCHE':'Aktion suchen','BILDABLÄUFE':'Bildabläufe','PDF SEITEN':'PDF-Seiten','UMBENENNEN':'Umbenennen','KOMPRIMIEREN':'Komprimieren','MARKIEREN':'Schwärzen &\nBeschriften','SCHNELLAKTIONEN':'Schnellaktionen','BILD EDITOR':'Bild bearbeiten','ZURÜCK':'Zurück','ZUSCHNEIDEN':'Zuschneiden','SCHWARZWEISS':'Schwarz\nweiß','GRÖSSE':'Bildgröße','90° LINKS':'90° links','90° RECHTS':'90° rechts','BITMAP':'Bitmap','SVG SCHNELL':'SVG\nSchnell','SVG ERWEITERT':'SVG\nErweitert','PDF VERBINDEN':'PDFs\nverbinden','PDF TEILEN':'PDF\nteilen','LINK LADEN':'Link\neinfügen','EINSTELLUNGEN':'Einstellungen','STANDBILD':'Standbild','AUFTRÄGE':'Aufträge','DEBUGGING':'Debugging','HILFE':'Hilfe','KONVERTER':'Konverter','VERSCHIEBEN':'Verschieben','KOPIEREN':'Kopieren','TERMINAL':'Terminal','EXPLORER':'Explorer','ABLAGE':'Ablage','ENTPACKEN':'Entpacken','SCHNEIDEN':'Schneiden','PFAD':'Pfad','ZIP':'ZIP','AUDIO LADEN':'Audio\nladen','VIDEO LADEN':'Video\nladen'}

def geometry(w):
    size=w.circle_size;center=size/2;outer=center-18;labels=w.labels
    groups=[[key for key in labels if key.startswith(('tool:','app:'))],[key for key in labels if key.startswith(('format:','download:'))],[key for key in labels if key.startswith('edit:')]]
    chunks=[]
    for group in groups:
        if not group:continue
        rings=math.ceil(len(group)/10);count=math.ceil(len(group)/rings)
        chunks.extend(group[i:i+count] for i in range(0,len(group),count))
    width=(outer-90)/max(1,len(chunks));layout=[]
    for ring,group in enumerate(chunks):
        count=len(group);step=360/count;r1=outer-ring*width;r0=r1-width+8
        for index,key in enumerate(group):
            start=index*step-step/2+1.2;span=step-2.4
            path=rounded_sector(QPointF(center,center),r1,r0,start,span)
            angle=math.radians(index*step-90);radius=(r1+r0)/2
            point=QPointF(center+radius*math.cos(angle),center+radius*math.sin(angle))
            layout.append((key,path,point,labels.index(key)))
    return sorted(layout,key=lambda entry:entry[3])


def paint_direct(w):
    p=QPainter(w);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);p.fillRect(w.rect(),Qt.GlobalColor.transparent);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w.paths=[];w.ring_paths=[];center=w.circle_size/2;layout=geometry(w)
    for key,path,point,index in layout:
        w.paths.append(path);accent=QColor(direct_color(key));selected=w.selected==index
        surface(p,path,accent,selected)
        label=key.split(':',1)[-1];text=w.action_titles.get(key,NAMES.get(label,label))
        radius=math.hypot(point.x()-center,point.y()-center)
        count=sum(1 for _,_,other,_ in layout if abs(math.hypot(other.x()-center,other.y()-center)-radius)<2)
        label_width=max(46,min(124,2*radius*math.sin(math.pi/max(2,count))-14))
        p.setPen(QPen(accent if selected else QColor('#adc2d6'),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        draw_icon(p,label,point.x(),point.y()-15,23)
        if key in getattr(getattr(w.controller,'prefs',None),'values',{}).get('favorite_actions',[]):
            p.setFont(QFont('Segoe UI',10));p.setPen(QColor('#ffbe8a'));p.drawText(QRectF(point.x()+15,point.y()-29,20,20),Qt.AlignmentFlag.AlignCenter,'★')
        font=QFont('Segoe UI',10 if label_width>=72 else 8,QFont.Weight.DemiBold);
        longest=max(text.split('\n'),key=len);advance=QFontMetrics(font).horizontalAdvance(longest)
        if advance>label_width:font.setPointSizeF(max(8,font.pointSizeF()*label_width/advance))
        p.setFont(font);p.setPen(QColor('#f3fffb'))
        p.drawText(QRectF(point.x()-label_width/2,point.y()+3,label_width,40),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop|Qt.TextFlag.TextWordWrap,text)
    p.setBrush(QColor('#142131'));p.setPen(QPen(QColor('#43556d'),1));p.drawEllipse(QRectF(center-82,center-82,164,164))
    if w.preview is not None and not w.preview.isNull():
        p.save();clip=QPainterPath();clip.addEllipse(QRectF(center-36,center-56,72,72));p.setClipPath(clip);p.fillRect(clip.boundingRect(),QColor('white'));pixmap=QPixmap.fromImage(w.preview).scaled(72,72,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation);p.drawPixmap(round(center-pixmap.width()/2),round(center-20-pixmap.height()/2),pixmap);p.restore()
    else:
        p.setPen(QColor('#e9f4ff'));p.setFont(QFont('Segoe UI',12,QFont.Weight.Bold));p.drawText(QRectF(center-64,center-36,128,36),Qt.AlignmentFlag.AlignCenter,'OrbitDrop')
    name=Path(w.files[0]).name if len(w.files)==1 else f'{len(w.files)} Dateien' if w.files else 'Link' if w.link else 'Datei ziehen'
    if w.checking:name='Prüfe Dateien …'
    p.setFont(QFont('Segoe UI',8,QFont.Weight.Bold));p.setPen(QColor('#e9f4ff'));p.drawText(QRectF(center-64,center+20,128,22),Qt.AlignmentFlag.AlignCenter,QFontMetrics(p.font()).elidedText(name,Qt.TextElideMode.ElideMiddle,125))
    p.setFont(QFont('Segoe UI',8));p.setPen(QColor('#a8bed6'));p.drawText(QRectF(center-64,center+43,128,20),Qt.AlignmentFlag.AlignCenter,w.action_titles.get(w.labels[w.selected],NAMES.get(w.labels[w.selected].split(':',1)[-1],w.labels[w.selected].split(':',1)[-1])).replace('\n',' ') if w.selected>=0 else 'Aktion wählen')
    y=w.circle_size+3
    p.setPen(QPen(QColor('#344c66'),1));p.setBrush(QColor('#1b2b3f'));p.drawRoundedRect(QRectF(10,y-2,w.circle_size-20,60),12,12)
    p.setFont(QFont('Segoe UI',9))
    for index,(color,text) in enumerate([('#7ed9ba','Konvertieren'),('#ffbe83','Bearbeiten'),('#83baff','Tools')]):
        x=center-180+index*130;p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(color));p.drawEllipse(QPointF(x,y+10),4,4);p.setPen(QColor('#c2d4e6'));p.drawText(QRectF(x+10,y,115,22),Qt.AlignmentFlag.AlignVCenter,text)
    message=w.message+' · Rechtsklick: Suche' if w.selected<0 else ('Gespeicherte Einstellungen: '+w.action_titles[w.labels[w.selected]] if w.labels[w.selected] in w.action_titles else action_hint(w.labels[w.selected]))
    p.drawText(QRectF(10,y+27,w.circle_size-20,23),Qt.AlignmentFlag.AlignCenter,message);p.end()


def action_hint(key):
    category,label=key.split(':',1)
    hints={'KOMPRIMIEREN':'Qualität, Bildgröße und maximale Dateigröße einstellen','MARKIEREN':'Schwärzungen, Pfeile, Text und Rahmen in ein Bild einzeichnen','SCHNELLAKTIONEN':'Eigene Rezepte und Startvorlagen verwalten','ZURÜCK':'Zur Bereichsauswahl · die Datei bleibt ausgewählt','BILD EDITOR':'Farben, Ausschnitt, Drehung und Bildgröße mit Vorschau','ZUSCHNEIDEN':'Ausschnitt im Bild wählen und als neue Datei speichern','BITMAP':'Schwarzweiß-Bitmap mit Vorschau und Schwellwertregler','SVG SCHNELL':'Automatisch vorbereiten und in echte Vektorpfade umwandeln','SVG ERWEITERT':'Konturen, Farben und Glättung mit Vorschau einstellen','SCHWARZWEISS':'Graustufen oder zwei Farben mit Vorschau','SCHNEIDEN':'Abspielen, Schnittmarken setzen und Abschnitte entfernen','KOPIEREN':'Dateien in die Zwischenablage kopieren','VERSCHIEBEN':'Zielordner wählen und Originale dorthin verschieben','TERMINAL':'Terminal im enthaltenden Ordner öffnen','ABLAGE':'Dateien in der schwebenden Ablage parken','ENTPACKEN':'Archiv in einen neuen Unterordner entpacken','EINSTELLUNGEN':'Formate ausblenden und OrbitDrop anpassen'}
    if label in hints:return hints[label]
    if category=='format':return 'Neue Kopie als '+label+' speichern'
    if category=='download':return 'Download-Einstellungen und Speicherort wählen'
    return NAMES.get(label,label).replace('\n',' ')
