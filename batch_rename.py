"""Previewed file renames, with exclusive staging and best-effort rollback."""
import os,re,uuid
from pathlib import Path
from file_actions import move_one


def valid_name(name):
    if not name or len(name)>240 or name in ('.','..') or name.endswith((' ','.')) or re.search(r'[<>:"/\\|?*\x00-\x1f]',name):raise ValueError('Ungültiger Windows-Dateiname: '+name)
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',name.split('.')[0]):raise ValueError('Reservierter Windows-Dateiname: '+name)
    return name


def signature(path):
    s=Path(path).stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)


def renamed_name(path,pattern,index,digits=3):
    if re.sub(r'\{(?:name|n)\}','',pattern).find('{')>=0 or '}' in re.sub(r'\{(?:name|n)\}','',pattern):raise ValueError('Erlaubte Platzhalter: {name} und {n}. Die Dateiendung bleibt erhalten.')
    if not 1<=digits<=8 or not 0<=index<=99_999_999:raise ValueError('Ungültige Nummerierung.')
    return valid_name(re.sub(r'\{(name|n)\}',lambda match:Path(path).stem if match[1]=='name' else str(index).zfill(digits),pattern)+Path(path).suffix)


def validate_pairs(pairs):
    sources=set();targets=set();plans=[]
    for source,target in pairs:
        source=Path(source).absolute();target=Path(target).absolute()
        if source.parent!=target.parent or source.is_symlink() or not source.is_file():raise ValueError('Nur reguläre Dateien im selben Ordner umbenennen.')
        valid_name(target.name);src=str(source).casefold();dst=str(target).casefold()
        if src in sources or dst in targets:raise ValueError('Doppelter Quell- oder Zielname: '+target.name)
        sources.add(src);targets.add(dst);plans.append((source,target,signature(source)))
    if not plans or len(plans)>10000:raise ValueError('Bitte 1 bis 10000 Dateien auswählen.')
    existing={}
    for folder in {target.parent for _,target,_ in plans}:
        for entry in folder.iterdir():existing.setdefault((folder,entry.name.casefold()),[]).append(str(entry.absolute()).casefold())
    for source,target,_ in plans:
        if any(entry not in sources for entry in existing.get((target.parent,target.name.casefold()),[])):raise FileExistsError('Zielname existiert bereits: '+str(target))
    return plans


def plan_renames(files,pattern,start=1,digits=3):
    if not isinstance(pattern,str) or not pattern.strip():raise ValueError('Bitte ein Namensmuster angeben.')
    return validate_pairs([(Path(file),Path(file).with_name(renamed_name(file,pattern,start+i,digits))) for i,file in enumerate(files)])


def execute_renames(plans):
    # Recheck both identities and the complete conflict plan after review.
    for source,target,stamp in plans:
        if signature(source)!=tuple(stamp):raise ValueError('Datei seit der Vorschau geändert: '+str(source))
    validate_pairs([(s,t) for s,t,_ in plans]);staged=[];finished=[]
    try:
        for source,target,_ in plans:
            if str(source)==str(target):continue
            temporary=source.with_name('.orbit-rename-'+uuid.uuid4().hex+'.tmp');move_one(source,temporary);staged.append((source,temporary,target))
        for source,temporary,target in staged:move_one(temporary,target);finished.append((source,temporary,target))
        return [str(target) for _,target,_ in plans]
    except Exception as error:
        failures=[]
        # Move completed outputs back to their staging paths before restoring
        # any original name, so cycles and case-only renames also roll back.
        for source,temporary,target in reversed(finished):
            try:move_one(target,temporary)
            except Exception as rollback:failures.append(str(target)+': '+str(rollback))
        for source,temporary,target in reversed(staged):
            if not os.path.lexists(temporary):continue
            try:move_one(temporary,source)
            except Exception as rollback:failures.append(str(temporary)+': '+str(rollback))
        if failures:raise OSError(str(error)+'; Rücknahme unvollständig. Bitte prüfen: '+'; '.join(failures)) from error
        raise


# Journals contain local paths only; identity checks also apply to persistent undo.
def _write_journal(path,record):
    import json
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as handle:
            json.dump(record,handle,ensure_ascii=False,indent=2);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)

def rename_with_journal(plans,root):
    from datetime import datetime,timezone
    path=Path(root)/'rename-journals'/(uuid.uuid4().hex+'.json')
    record={'version':1,'state':'prepared','time':datetime.now(timezone.utc).isoformat(),'plans':[[str(s),str(t),list(stamp)] for s,t,stamp in plans]}
    _write_journal(path,record)
    try:outputs=execute_renames(plans)
    except Exception:
        record['state']='failed';_write_journal(path,record);raise
    undo=validate_pairs([(t,s) for s,t,_ in plans])
    record.update(state='complete',undo=[[str(s),str(t),list(stamp)] for s,t,stamp in undo])
    try:_write_journal(path,record)
    except Exception as error:
        try:execute_renames(undo)
        except Exception as rollback:raise OSError('Protokoll konnte nicht gespeichert werden; Rücknahme unvollständig: '+str(rollback)) from error
        raise OSError('Protokoll konnte nicht gespeichert werden. Namen wurden zurückgenommen.') from error
    return outputs,path

def read_journal(path):
    import json
    path=Path(path)
    if path.stat().st_size>20*1024*1024:raise ValueError('Umbenennungsprotokoll ist zu groß.')
    record=json.loads(path.read_text(encoding='utf-8'))
    if record.get('version')!=1 or record.get('state')!='complete':raise ValueError('Diese Umbenennung ist nicht rücknehmbar.')
    undo=[(Path(s),Path(t),tuple(stamp)) for s,t,stamp in record['undo']]
    if not 1<=len(undo)<=10000:raise ValueError('Ungültiges Umbenennungsprotokoll.')
    return record,undo

def undo_journal(path):
    record,undo=read_journal(path);outputs=execute_renames(undo);record['state']='undone'
    try:_write_journal(path,record)
    except Exception as error:
        try:execute_renames(validate_pairs([(t,s) for s,t,_ in undo]))
        except Exception as rollback:raise OSError('Protokoll konnte nicht aktualisiert werden; Namen bitte prüfen: '+str(rollback)) from error
        raise OSError('Protokoll konnte nicht aktualisiert werden. Die Rücknahme wurde zurückgesetzt.') from error
    return outputs

def latest_journal(root):
    for path in sorted((Path(root)/'rename-journals').glob('*.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True):
        try:read_journal(path);return path
        except (OSError,ValueError,KeyError,TypeError):continue
    return None
