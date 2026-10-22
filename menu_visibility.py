"""Stable menu IDs shared by settings, radial menus and contextual search."""
EDIT_IDS=('TEXT ERKENNEN','AUDIO VERBESSERN','BILD EDITOR','ZUSCHNEIDEN','MARKIEREN','GRÖSSE','SCHWARZWEISS','BITMAP','90° LINKS','90° RECHTS','180°','SCHNEIDEN','PDF TEILEN','PDF SEITEN','PDF VERBINDEN','KOMPRIMIEREN')
APP_IDS=('AKTIONSSUCHE','UPDATES','BILDABLÄUFE','SCHNELLAKTIONEN','LINK LADEN','AUFTRÄGE','EINSTELLUNGEN','KONVERTER','DEBUGGING','HILFE')


def action_id(key):
    if key.endswith(':ZURÜCK') or key=='ZURÜCK':return 'nav:ZURÜCK'
    if key in ('KONVERTIEREN','BEARBEITEN','TOOLS'):return 'home:'+key
    return key


def visible_actions(actions,values):
    hidden=set(values.get('hidden_actions',[]));formats=set(values.get('hidden_formats',[]));result=[]
    for key in actions:
        if action_id(key) in hidden:continue
        if key.startswith('format:'):
            target=key.split(':',1)[1]
            if target in formats or target.startswith('SVG ') and 'SVG' in formats:continue
        result.append(key)
    return result


def action_catalog(values):
    from converter import EXTENSIONS
    from file_actions import FILE_ACTIONS
    from direct_wheel import NAMES
    def title(label):return NAMES.get(label,label).replace('\n',' ')
    groups=[('Bereichsauswahl',[('home:'+key,title(key)) for key in ('KONVERTIEREN','BEARBEITEN','TOOLS')]),('Konvertieren',[]),('Bearbeiten',[('edit:'+key,title(key)) for key in EDIT_IDS]),('Tools · Dateien',[('tool:'+key,title(key)) for key in FILE_ACTIONS]),('Tools · Programm',[('app:'+key,title(key)) for key in APP_IDS]),('Links & Downloads',[('download:'+key,title(key)) for key in ('AUDIO LADEN','VIDEO LADEN')]),('Navigation',[('nav:ZURÜCK','Zurück nach einer Menünavigation')])]
    for target in sorted(EXTENSIONS):
        groups[1][1].extend([('format:SVG SCHNELL','SVG · Schnell'),('format:SVG ERWEITERT','SVG · Erweitert')] if target=='SVG' else [('format:'+target,title(target))])
    custom=[('edit:quick:'+item['id'],item['name']) for item in values.get('quick_actions',[])]+[('edit:flow:'+item['id'],item['name']) for item in values.get('workflows',[])]
    if custom:groups.append(('Eigene Schnellaktionen & Abläufe',custom))
    known={key for _,items in groups for key,_ in items}
    extra=[(key,key) for key in values.get('hidden_actions',[]) if key not in known]
    if extra:groups.append(('Ältere / derzeit nicht verfügbare Einträge',extra))
    return groups
