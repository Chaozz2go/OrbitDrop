"""Inspect content, and offer only conversions with available local backends."""
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from PIL import Image

@dataclass(frozen=True)
class FileInfo:
    kind: str
    actions: tuple[str, ...]
    message: str = ''

def backend(name):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    folders = [base / 'bin', Path(__file__).resolve().parent / 'bin']
    if getattr(sys, 'frozen', False):
        folders.insert(0,Path(sys.executable).resolve().parent / 'bin')
    executable = name + ('.exe' if sys.platform == 'win32' else '')
    if sys.platform == 'win32':
        local = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))
        folders += [local/'Microsoft/WinGet/Links']
        for env in ('PROGRAMFILES','PROGRAMFILES(X86)'):
            root=Path(os.environ.get(env,'C:/Program Files'))
            folders += [root/'ffmpeg/bin',root/'FFmpeg/bin']
    for folder in folders:
        candidate = folder / executable
        if candidate.is_file():
            return str(candidate)
    found=shutil.which(name)
    if found:return found
    if sys.platform=='win32' and name in ('ffmpeg','ffprobe'):
        # A running process does not see PATH updates made by a new installer.
        # Search WinGet's package directories without requiring a Windows reboot.
        packages=local/'Microsoft/WinGet/Packages'
        if packages.is_dir():
            for package in packages.glob('Gyan.FFmpeg*'):
                for candidate in package.glob('*/bin/'+executable):
                    if candidate.is_file():return str(candidate)
    return None


def media_signature(header):
    if len(header)>=12 and header[4:8]==b'ftyp':
        return 'MP4/MOV'
    if header.startswith(b'\x1aE\xdf\xa3'):
        return 'MKV/WebM'
    if header.startswith(b'RIFF') and header[8:12]==b'AVI ':
        return 'AVI'
    if header.startswith((b'GIF87a',b'GIF89a')):
        return 'GIF'
    if header.startswith(b'fLaC'):
        return 'FLAC'
    if header.startswith(b'OggS'):
        return 'Ogg/Opus'
    if header.startswith(b'ID3'):
        return 'MP3'
    return None

def run(args, timeout=10, duration=None):
    from task_runtime import run_process
    return run_process(args, timeout=timeout, duration=duration)

@lru_cache(maxsize=4)
def encoders(executable):
    result = run([executable, '-hide_banner', '-encoders'])
    if result.returncode:
        return set()
    return {parts[1] for line in result.stdout.splitlines() if len(parts := line.split()) >= 2 and len(parts[0]) == 6}

def inspect_file(filename):
    path = Path(filename)
    if not path.is_file():
        return FileInfo('Unbekannt', (), 'Nur lokale Dateien werden unterstützt.')
    from extended import image_actions, identify_extra
    supported_images = image_actions()
    try:
        with Image.open(path) as image:
            if getattr(image, 'n_frames', 1) > 1:
                if image.format == 'GIF':
                    raise ValueError('Animated GIF: use media backend')
                return FileInfo('Bild', (), 'Animationen und mehrseitige Bilder noch nicht unterstützt.')
            image.verify()
        return FileInfo('Bild', supported_images)
    except Exception:
        pass
    with path.open('rb') as handle:
        header = handle.read(1024)
    if header.startswith(b'%PDF-'):
        try:
            import pymupdf
            with pymupdf.open(path) as pdf:
                if pdf.needs_pass:
                    return FileInfo('PDF', (), 'Verschlüsselte PDFs werden nicht unterstützt.')
            return FileInfo('PDF', ('DOCX','PPTX','XLSX','JPG','PNG','EPUB','TXT','MD'),
                            'Bilder: alle Seiten als ZIP, 300 DPI. Office: vereinfachter Export, keine OCR.')
        except ImportError:
            return FileInfo('PDF', (), 'PDF-Modul fehlt. Start.cmd erneut einrichten.')
        except Exception:
            return FileInfo('PDF', (), 'PDF kann nicht gelesen werden.')
    extra = identify_extra(path, header)
    if extra is not None:
        return extra
    media_kind = media_signature(header)
    ffprobe, ffmpeg = backend('ffprobe'), backend('ffmpeg')
    if not (ffprobe and ffmpeg):
        missing=', '.join(name for name,value in [('ffmpeg.exe',ffmpeg),('ffprobe.exe',ffprobe)] if not value)
        return FileInfo(media_kind or 'Unbekannt', (), f'Medienkonverter fehlt: {missing}. Medien-einrichten.cmd starten, danach OrbitDrop neu starten.')
    if ffprobe and ffmpeg:
        try:
            result = run([ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe',
                          '-show_streams', '-of', 'json', str(path.resolve())], timeout=30)
            if result.returncode:
                return FileInfo(media_kind or 'Unbekannt', (), 'FFprobe kann die Datei nicht lesen: '+result.stderr.strip()[-180:])
            streams = json.loads(result.stdout).get('streams', []) if result.returncode == 0 else []
            video = any(s.get('codec_type') == 'video' and s.get('codec_name') and s.get('width', 0) > 0 and s.get('height', 0) > 0 and not s.get('disposition', {}).get('attached_pic') for s in streams)
            audio = any(s.get('codec_type') == 'audio' and s.get('codec_name') and int(s.get('sample_rate', 0)) > 0 and s.get('channels', 0) > 0 for s in streams)
            available = encoders(ffmpeg)
            actions = []
            if video:
                if {'libx264', 'aac'} <= available:
                    actions.append('MP4')
                if {'libvpx-vp9', 'libopus'} <= available:
                    actions.append('WEBM')
                for action, needed in [('MOV', {'libx264','aac'}), ('MKV', {'libx264','aac'}), ('AVI', {'mpeg4','libmp3lame'}), ('WMV', {'wmv2','wmav2'}), ('GIF', {'gif'})]:
                    if needed <= available:
                        actions.append(action)
                if 'png' in available:
                    actions.append('STANDBILD')
            if audio:
                for action, encoder in [('MP3', 'libmp3lame'), ('M4A', 'aac'), ('WAV', 'pcm_s16le'), ('FLAC', 'flac'), ('OGG', 'libvorbis'), ('OPUS', 'libopus'), ('AIFF', 'pcm_s16be'), ('WMA', 'wmav2')]:
                    if encoder in available:
                        actions.append(action)
            if video or audio:
                return FileInfo('Video' if video else 'Audio', tuple(actions), '' if actions else 'Medien erkannt, aber dieser FFmpeg-Build hat keine passenden Ausgabe-Encoder.')
        except subprocess.TimeoutExpired:
            return FileInfo(media_kind or 'Unbekannt', (), 'Medienprüfung hat das Zeitlimit erreicht. Datei ggf. zuerst vollständig lokal speichern.')
        except (OSError, ValueError) as error:
            return FileInfo(media_kind or 'Unbekannt', (), 'Medienprüfung fehlgeschlagen: '+str(error)[-180:])
    message = 'Für Audio/Video ffmpeg.exe und ffprobe.exe im Ordner bin ablegen.' if not (ffprobe and ffmpeg) else 'Kein unterstützter Dateiinhalt erkannt.'
    return FileInfo('Unbekannt', (), message)

def common_actions(files):
    if not files:
        return (), 'Datei ziehen', 'Warte auf Dateien'
    infos = [inspect_file(file) for file in files]
    actions = tuple(a for a in infos[0].actions if all(a in info.actions for info in infos))
    kind = infos[0].kind if all(i.kind == infos[0].kind for i in infos) else 'Gemischte Auswahl'
    if not actions:
        return (), kind, next((i.message for i in infos if i.message), 'Keine gemeinsame Aktion verfügbar.')
    return actions, kind, f'{len(files)} Datei(en) erkannt'
