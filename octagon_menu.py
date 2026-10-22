"""Equal regular octagons on fixed concentric slots, painted natively with Qt."""
import math
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from circle_menu import HOME, action_color, direct_color
from menu_icons import draw_icon

MORE = 'nav:MEHR'
PREVIOUS = 'nav:VORHERIGE'
NEXT = 'nav:NÄCHSTE'
NAVIGATION = frozenset((MORE, PREVIOUS, NEXT))
INNER_RADIUS = 1.36
OUTER_RADIUS = 2.82
FOOTER_HEIGHT = 72


def octagon(center, size):
    half = size / 2
    cut = size / (2 + math.sqrt(2))
    points = [(-half+cut,-half),(half-cut,-half),(half,-half+cut),(half,half-cut),
              (half-cut,half),(-half+cut,half),(-half,half-cut),(-half,-half+cut)]
    path = QPainterPath()
    for i, (x,y) in enumerate(points):
        point = QPointF(center.x()+x, center.y()+y)
        if i: path.lineTo(point)
        else: path.moveTo(point)
    path.closeSubpath()
    return path


def stage_metrics(area):
    available = max(120, min(area.width()-20, area.height()-FOOTER_HEIGHT-20))
    outer_tile = math.floor((available-24)/(2*OUTER_RADIUS+1))
    outer_supported = outer_tile >= 72
    radius = OUTER_RADIUS if outer_supported else INNER_RADIUS
    tile = max(32, min(128, math.floor((available-24)/(2*radius+1))))
    stage = math.ceil((2*radius+1)*tile+24)
    return tile, stage, outer_supported


def preferred(w):
    if w.link:
        return ['download:AUDIO LADEN','download:VIDEO LADEN','app:AUFTRÄGE','app:LINK LADEN','app:HILFE']
    if w.mode == 'edit':
        names = {'Bild':['BILD EDITOR','ZUSCHNEIDEN','90° RECHTS','GRÖSSE','KOMPRIMIEREN'],
                 'Video':['SCHNEIDEN','90° RECHTS','KOMPRIMIEREN','90° LINKS','180°'],
                 'Audio':['SCHNEIDEN','AUDIO VERBESSERN','KOMPRIMIEREN'],
                 'PDF':['PDF SEITEN','PDF TEILEN','TEXT ERKENNEN','PDF VERBINDEN','KOMPRIMIEREN']}.get(w.kind,[])
        return ['edit:'+name for name in names]
    if w.mode == 'convert':
        names = {'Bild':['PNG','JPG','WEBP','PDF','SVG SCHNELL'],
                 'SVG':['PNG','JPG','WEBP','PDF','BMP'],
                 'Video':['MP4','WEBM','MOV','MP3','GIF'],
                 'Audio':['MP3','WAV','FLAC','M4A','OPUS'],
                 'PDF':['DOCX','PNG','TXT','PPTX','XLSX']}.get(w.kind,['PDF','DOCX','TXT','MD','EPUB'])
        return ['format:'+name for name in names]
    if w.mode == 'files':
        return (['tool:KOPIEREN','tool:VERSCHIEBEN','tool:ZIP','tool:ABLAGE','tool:TERMINAL'] if w.files
                else ['app:LINK LADEN','app:AUFTRÄGE','app:AKTIONSSUCHE','app:HILFE','app:EINSTELLUNGEN'])
    return []


def plan(w, actions):
    actions = list(dict.fromkeys(actions))
    if w.node == 'home':
        w.secondary_actions=[];w.secondary_pages=1
        positions = {key: i*2 for i,key in enumerate(HOME)}
        return [(key,0,positions.get(key,i%6)) for i,key in enumerate(actions)]
    back = next((key for key in actions if key.endswith(':ZURÜCK')), None)
    usable = [key for key in actions if key != back]
    primary = preferred(w)
    slots = {i:key for i,key in enumerate(primary[:5]) if key in usable}
    if not slots:
        slots = dict(enumerate(usable[:5]))
    favorites = getattr(getattr(w.controller,'prefs',None),'values',{}).get('favorite_actions',[])
    favorite = next((key for key in favorites if key in usable and key not in [slots.get(i) for i in range(4)]), None)
    if favorite: slots[4] = favorite
    if back: slots[4] = back
    inner = [(key,0,slot) for slot,key in sorted(slots.items())]
    secondary = [key for key in actions if key not in slots.values()]
    w.secondary_actions = secondary
    w.secondary_pages = max(1, math.ceil(len(secondary)/10)) if len(secondary)>12 else 1
    w.outer_page %= w.secondary_pages
    if secondary:
        inner.append((MORE,0,5))
    if w.menu_expanded and w.outer_supported:
        if len(secondary)<=12:
            inner.extend((key,1,round(i*12/len(secondary))) for i,key in enumerate(secondary))
        else:
            page = secondary[w.outer_page*10:(w.outer_page+1)*10]
            inner.extend((key,1,i) for i,key in enumerate(page))
            inner.extend([(PREVIOUS,1,10),(NEXT,1,11)])
    return inner


def configure(w, area):
    w.tile_size,w.circle_size,w.outer_supported = stage_metrics(area)
    if not w.outer_supported:w.menu_expanded=False
    w._octagon_slots = plan(w,w.all_actions)
    w.labels = [entry[0] for entry in w._octagon_slots]
    w.resize(w.circle_size,w.circle_size+FOOTER_HEIGHT)
    w.move(max(area.left(),min(w.x(),area.right()-w.width()+1)),
           max(area.top(),min(w.y(),area.bottom()-w.height()+1)))
    w.paths = [entry[1] for entry in geometry(w)]
    w.ring_paths = []


def geometry(w):
    assignments = getattr(w,'_octagon_slots',[])
    if [entry[0] for entry in assignments] != w.labels:
        assignments = [(key,0,i%6) for i,key in enumerate(w.labels)]
    size = getattr(w,'tile_size',112)
    center = w.circle_size/2
    result = []
    for index,(key,ring,slot) in enumerate(assignments):
        radius = size*(OUTER_RADIUS if ring else INNER_RADIUS)
        angle = math.radians(-90+slot*(30 if ring else 60))
        point = QPointF(center+radius*math.cos(angle),center+radius*math.sin(angle))
        result.append((key,octagon(point,size),point,index))
    return result


def title(w,key):
    from direct_wheel import NAMES
    if key == MORE:
        return 'Weniger' if w.menu_expanded else 'Weitere'
    if key == PREVIOUS:return 'Vorige\nSeite'
    if key == NEXT:return 'Nächste\nSeite'
    if key in HOME:return {'KONVERTIEREN':'Konvertieren','BEARBEITEN':'Bearbeiten','TOOLS':'Tools'}[key]
    label = key.split(':',1)[-1]
    return w.action_titles.get(key,NAMES.get(label,label))


def accent(w,key):
    if key in HOME:return QColor(action_color('home',key))
    if key in NAVIGATION:
        return QColor('#7ed9ba' if w.mode=='convert' else '#ffbe83' if w.mode=='edit' else '#83baff')
    return QColor(direct_color(key))


def paint_surface(p,path,color,selected=False,active=False):
    gradient=QLinearGradient(path.boundingRect().topLeft(),path.boundingRect().bottomRight())
    gradient.setColorAt(0,color.lighter(110) if selected else QColor('#263b53'))
    gradient.setColorAt(1,color.darker(115) if selected else QColor('#1b2b3f'))
    p.setBrush(gradient);p.setPen(QPen(color if selected or active else QColor('#405b77'),2 if selected or active else 1))
    p.drawPath(path)


def tile_icon(p,key,point,size):
    label=key.split(':',1)[-1]
    if key==MORE:
        for x in (-7,0,7):p.drawEllipse(QPointF(point.x()+x,point.y()),1.6,1.6)
    elif key in (PREVIOUS,NEXT):
        p.save();p.translate(point)
        if key==NEXT:p.rotate(180)
        draw_icon(p,'ZURÜCK',0,0,size);p.restore()
    elif key in HOME:
        from wheel_render import icon
        icon(p,key,point.x(),point.y(),size)
    else:draw_icon(p,label,point.x(),point.y(),size)


def draw_label(p,rect,text,size,color):
    font=QFont('Segoe UI');font.setPointSizeF(max(7.5,min(10,size*.082)));font.setWeight(QFont.Weight.DemiBold)
    words_for_size=text.replace('\n',' ').split()
    while font.pointSizeF()>7.5 and any(QFontMetrics(font).horizontalAdvance(word)>rect.width() for word in words_for_size):
        font.setPointSizeF(max(7.5,font.pointSizeF()-.25))
    p.setFont(font);metrics=QFontMetrics(font)
    words=text.replace('\n',' ').split();lines=[];line=''
    for word in words:
        candidate=(line+' '+word).strip()
        if line and metrics.horizontalAdvance(candidate)>rect.width():lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    if len(lines)>2:lines=[lines[0],metrics.elidedText(' '.join(lines[1:]),Qt.TextElideMode.ElideRight,int(rect.width()))]
    lines=[metrics.elidedText(line,Qt.TextElideMode.ElideRight,int(rect.width())) for line in lines]
    p.setPen(color);p.drawText(rect,Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop,'\n'.join(lines))


def paint(w):
    from direct_wheel import action_hint
    p=QPainter(w);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    p.fillRect(w.rect(),Qt.GlobalColor.transparent);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    center=w.circle_size/2;size=getattr(w,'tile_size',112)
    layout=geometry(w);w.paths=[entry[1] for entry in layout]
    for key,path,point,index in layout:
        color=accent(w,key);selected=index==w.selected
        paint_surface(p,path,color,selected,key==MORE and w.menu_expanded)
        ink=QColor('#101b29') if selected else color
        p.setPen(QPen(ink,1.9,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        tile_icon(p,key,QPointF(point.x(),point.y()-size*.19),min(30,size*.24))
        draw_label(p,QRectF(point.x()-size*.40,point.y()+size*.06,size*.80,size*.34),title(w,key),size,
                   QColor('#101b29') if selected else QColor('#f0f6ff'))
        favorites=getattr(getattr(w.controller,'prefs',None),'values',{}).get('favorite_actions',[])
        if key in favorites:
            p.setPen(QColor('#101b29') if selected else QColor('#ffbe83'));p.setFont(QFont('Segoe UI',8));p.drawText(QRectF(point.x()+size*.20,point.y()-size*.22,18,18),'★')
    center_point=QPointF(center,center)
    paint_surface(p,octagon(center_point,size),QColor('#526e89'))
    if w.preview is not None and not w.preview.isNull():
        rect=QRectF(center-size*.25,center-size*.33,size*.50,size*.44)
        clip=QPainterPath();clip.addRoundedRect(rect,4,4);p.save();p.setClipPath(clip)
        pixmap=QPixmap.fromImage(w.preview).scaled(int(rect.width()),int(rect.height()),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(round(rect.center().x()-pixmap.width()/2),round(rect.center().y()-pixmap.height()/2),pixmap);p.restore()
    else:
        p.setFont(QFont('Segoe UI',max(8,round(size*.09)),QFont.Weight.Bold));p.setPen(QColor('#edf6ff'))
        p.drawText(QRectF(center-size*.40,center-size*.24,size*.80,size*.25),Qt.AlignmentFlag.AlignCenter,'OrbitDrop')
    name=Path(w.files[0]).name if len(w.files)==1 else f'{len(w.files)} Dateien' if w.files else 'Link' if w.link else 'Datei ziehen'
    if w.checking:name='Prüfe Dateien …'
    p.setFont(QFont('Segoe UI',max(7,round(size*.075)),QFont.Weight.DemiBold));p.setPen(QColor('#edf6ff'))
    p.drawText(QRectF(center-size*.40,center+size*.15,size*.80,size*.22),Qt.AlignmentFlag.AlignCenter,QFontMetrics(p.font()).elidedText(name,Qt.TextElideMode.ElideMiddle,int(size*.80)))
    radius=OUTER_RADIUS if w.menu_expanded and w.secondary_actions else INNER_RADIUS
    width=min(w.circle_size-8,(radius*2+1)*size+12)
    footer=QRectF(center-width/2,center+(radius+.5)*size+13,width,58)
    p.setBrush(QColor('#17283a'));p.setPen(QPen(QColor('#344c66'),1));p.drawRoundedRect(footer,12,12)
    p.setFont(QFont('Segoe UI',8))
    for i,(color,text) in enumerate([('#7ed9ba','Konvertieren'),('#ffbe83','Bearbeiten'),('#83baff','Tools')]):
        x=footer.left()+footer.width()*(i+.5)/3
        p.setPen(QColor(color));p.drawText(QRectF(x-footer.width()/6,footer.top()+4,footer.width()/3,19),Qt.AlignmentFlag.AlignCenter,text)
    if 0<=w.selected<len(w.labels):
        key=w.labels[w.selected]
        if key==MORE:message='Äußeren Ring einklappen' if w.menu_expanded else 'Weitere Werkzeuge · beim Ziehen kurz darauf halten'
        elif key in (PREVIOUS,NEXT):message=f'Äußerer Ring · Seite {w.outer_page+1} von {w.secondary_pages}'
        elif key in HOME:message='Bereich wählen · passende Aktionen für deine Datei'
        else:message=action_hint(key)
    else:
        message=('Bereich wählen' if w.node=='home' else {'convert':'Konvertieren','edit':'Bearbeiten','files':'Tools'}.get(w.mode,'OrbitDrop'))+' · Rechtsklick: Suche · Esc: schließen'
        if not w.outer_supported and w.secondary_actions:message='Wenig Platz · Weitere öffnet die Aktionssuche'
    p.setPen(QColor('#c2d4e6'));p.drawText(footer.adjusted(8,25,-8,-3),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,message)
    p.end()
