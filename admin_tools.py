"""Read-only diagnostics and explicit exports for administrators and developers."""
from pathlib import Path
from datetime import datetime,timezone
from collections import deque
import hashlib,difflib,os,re,io,csv
from data_formats import MAX_TEXT,read_text,parse,serialize,read_table,records,kind_for
from task_runtime import checkpoint

ENCODINGS=('utf-8','utf-8-sig','utf-16','utf-16-le','utf-16-be','cp1252','latin-1')

def file_hashes(files,expected=''):
    expected=expected.strip().lower()
    if expected and not re.fullmatch('[a-f0-9]{64}',expected):raise ValueError('SHA-256 bitte als genau 64 Hex-Zeichen eingeben.')
    rows=[]
    for path in map(Path,files):
        from batch_rename import signature
        stamp=signature(path);digest=hashlib.sha256();size=path.stat().st_size;done=0
        with path.open('rb') as f:
            while block:=f.read(1024*1024):
                digest.update(block);done+=len(block);checkpoint(done/max(1,size)*100,'SHA-256: '+path.name)
        if signature(path)!=stamp:raise ValueError('Datei wurde während der Prüfsummenberechnung geändert: '+path.name)
        value=digest.hexdigest();rows.append(f'{path.name}\nGröße: {done} Bytes\nSHA-256: {value}'+('\nVergleich: '+('STIMMT ÜBEREIN' if value==expected else 'STIMMT NICHT ÜBEREIN') if expected else ''))
    return '\n\n'.join(rows)

def compare_files(files):
    if len(files)!=2:raise ValueError('Bitte genau zwei Dateien auswählen.')
    a,b=map(Path,files);hashes=file_hashes([a,b]);same=a.stat().st_size==b.stat().st_size
    if same:
        with a.open('rb') as af,b.open('rb') as bf:
            while block:=af.read(1024*1024):
                checkpoint(message='Dateien werden verglichen …')
                if block!=bf.read(len(block)):same=False;break
    if same:return 'Dateien sind bytegenau identisch.\n\n'+hashes
    try:
        left,_=read_text(a);right,_=read_text(b)
    except ValueError:return 'Dateien unterscheiden sich. Binärdatei oder zu groß für einen Textvergleich.\n\n'+hashes
    if len(left.splitlines())+len(right.splitlines())>50000:raise ValueError('Zu viele Zeilen für den Textvergleich (max. 50000 insgesamt). SHA-256 separat vergleichen.')
    result=[];size=0
    for line in difflib.unified_diff(left.splitlines(keepends=True),right.splitlines(keepends=True),fromfile=a.name,tofile=b.name):
        checkpoint(message='Textunterschiede werden ermittelt …');size+=len(line)
        if size>2*1024*1024:result.append('\n… Anzeige auf 2 MiB begrenzt.');break
        result.append(line)
    if not result:return 'Text ist gleich, Bytes unterscheiden sich (z. B. Kodierung oder BOM).\n\n'+hashes
    return 'Unterschiede (− erste Datei, + zweite Datei):\n\n'+''.join(result)

def text_transform(text,find='',replace='',deduplicate=False,sort=False,number=False):
    if find:text=text.replace(find,replace)
    if deduplicate or sort or number:
        lines=text.splitlines();end=text.endswith(('\n','\r'))
        if deduplicate:lines=list(dict.fromkeys(lines))
        if sort:lines=sorted(lines)
        if number:lines=[f'{i}\t{line}' for i,line in enumerate(lines,1)]
        separator='\r\n' if '\r\n' in text else '\r' if '\r' in text else '\n'
        text=separator.join(lines)+(separator if end else '')
    return text

def table_transform(text,kind,columns='',sort_column='',deduplicate=False,input_delimiter=None,delimiter=',',target='CSV'):
    rows=read_table(text,kind,input_delimiter)
    if not rows:raise ValueError('Keine Datenzeilen vorhanden.')
    keys=list(rows[0]);chosen=[x.strip() for x in columns.split(',') if x.strip()] if columns.strip() else keys
    if not chosen or len(set(chosen))!=len(chosen) or not set(chosen)<=set(keys):raise ValueError('Spalten bitte mit exakten Namen kommasepariert auswählen.')
    rows=[{k:r[k] for k in chosen} for r in rows]
    if sort_column:
        if sort_column not in chosen:raise ValueError('Sortierspalte ist nicht ausgewählt.')
        rows.sort(key=lambda r:r[sort_column])
    if deduplicate:
        seen=set();unique=[]
        for r in rows:
            key=tuple(r.values())
            if key not in seen:seen.add(key);unique.append(r)
        rows=unique
    return serialize(rows,target,delimiter=delimiter)

def _time(text):
    value=datetime.fromisoformat(text.strip().replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def log_lines(path,needle='',start='',end='',tail=0,encoding='utf-8',preview_limit=5000):
    """Filter streaming, or seek a bounded tail. No full-file load."""
    path=Path(path);first=_time(start) if start.strip() else None;last=_time(end) if end.strip() else None
    if first and last and first>last:raise ValueError('Startzeit liegt nach der Endzeit.')
    if encoding not in ENCODINGS:raise ValueError('Unbekannte Zeichenkodierung.')
    if path.stat().st_size>512*1024*1024 and not tail:raise ValueError('Für vollständiges Filtern maximal 512 MiB; alternativ letzte Zeilen anzeigen.')
    if not 0<=tail<=10000:raise ValueError('Letzte Zeilen: 0 bis 10000.')
    def source():
        if tail:
            with path.open('rb') as f:
                header=f.read(4);size=f.seek(0,2);offset=max(0,size-4*1024*1024)
                if encoding.startswith('utf-16'):offset-=offset%2
                f.seek(offset);raw=f.read()
            codec=encoding
            if encoding=='utf-16' and offset:codec='utf-16-le' if header.startswith(b'\xff\xfe') else 'utf-16-be' if header.startswith(b'\xfe\xff') else encoding
            if offset:
                separator='\n'.encode(codec)
                boundary=raw.find(separator)
                if codec.startswith('utf-16'):
                    while boundary>=0 and boundary%2:boundary=raw.find(separator,boundary+1)
                if boundary<0:raise ValueError('Keine vollständige Zeile in den letzten 4 MiB gefunden.')
                raw=raw[boundary+len(separator):]
            text=raw.decode(codec,errors='strict')
            yield from deque(text.splitlines(keepends=True),maxlen=tail)
        else:
            with path.open('r',encoding=encoding,newline='') as f:
                while line:=f.readline(1024*1024+1):
                    if len(line)>1024*1024:raise ValueError('Eine Logzeile ist größer als 1 MiB.')
                    yield line
    count=0
    for n,line in enumerate(source(),1):
        checkpoint(message=f'Log · Zeile {n}')
        if len(line)>1024*1024:raise ValueError('Eine Logzeile ist größer als 1 MiB.')
        if needle.casefold() not in line.casefold():continue
        if first or last:
            match=re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?',line)
            if not match:continue
            stamp=_time(match.group())
            if first and stamp<first or last and stamp>last:continue
        count+=1
        if preview_limit and count>preview_limit:yield '\n… Vorschau begrenzt; Export enthält alle passenden Zeilen.\n';return
        yield line

def load_certificates(path,password=''):
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import pkcs12
    path=Path(path)
    if path.stat().st_size>4*1024*1024:raise ValueError('Zertifikatsdatei zu groß (max. 4 MiB).')
    data=path.read_bytes()
    if path.suffix.lower() in ('.pfx','.p12'):
        try:key,cert,chain=pkcs12.load_key_and_certificates(data,password.encode('utf-8') if password else None)
        except ValueError as e:raise ValueError('PFX nicht lesbar. Passwort oder Datei prüfen.') from e
        key=None;certs=([cert] if cert is not None else [])+list(chain or [])
    elif b'-----BEGIN CERTIFICATE-----' in data:
        blocks=re.findall(br'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',data,re.S);certs=[x509.load_pem_x509_certificate(b) for b in blocks]
    else:
        try:certs=[x509.load_der_x509_certificate(data)]
        except ValueError as e:raise ValueError('Kein unterstütztes X.509-Zertifikat gefunden. Private Schlüssel werden nicht angezeigt.') from e
    if not certs:raise ValueError('Keine Zertifikate enthalten.')
    if len(certs)>100:raise ValueError('Maximal 100 Zertifikate pro Anzeige.')
    return certs

def certificate_report(path,password=''):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    reports=[];now=datetime.now(timezone.utc)
    for index,cert in enumerate(load_certificates(path,password),1):
        try:sans=', '.join(str(x.value) for x in cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value)
        except x509.ExtensionNotFound:sans='Keine SANs'
        try:ca=cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        except x509.ExtensionNotFound:ca=False
        status='ABGELAUFEN' if now>cert.not_valid_after_utc else 'NOCH NICHT GÜLTIG' if now<cert.not_valid_before_utc else 'Im zeitlichen Gültigkeitsbereich'
        reports.append(f'Zertifikat {index}\nInhaber: {cert.subject.rfc4514_string()}\nAussteller: {cert.issuer.rfc4514_string()}\nSeriennummer: {cert.serial_number:X}\nSAN: {sans}\nCA: {ca}\nGültig ab: {cert.not_valid_before_utc.isoformat()}\nGültig bis: {cert.not_valid_after_utc.isoformat()}\nStatus: {status}\nSHA-256: {cert.fingerprint(hashes.SHA256()).hex()}')
    return '\n\n'.join(reports)+'\n\nNur lokale Anzeige. Zertifikatskette, Vertrauen, Hostname und Sperrstatus werden nicht validiert. Private Schlüssel werden nicht exportiert.'

def certificate_bytes(path,target,password=''):
    from cryptography.hazmat.primitives.serialization import Encoding
    if target not in ('PEM','DER'):raise ValueError('Zertifikatsziel muss PEM oder DER sein.')
    certs=load_certificates(path,password)
    if target=='DER' and len(certs)!=1:raise ValueError('DER kann hier nur genau ein Zertifikat enthalten; für eine Kette PEM verwenden.')
    return b''.join(c.public_bytes(Encoding.PEM if target=='PEM' else Encoding.DER) for c in certs)
