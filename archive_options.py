"""Archive options with exclusive outputs, bounded inspection and staged extraction."""
from pathlib import Path
import gzip,os,shutil,stat,subprocess,sys,tarfile,tempfile,time,zipfile
from contextlib import contextmanager
from archives import source_entries,create_zip,archive_kind,_safe_parts,_linklike,MAX_ENTRIES,MAX_BYTES
from task_runtime import checkpoint,copy_stream,stop_process
from file_actions import move_one

LEVELS={'Schnell':1,'Ausgewogen':6,'Kleinste Datei':9,'Ohne Kompression':0}

def sevenzip():
    from filetypes import backend
    found=backend('7z') or backend('7zz')
    if found:return found
    if sys.platform=='win32':
        for env in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
            root=Path(os.environ.get(env,'C:/Program Files'))
            for suffix in ('7-Zip/7z.exe','Programs/7-Zip/7z.exe'):
                if (root/suffix).is_file():return str(root/suffix)
    return None

def _seven(args,cwd=None,stdout_path=None,limit=16*1024*1024):
    exe=sevenzip()
    if not exe:raise OSError('7-Zip fehlt. Im Dashboard unter Einrichtung installieren und erneut prüfen.')
    flags={'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform=='win32' else {'start_new_session':True}
    with tempfile.TemporaryFile() as log,tempfile.TemporaryFile() as err:
        output=open(stdout_path,'xb') if stdout_path else log
        process=None
        try:
            process=subprocess.Popen([exe,*args],cwd=cwd,stdin=subprocess.DEVNULL,stdout=output,stderr=err,**flags);started=time.monotonic()
            while process.poll() is None:
                checkpoint(message='7-Zip verarbeitet das Archiv …')
                if time.monotonic()-started>3600:raise OSError('Zeitlimit für 7-Zip erreicht.')
                if os.fstat(output.fileno()).st_size>limit or os.fstat(err.fileno()).st_size>1024*1024:raise ValueError('Archivausgabe überschreitet das erlaubte Limit.')
                try:process.wait(timeout=.1)
                except subprocess.TimeoutExpired:pass
            checkpoint()
            if os.fstat(output.fileno()).st_size>limit:raise ValueError('Archivausgabe überschreitet das erlaubte Limit.')
            if process.returncode:
                err.seek(0);log.seek(0);detail=(err.read(4096)+log.read(4096)).decode('utf-8',errors='replace')
                raise ValueError('7-Zip konnte das Archiv nicht verarbeiten. Passwort, Archiv und verfügbare Teile prüfen.\n'+detail[-1500:])
            if stdout_path:return None
            log.seek(0);return log.read().decode('utf-8',errors='replace')
        except BaseException:
            if process is not None:stop_process(process)
            raise
        finally:
            if stdout_path:output.close()

def create_archive(files,output,format='ZIP',level=6,password='',hide_names=False,split_mb=0,verify=True):
    output=Path(output).absolute();split_mb=int(split_mb)
    if format not in ('ZIP','7Z','TAR.GZ') or level not in (0,1,6,9) or not 0<=split_mb<=100000:raise ValueError('Ungültige Archivoptionen.')
    if format=='TAR.GZ' and (password or hide_names or split_mb):raise ValueError('TAR.GZ unterstützt hier kein Passwort, keine verschlüsselten Namen und keine Teile.')
    if hide_names and (format!='7Z' or not password):raise ValueError('Verschlüsselte Dateinamen benötigen 7z mit Passwort.')
    entries=source_entries(files,output)
    for _,name in entries:_safe_parts(name)
    if output.exists():raise FileExistsError('Archiv existiert bereits. Bitte einen neuen Namen wählen.')
    if format=='ZIP' and not split_mb:
        return [str(create_zip(files,output,level,password,verify))]
    if format=='TAR.GZ':
        with output.open('xb') as handle:
            try:
                with tarfile.open(fileobj=handle,mode='w:gz',compresslevel=level) as archive:
                    for index,(source,name) in enumerate(entries):
                        checkpoint(index/max(1,len(entries))*90,'TAR.GZ: '+name)
                        info=archive.gettarinfo(str(source),arcname=name)
                        if source.is_dir():archive.addfile(info)
                        else:
                            class Reader:
                                def __init__(self,stream):self.stream=stream
                                def read(self,size=-1):checkpoint();return self.stream.read(size)
                            with source.open('rb') as source_file:archive.addfile(info,Reader(source_file))
                handle.flush()
                if verify:
                    with tarfile.open(output,'r:gz') as archive:
                        for info in archive:
                            checkpoint(message='Archiv wird geprüft …')
                            if info.isfile():
                                with archive.extractfile(info) as member:
                                    while member.read(1024*1024):checkpoint()
                return [str(output)]
            except Exception:handle.close();output.unlink(missing_ok=True);raise
    if not sevenzip():raise OSError('Für 7z und geteilte Archive bitte 7-Zip im Dashboard einrichten.')
    published=[]
    with tempfile.TemporaryDirectory(prefix='orbit-archive-',dir=output.parent) as directory:
        directory=Path(directory);stage=directory/'source';stage.mkdir();packed=directory/'packed';packed.mkdir()
        # A separate input tree gives identical archive paths for selections from
        # different folders. Hardlinks are read-only inputs; cross-volume fallback copies.
        for source,name in entries:
            checkpoint(message='Archivquellen werden vorbereitet …');target=stage.joinpath(*_safe_parts(name))
            if source.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                try:os.link(source,target)
                except OSError:
                    with source.open('rb') as src,target.open('xb') as dst:copy_stream(src,dst)
        names=sorted({Path(name).parts[0] for _,name in entries});manifest=directory/'sources.txt';manifest.write_text('\n'.join(names)+'\n',encoding='utf-8')
        target=packed/output.name;args=['a','-t'+('7z' if format=='7Z' else 'zip'),'-mx='+str(level),'-sse','-spd','-scsUTF-8','-bso0','-bsp0']
        if format=='ZIP':args+=['-mm=Deflate']
        if password:args+=['-p'+password, '-mhe=on' if format=='7Z' and hide_names else '-mhe=off' if format=='7Z' else '-mem=AES256']
        if split_mb:args+=['-v'+str(split_mb)+'m']
        _seven([*args,str(target),'@'+str(manifest)],cwd=stage)
        outputs=sorted(packed.iterdir())
        if not outputs:raise ValueError('7-Zip hat kein Archiv erzeugt.')
        if verify:_seven(['t','-bso0','-bsp0','-p'+password,'--',str(outputs[0])])
        try:
            for path in outputs:
                checkpoint(message='Archiv wird gespeichert …');dest=output.parent/path.name;move_one(path,dest);published.append(dest)
            return [str(p) for p in published]
        except Exception:
            for path in published:path.unlink(missing_ok=True)
            raise

def _uses_seven(source):
    kind=archive_kind(source)
    return kind=='7Z' or kind=='RAR' and sevenzip() is not None

@contextmanager
def _opened(source,password=''):
    kind=archive_kind(source)
    if kind=='ZIP':
        import pyzipper
        with pyzipper.AESZipFile(str(source)) as archive:
            if password:archive.setpassword(password.encode('utf-8'))
            yield kind,archive
    elif kind=='RAR':
        import rarfile
        with rarfile.RarFile(source) as archive:
            if password:archive.setpassword(password)
            yield kind,archive
    elif kind in ('TAR','GZIP'):
        try:archive=tarfile.open(source,'r:*')
        except tarfile.ReadError:
            if kind!='GZIP':raise
            with gzip.open(source,'rb') as stream:yield 'SINGLE_GZIP',stream
        else:
            with archive:yield 'TAR',archive
    else:raise ValueError('Dieses Archiv benötigt 7-Zip oder wird nicht unterstützt.')

def list_archive(source,password=''):
    source=Path(source);rows=[]
    if _uses_seven(source):
        text=_seven(['l','-slt','-ba','-sccUTF-8','-p'+password,'--',str(source)])
        for block in text.replace('\r','').strip().split('\n\n'):
            fields={}
            for line in block.splitlines():
                if ' = ' in line:
                    key,value=line.split(' = ',1)
                    if key in fields:raise ValueError('Archiv enthält mehrdeutige Dateinamen.')
                    fields[key]=value
            if 'Path' not in fields:continue
            if any(k in fields for k in ('Symbolic Link','Hard Link')):raise ValueError('Links im Archiv werden nicht unterstützt.')
            rows.append(dict(name=fields['Path'],size=int(fields.get('Size') or 0),directory=fields.get('Folder')=='+' or fields.get('Attributes','').startswith('D')))
    else:
        with _opened(source,password) as (kind,archive):
            if kind=='SINGLE_GZIP':rows=[dict(name=source.stem,size=0,directory=False)]
            elif kind=='TAR':
                for item in archive:
                    if not(item.isfile() or item.isdir()):raise ValueError('Links und Geräte im Archiv werden nicht entpackt.')
                    rows.append(dict(name=item.name,size=item.size,directory=item.isdir()))
                    if len(rows)>MAX_ENTRIES:raise ValueError('Archiv enthält zu viele Einträge.')
            else:
                for item in archive.infolist():
                    if (kind=='ZIP' and stat.S_ISLNK(item.external_attr>>16)) or (kind=='RAR' and item.is_symlink()):raise ValueError('Links im Archiv werden nicht entpackt.')
                    rows.append(dict(name=item.filename,size=item.file_size,directory=item.is_dir() if kind=='ZIP' else item.isdir()))
                    if len(rows)>MAX_ENTRIES:raise ValueError('Archiv enthält zu viele Einträge.')
    seen=set();total=0
    if len(rows)>MAX_ENTRIES:raise ValueError('Archiv enthält zu viele Einträge (max. 10000).')
    for row in rows:
        parts=_safe_parts(row['name']);key='/'.join(parts).casefold()
        if not parts or key in seen:raise ValueError('Leerer oder doppelter Archivpfad.')
        if row['size']<0:raise ValueError('Ungültige Archivgröße.')
        seen.add(key);total+=row['size']
    if total>MAX_BYTES:raise ValueError('Entpacklimit: maximal 2 GiB unkomprimierter Inhalt.')
    return rows

def _check_destination(path):
    for parent in (path,*path.parents):
        if os.path.lexists(parent) and _linklike(parent):raise ValueError('Ziel enthält eine Verknüpfung/Junction: '+str(parent))

def extract_options(source,destination,password='',selected=None,conflict='error',subfolder=True):
    source=Path(source).absolute();destination=Path(destination).absolute()
    if conflict not in ('error','skip','rename','overwrite'):raise ValueError('Ungültige Konfliktoption.')
    _check_destination(destination)
    if not destination.is_dir():raise ValueError('Bitte einen vorhandenen Zielordner wählen.')
    rows=list_archive(source,password);chosen=set(selected) if selected is not None else {r['name'] for r in rows}
    if not chosen or not chosen<={r['name'] for r in rows}:raise ValueError('Bitte vorhandene Archiveinträge auswählen.')
    rows=[r for r in rows if r['name'] in chosen]
    total=0;installed=[];installed_stamps={};backups=[];created_dirs=[]
    temporary=tempfile.mkdtemp(prefix='.orbit-unpack-',dir=destination);keep_recovery=False
    try:
        stage=Path(temporary)/'data';stage.mkdir();backup=Path(temporary)/'backup';backup.mkdir()
        def store(row,stream):
            nonlocal total
            target=stage.joinpath(*_safe_parts(row['name']));target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as handle:
                while block:=stream.read(1024*1024):
                    checkpoint(message='Entpacken: '+row['name']);total+=len(block)
                    if total>MAX_BYTES:raise ValueError('Archiv überschreitet 2 GiB.')
                    handle.write(block)
        if _uses_seven(source):
            for index,row in enumerate(rows):
                if row['directory']:continue
                raw=Path(temporary)/('member-'+str(index))
                _seven(['x','-so','-spd','-bso0','-bsp0','-p'+password,'--',str(source),row['name']],stdout_path=raw,limit=MAX_BYTES-total)
                with raw.open('rb') as stream:store(row,stream)
                raw.unlink()
        else:
            with _opened(source,password) as (kind,archive):
                for row in rows:
                    checkpoint(message='Entpacken: '+row['name'])
                    if row['directory']:continue
                    if kind=='SINGLE_GZIP':store(row,archive)
                    elif kind=='TAR':
                        with archive.extractfile(row['name']) as stream:store(row,stream)
                    else:
                        with archive.open(row['name']) as stream:store(row,stream)
        # Decompression finishes before any existing destination file is touched.
        root=destination
        if subfolder:
            name=source.name
            for suffix in ('.tar.gz','.tar.bz2','.tar.xz','.001','.7z','.zip','.rar','.tar','.gz'):
                if name.lower().endswith(suffix):name=name[:-len(suffix)]
            base=(name or 'Archiv')+'_entpackt';root=destination/base;number=1
            while os.path.lexists(root):root=destination/(base+'_'+str(number));number+=1
        def make_dir(path):
            if path.is_dir():return
            if os.path.lexists(path):raise FileExistsError('Ein Zielordner ist bereits als Datei vorhanden: '+str(path))
            make_dir(path.parent);path.mkdir();created_dirs.append(path)
        targets=[];used=set()
        for row in rows:
            target=root.joinpath(*_safe_parts(row['name']));_check_destination(target)
            if row['directory']:
                if target.exists() and not target.is_dir():raise FileExistsError('Ordnername belegt: '+str(target))
                targets.append((row,target));continue
            if target.exists() or str(target).casefold() in used:
                if conflict=='skip':continue
                if conflict=='error':raise FileExistsError('Zielname existiert bereits: '+str(target))
                if conflict=='rename':
                    base=target;number=2
                    while target.exists() or str(target).casefold() in used:target=base.with_name(base.stem+'_'+str(number)+base.suffix);number+=1
                elif target.is_dir():raise FileExistsError('Ziel ist ein Ordner: '+str(target))
            if target==source:raise ValueError('Das Quellarchiv darf nicht überschrieben werden.')
            used.add(str(target).casefold());targets.append((row,target))
        try:
            for row,target in targets:
                checkpoint(message='Dateien werden übernommen …');_check_destination(target)
                if row['directory']:make_dir(target);continue
                make_dir(target.parent)
                if os.path.lexists(target):
                    if conflict!='overwrite':raise FileExistsError('Ziel inzwischen belegt: '+str(target))
                    saved=backup/str(len(backups));move_one(target,saved);backups.append((target,saved))
                move_one(stage.joinpath(*_safe_parts(row['name'])),target);installed.append(target)
                from batch_rename import signature
                installed_stamps[target]=signature(target)
        except Exception as error:
            failures=[]
            for target in reversed(installed):
                try:
                    if target.exists() and signature(target)!=installed_stamps[target]:raise OSError('Ergebnis wurde inzwischen geändert: '+str(target))
                    target.unlink(missing_ok=True)
                except OSError as failure:failures.append(str(failure))
            for target,saved in reversed(backups):
                try:move_one(saved,target)
                except OSError as failure:failures.append(str(failure))
            for folder in reversed(created_dirs):
                try:folder.rmdir()
                except OSError:pass
            if failures:
                import json
                keep_recovery=True
                (Path(temporary)/'recovery.json').write_text(json.dumps([(str(t),str(b)) for t,b in backups],ensure_ascii=False),encoding='utf-8')
                raise OSError('Rücknahme unvollständig. Sicherungen bleiben erhalten unter '+str(temporary)+'. '+str(error)) from error
            raise
    finally:
        if not keep_recovery:shutil.rmtree(temporary)
    return [str(root)] if subfolder else [str(p) for p in installed]


def test_archive(source,password=''):
    rows=list_archive(source,password);total=0
    if _uses_seven(source):
        _seven(['t','-bso0','-bsp0','-p'+password,'--',str(Path(source).absolute())]);return len(rows)
    with _opened(source,password) as (kind,archive):
        for row in rows:
            if row['directory']:continue
            stream=archive if kind=='SINGLE_GZIP' else archive.extractfile(row['name']) if kind=='TAR' else archive.open(row['name'])
            try:
                while block:=stream.read(1024*1024):
                    total+=len(block);checkpoint(message='Archivprüfung: '+row['name'])
                    if total>MAX_BYTES:raise ValueError('Archiv überschreitet 2 GiB.')
            finally:
                if kind!='SINGLE_GZIP':stream.close()
    return len(rows)
