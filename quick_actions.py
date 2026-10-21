"""Named compression recipes, not executable shell commands."""
import uuid
from compression import compression_settings


def validate_presets(items):
    if not isinstance(items,list) or len(items)>40:raise ValueError('Maximal 40 Schnellaktionen sind erlaubt.')
    result=[];names=set();ids=set()
    for item in items:
        if not isinstance(item,dict):raise ValueError('Ungültige Schnellaktion.')
        try:identifier=str(uuid.UUID(str(item['id'])));name=str(item['name']).strip();kind=item['kind']
        except (KeyError,ValueError,TypeError,AttributeError) as error:raise ValueError('Ungültige Schnellaktion.') from error
        if not 1<=len(name)<=28 or any(ord(c)<32 for c in name) or name.casefold() in names or identifier in ids:raise ValueError('Schnellaktionen benötigen eindeutige Namen (max. 28 Zeichen).')
        if kind not in ('Bild','Video','Audio','PDF'):raise ValueError('Ungültiger Schnellaktion-Dateityp.')
        names.add(name.casefold());ids.add(identifier);result.append({'id':identifier,'name':name,'kind':kind,'parameters':compression_settings(item.get('parameters',{}))})
    return result


def save_preset(prefs,name,kind,parameters):
    items=list(prefs.values.get('quick_actions',[]));items.append({'id':str(uuid.uuid4()),'name':name,'kind':kind,'parameters':parameters})
    prefs.update(dict(prefs.values,quick_actions=validate_presets(items)))
