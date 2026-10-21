"""Bounded local recognition reports. Never retain file bytes, media tags or full paths."""
from datetime import datetime,timezone
from importlib.metadata import version,PackageNotFoundError
import json
from pathlib import Path
import platform
from functools import lru_cache
from filetypes import backend,media_signature,run

@lru_cache(maxsize=1)
def environment():
    packages={}
    for name in ('PySide6','Pillow','av','yt-dlp'):
        try:packages[name]=version(name)
        except PackageNotFoundError:packages[name]='fehlt'
    converters={}
    for name in ('ffmpeg','ffprobe','pandoc'):
        executable=backend(name)
        converters[name]={'available':bool(executable)}
        if executable:
            try:
                result=run([executable,'-version' if name.startswith('ff') else '--version'],timeout=5)
                converters[name]['version']=(result.stdout.splitlines() or ['Nicht abrufbar'])[0][:200]
            except Exception:converters[name]['version']='Start fehlgeschlagen'
    return {'app_version':'0.16.0','system':platform.system(),'system_release':platform.release(),'architecture':platform.machine(),'python':platform.python_version(),'packages':packages,'converters':converters}

def recognition_report(path,info):
    path=Path(path)
    if not path.is_file():return None
    reason=str(info.message or 'Kein unterstützter Dateiinhalt erkannt.')
    for private in sorted({str(path),str(path.resolve()),str(path.parent),str(path.resolve().parent),path.name,str(Path.home())},key=len,reverse=True):
        if len(private)>1:reason=reason.replace(private,'[Datei/Pfad]')
    report={'name':path.name,'extension':path.suffix.lower()[:30],'kind':info.kind,'reason':reason[:1000]}
    try:
        report['size_bytes']=path.stat().st_size
        with path.open('rb') as handle:report['container_hint']=media_signature(handle.read(64)) or 'Keine bekannte Mediensignatur'
    except OSError:report['read_error']='Datei nicht mehr lesbar'
    # Only technical codec fields; no arbitrary tags, paths, chapters or metadata.
    executable=backend('ffprobe')
    if executable:
        try:
            result=run([executable,'-v','error','-protocol_whitelist','file,pipe','-show_entries','stream=codec_type,codec_name,width,height,sample_rate,channels','-of','json',str(path.resolve())],timeout=5)
            if result.returncode==0:
                allowed={'codec_type','codec_name','width','height','sample_rate','channels'}
                report['streams']=[{key:value for key,value in stream.items() if key in allowed} for stream in json.loads(result.stdout).get('streams',[])[:12]]
        except Exception:report['probe_status']='Codecprüfung fehlgeschlagen oder Zeitlimit erreicht'
    report['environment']=environment()
    return report

class DiagnosticStore:
    def __init__(self,prefs):
        self.prefs=prefs;self.records=[]
        try:
            records=json.loads((prefs.root/'diagnostics.json').read_text(encoding='utf-8'))
            if isinstance(records,list):self.records=[r for r in records if isinstance(r,dict)][-100:]
        except (OSError,ValueError):pass
    def add(self,reports):
        for report in reports:
            if not report:continue
            key=tuple(report.get(k) for k in ('name','extension','size_bytes','kind','reason'))
            existing=next((r for r in self.records if tuple(r.get(k) for k in ('name','extension','size_bytes','kind','reason'))==key),None)
            now=datetime.now(timezone.utc).isoformat(timespec='seconds')
            if existing:
                self.records.remove(existing);record={**report,'first_seen':existing.get('first_seen',now),'last_seen':now,'occurrences':int(existing.get('occurrences',1))+1}
            else:record={**report,'first_seen':now,'last_seen':now,'occurrences':1}
            self.records.append(record)
        self.records=self.records[-100:];self.prefs._save('diagnostics.json',self.records)
    def clear(self):self.prefs._save('diagnostics.json',[]);self.records=[]
    def export_data(self,include_names=False):
        records=json.loads(json.dumps(self.records))
        if not include_names:
            for index,record in enumerate(records):record['name']=f'Datei_{index+1}'+record.get('extension','')
        return {'schema_version':1,'app':'OrbitDrop','records':records,'note':'Keine Originaldateien, vollständigen Pfade, Dateiinhalte oder Medien-Tags enthalten.'}
    def export(self,path,include_names=False):
        # Exclusive creation: never silently replace a user file.
        with Path(path).open('x',encoding='utf-8') as handle:json.dump(self.export_data(include_names),handle,ensure_ascii=False,indent=2)
