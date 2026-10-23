"""Create ZIPs and extract archives without overwrites or raw-path extraction."""
import gzip
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import zipfile
from task_runtime import checkpoint, copy_stream

MAX_BYTES=2*1024**3
MAX_ENTRIES=10000


def archive_kind(source):
    path=Path(source)
    if not path.is_file():return None
    with path.open('rb') as handle:header=handle.read(512)
    if header.startswith(b'7z\xbc\xaf\x27\x1c') or path.name.lower().endswith('.001') and header.startswith(b'PK'):return '7Z'
    if header.startswith(b'Rar!\x1a\x07'):return 'RAR'
    if header.startswith(b'\x1f\x8b'):return 'GZIP'
    if header[257:262]==b'ustar':return 'TAR'
    if zipfile.is_zipfile(path):return 'ZIP'
    return None


def _linklike(path):
    status=path.lstat()
    return path.is_symlink() or bool(getattr(status,'st_file_attributes',0)&0x400)


def source_entries(files,output):
    sources=[Path(os.path.abspath(file)) for file in files]
    if not sources:raise ValueError('Keine Dateien ausgewählt.')
    output=Path(os.path.abspath(output))
    names=set()
    for source in sources:
        if not source.exists():raise ValueError('Quelle nicht mehr vorhanden: '+str(source))
        if not source.name or source.parent==source:raise ValueError('Bitte keine Laufwerkswurzel zippen.')
        if _linklike(source):raise ValueError('Verknüpfungen und Junctions werden nicht mitgepackt.')
        name=source.name.casefold()
        if name in names:raise ValueError('Mehrere Quellen mit gleichem Namen: '+source.name)
        names.add(name)
        if source.resolve()==output.resolve() or (source.is_dir() and source.resolve() in output.resolve().parents):
            raise ValueError('Die ZIP-Datei muss außerhalb der ausgewählten Quellen liegen.')
    # Drop selections already covered by a selected parent folder.
    sources=[source for source in sources if not any(other!=source and other in source.parents for other in sources)]
    entries=[]
    for source in sources:
        entries.append((source,source.name))
        if source.is_dir():
            for parent,dirs,files_in_dir in os.walk(source,followlinks=False):
                for name in dirs+files_in_dir:
                    checkpoint(message='Ordner wird gelesen …')
                    child=Path(parent)/name
                    if _linklike(child):raise ValueError('Ordner enthält einen Link/Junction: '+str(child))
                    if not (child.is_file() or child.is_dir()):raise ValueError('Spezialdateien werden nicht unterstützt.')
                    entries.append((child,str(Path(source.name)/child.relative_to(source))))
                    if len(entries)>MAX_ENTRIES:raise ValueError('Zu viele Einträge zum Zippen (max. 10000).')
        if len(entries)>MAX_ENTRIES:raise ValueError('Zu viele Einträge zum Zippen (max. 10000).')
    return entries


def create_zip(files,output,level=6,password='',verify=False):
    if level not in (0,1,6,9):raise ValueError('Ungültige ZIP-Kompressionsstufe.')
    entries=source_entries(files,output);output=Path(output)
    # 'x' reserves the archive exclusively. Never delete an output we did not create.
    module=zipfile
    if password:
        import pyzipper
        module=pyzipper
    compression=module.ZIP_STORED if level==0 else module.ZIP_DEFLATED
    archive=module.AESZipFile(str(output),'x',compression,compresslevel=level,allowZip64=True) if password else zipfile.ZipFile(output,'x',compression,compresslevel=level,allowZip64=True)
    if password:archive.setpassword(password.encode('utf-8'));archive.setencryption(module.WZ_AES,nbits=256)
    try:
        with archive:
            total=sum(source.stat().st_size for source,name in entries if source.is_file());done=0
            for source,name in entries:
                checkpoint(done/max(1,total)*100,'ZIP: '+name)
                if source.is_dir():archive.write(str(source),name)
                else:
                    info=getattr(archive,'zipinfo_cls',zipfile.ZipInfo).from_file(str(source),name);info.compress_type=compression;info._compresslevel=level
                    with source.open('rb') as input_file,archive.open(info,'w',force_zip64=True) as output_file:
                        while block:=input_file.read(1024*1024):
                            checkpoint(done/max(1,total)*100,'ZIP: '+name)
                            output_file.write(block);done+=len(block)
        if verify:
            reader=module.AESZipFile(str(output)) if password else zipfile.ZipFile(output)
            with reader:
                if password:reader.setpassword(password.encode('utf-8'))
                for info in reader.infolist():
                    checkpoint(message='Archiv wird geprüft …')
                    if not info.is_dir():
                        with reader.open(info) as handle:
                            while handle.read(1024*1024):checkpoint(message='Archiv wird geprüft …')
        return output
    except Exception:
        output.unlink(missing_ok=True)
        raise


def _safe_parts(name):
    name=name.replace('\\','/')
    if name.startswith('/') or any(part=='..' for part in name.split('/')):
        raise ValueError('Unsicherer Archivpfad: '+name)
    parts=PurePosixPath(name).parts
    reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    for part in parts:
        if part.rstrip(' .')!=part or re.search(r'[<>:"|?*\x00-\x1f]',part) or part.split('.')[0].upper() in reserved:
            raise ValueError('Unter Windows ungültiger Archivpfad: '+name)
    return parts


def extract_archive(source,output):
    source=Path(source);output=Path(output)
    kind=archive_kind(source)
    if not kind:raise ValueError('Kein unterstütztes Archiv (ZIP/TAR/GZIP/RAR).')
    # Exclusive directory creation avoids merging with or overwriting existing files.
    output.mkdir()
    total=0;count=0;seen=set()
    def store(name,stream=None,declared=0,directory=False):
        nonlocal total,count
        checkpoint(message='Entpacken: '+name)
        parts=_safe_parts(name)
        if not parts:
            if directory:return
            raise ValueError('Leerer Archivpfad.')
        key='/'.join(parts).casefold()
        if key in seen:raise ValueError('Doppelter Archivpfad: '+name)
        seen.add(key);count+=1
        if count>MAX_ENTRIES or total+declared>MAX_BYTES:
            raise ValueError('Archivlimit: maximal 2 GiB und 10000 Einträge.')
        target=output.joinpath(*parts)
        if directory:
            target.mkdir(parents=True,exist_ok=True);return
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:
            while chunk:=stream.read(1024*1024):
                checkpoint(message='Entpacken: '+name)
                total+=len(chunk)
                if total>MAX_BYTES:raise ValueError('Archiv überschreitet das Limit von 2 GiB.')
                handle.write(chunk)
    try:
        if kind=='ZIP':
            with zipfile.ZipFile(source) as archive:
                for info in archive.infolist():
                    mode=info.external_attr>>16
                    if stat.S_ISLNK(mode):raise ValueError('Archiv enthält symbolische Links.')
                    if info.flag_bits&1:raise ValueError('Passwortgeschützte ZIPs noch nicht unterstützt.')
                    if info.is_dir():store(info.filename,directory=True)
                    else:
                        with archive.open(info) as handle:store(info.filename,handle,info.file_size)
        elif kind=='RAR':
            import rarfile
            with rarfile.RarFile(source) as archive:
                if archive.needs_password():raise ValueError('Passwortgeschützte RARs noch nicht unterstützt.')
                for info in archive.infolist():
                    if info.is_symlink():raise ValueError('Archiv enthält symbolische Links.')
                    if info.isdir():store(info.filename,directory=True)
                    else:
                        with archive.open(info) as handle:store(info.filename,handle,info.file_size)
        else:
            try:archive=tarfile.open(source,'r:*')
            except tarfile.ReadError:
                if kind!='GZIP':raise
                with gzip.open(source,'rb') as handle:store(source.stem,handle)
            else:
                with archive:
                    for info in archive:
                        if info.isdir():store(info.name,directory=True)
                        elif not info.isfile():raise ValueError('Links/Geräte im Archiv werden nicht entpackt.')
                        else:
                            with archive.extractfile(info) as handle:store(info.name,handle,info.size)
        return output
    except Exception:
        shutil.rmtree(output)
        raise
