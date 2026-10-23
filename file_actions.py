"""Windows file operations. Clipboard, shell launch and move planning are separate."""
import ctypes
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from PySide6.QtCore import QMimeData, QUrl
from task_runtime import checkpoint,copy_stream

FILE_ACTIONS = ('ZIP', 'ABLAGE', 'KOPIEREN', 'VERSCHIEBEN', 'ENTPACKEN', 'PFAD', 'TERMINAL', 'EXPLORER','UMBENENNEN')
DESCRIPTIONS = {
    'UMBENENNEN': 'Dateinamen mit Vorschau und Konfliktprüfung ändern.',
    'ZIP': 'Archiv erstellen: ZIP, 7z oder TAR.GZ mit Kompression, Passwort und Zielwahl.',
    'ENTPACKEN': 'Archivinhalt ansehen, auswählen, prüfen und am gewählten Ort entpacken.',
    'ABLAGE': 'In der schwebenden Ablage parken; Originale bleiben an ihrem Ort.',
    'KOPIEREN': 'Dateien/Ordner in die Zwischenablage. Danach mit Strg+V einfügen.',
    'VERSCHIEBEN': 'Zielordner wählen und Originale dorthin verschieben.',
    'PFAD': 'Vollständige Pfade als Text kopieren, ein Pfad pro Zeile.',
    'TERMINAL': 'Terminal im Ordner öffnen. Bei Dateien: enthaltender Ordner.',
    'EXPLORER': 'Im Explorer anzeigen. Bei mehreren Dateien: beteiligte Ordner öffnen.',
}

def available_file_actions(files=None):
    from archives import archive_kind
    try:
        can_unpack=bool(files) and all(archive_kind(file) for file in files)
    except OSError:
        can_unpack=False
    return tuple(action for action in FILE_ACTIONS if (action!='ENTPACKEN' or can_unpack) and (action!='UMBENENNEN' or bool(files) and all((Path(file).is_file() or Path(file).is_dir()) and not Path(file).is_symlink() for file in files)))

def paths_from_urls(urls):
    if not urls or not all(url.isLocalFile() for url in urls):
        raise ValueError('Nur lokale Dateien und Ordner werden unterstützt.')
    return validate_paths([url.toLocalFile() for url in urls])

def validate_paths(files):
    result=[]; seen=set()
    for file in files:
        path=Path(os.path.abspath(file))
        if not path.exists() or not (path.is_file() or path.is_dir()):
            raise ValueError(f'Nicht mehr verfügbar: {path}')
        key=os.path.normcase(str(path))
        if key not in seen:
            seen.add(key);result.append(path)
    if not result:
        raise ValueError('Keine Dateien ausgewählt.')
    return result

def file_mime(files):
    paths=validate_paths(files)
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    # Qt translates local URLs into CF_HDROP for native Explorer paste/drop.
    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"',struct.pack('<I',1))
    return mime

def copy_paths_text(files):
    return '\n'.join(str(path) for path in validate_paths(files))

def containing_folders(files):
    result=[]
    for path in validate_paths(files):
        folder=path if path.is_dir() else path.parent
        if folder not in result:result.append(folder)
    return result

def terminal_commands(files):
    if sys.platform != 'win32':
        raise OSError('Terminal-Aktion ist für Windows implementiert.')
    executable=shutil.which('wt.exe')
    if executable:
        return [([executable,'-d',str(folder)],str(folder)) for folder in containing_folders(files)]
    powershell=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    if not powershell.is_file():
        raise OSError('Windows Terminal/PowerShell nicht gefunden.')
    # Use cwd rather than interpolating a path into PowerShell command text.
    return [([str(powershell),'-NoLogo','-NoExit'],str(folder)) for folder in containing_folders(files)]

def open_terminals(files):
    for args,folder in terminal_commands(files):
        subprocess.Popen(args,cwd=folder,creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0))

def explorer_commands(files):
    if sys.platform != 'win32':
        raise OSError('Explorer-Aktion ist nur unter Windows verfügbar.')
    paths=validate_paths(files)
    executable=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'explorer.exe')
    if len(paths)==1:
        path=paths[0]
        return [[executable,str(path)]] if path.is_dir() else [[executable,'/select,',str(path)]]
    # Open each containing folder once. Avoid one Explorer window per file.
    return [[executable,str(folder)] for folder in containing_folders(paths)]

def show_in_explorer(files):
    for args in explorer_commands(files):
        subprocess.Popen(args)


def plan_moves(files, destination):
    paths=validate_paths(files)
    root=Path(os.path.abspath(destination))
    if not root.is_dir():
        raise ValueError('Der Zielordner existiert nicht.')
    plans=[];names=set()
    for source in paths:
        if not source.name or source.parent==source:
            raise ValueError('Laufwerkswurzeln können nicht verschoben werden.')
        target=root/source.name
        name=os.path.normcase(source.name)
        if name in names:
            raise ValueError('Mehrere Quellen haben denselben Namen: '+source.name)
        names.add(name)
        if os.path.lexists(target):
            raise FileExistsError('Ziel existiert bereits; es wird nichts überschrieben: '+str(target))
        if source.is_dir():
            real_source,real_root=source.resolve(),root.resolve()
            if real_root==real_source or real_source in real_root.parents:
                raise ValueError('Ein Ordner kann nicht in sich selbst verschoben werden.')
        if any(source!=other and source in other.parents for other in paths):
            raise ValueError('Elternordner und darin enthaltene Dateien bitte getrennt auswählen.')
        plans.append((source,target))
    return plans


def _copy_then_remove(source, target):
    if source.is_symlink():
        os.symlink(os.readlink(source),target,target_is_directory=source.is_dir())
        source.unlink()
    elif source.is_dir():
        # copytree creates the target exclusively. Only delete the original after
        # the complete copy succeeds; on failure preserve source and partial target.
        shutil.copytree(source,target,symlinks=True)
        checkpoint(message='Ordner kopiert; Quelle wird entfernt …')
        shutil.rmtree(source)
    else:
        # Exclusive open prevents replacing an output created after preflight.
        with source.open('rb') as input_file:
            output_file=target.open('xb')
            try:
                with output_file:
                    copy_stream(input_file,output_file,source.stat().st_size)
                shutil.copystat(source,target)
            except Exception:
                target.unlink(missing_ok=True)
                raise
        source.unlink()


def move_one(source, target):
    if os.path.lexists(target):
        raise FileExistsError('Ziel wurde inzwischen angelegt: '+str(target))
    if sys.platform=='win32':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        move=kernel.MoveFileExW
        move.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]
        move.restype=ctypes.c_int
        # Never set MOVEFILE_REPLACE_EXISTING. Directory cross-volume moves use
        # the explicit fallback below; Windows only moves directories in-volume.
        flags=0 if source.is_dir() else 2
        if move(str(source),str(target),flags):
            if os.path.lexists(source):
                raise OSError('Ziel wurde angelegt, aber die Quelle ist noch vorhanden. Bitte beide Speicherorte prüfen.')
            return
        error=ctypes.get_last_error()
        if not (source.is_dir() and error==17):
            raise ctypes.WinError(error)
    _copy_then_remove(source,target)


def execute_moves(plans):
    outputs=[];errors=[]
    for source,target in plans:
        try:
            checkpoint(message='Verschieben: '+source.name)
            move_one(source,target);outputs.append(str(target))
        except Exception as error:
            errors.append(f'{source.name}: {error}')
            # Stop after an actual error so the remaining selection stays put.
            break
    return outputs,errors
