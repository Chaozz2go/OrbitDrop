"""Opt-in Windows FFmpeg installer; stdlib only, no admin or PATH changes."""
import hashlib
from pathlib import Path
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from task_runtime import checkpoint, copy_stream

SOURCE = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'

def download(url, destination, progress=False):
    request=urllib.request.Request(url,headers={'User-Agent':'OrbitDrop-MediaSetup/0.4'})
    total=0
    with urllib.request.urlopen(request,timeout=60) as response, Path(destination).open('wb') as output:
        length=int(response.headers.get('Content-Length','0'))
        while block:=response.read(1024*1024):
            checkpoint(total/max(1,length)*100 if length else None,'Medienkonverter werden heruntergeladen …')
            output.write(block);total+=len(block)
            if progress and sys.stdout is not None:print(f'\rHeruntergeladen: {total/1024/1024:.0f} MiB',end='',flush=True)
    if progress and sys.stdout is not None:print()


def verify_checksum(archive_path, checksum_text):
    match=re.search(r'\b[0-9a-fA-F]{64}\b',checksum_text)
    if not match:raise ValueError('Keine SHA-256-Pruefsumme vom Anbieter erhalten.')
    digest=hashlib.sha256()
    with Path(archive_path).open('rb') as handle:
        while block:=handle.read(1024*1024):digest.update(block)
    if digest.hexdigest().lower()!=match[0].lower():
        raise ValueError('Pruefsumme stimmt nicht. Es wurde nichts installiert. Bitte erneut versuchen.')


def install_archive(archive_path, destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    # Stage both binaries completely before replacing any old files. Fixed output
    # filenames avoid extracting arbitrary ZIP paths supplied by the download.
    with tempfile.TemporaryDirectory(prefix='.orbit-media-',dir=destination) as temp:
        staged=Path(temp)
        with zipfile.ZipFile(archive_path) as archive:
            for name in ('ffmpeg.exe','ffprobe.exe'):
                entries=[entry for entry in archive.infolist() if entry.filename.replace('\\','/').endswith('/bin/'+name)]
                if len(entries)!=1 or entries[0].file_size>500*1024**2:
                    raise ValueError(name+' nicht eindeutig im Paket vorhanden.')
                with archive.open(entries[0]) as source, (staged/name).open('xb') as output:
                    copy_stream(source,output)
                with (staged/name).open('rb') as handle:
                    if handle.read(2)!=b'MZ':raise ValueError('Kein Windows-Programm: '+name)
            for label in ('LICENSE','LICENSE.txt','README.txt'):
                entries=[entry for entry in archive.infolist() if Path(entry.filename).name==label and entry.file_size<1024**2]
                if entries:
                    (staged/('FFmpeg-'+label)).write_bytes(archive.read(entries[0]))
        checkpoint(message='Medienkonverter werden eingerichtet …')
        for file in staged.iterdir():file.replace(destination/file.name)


def install_media():
    import platform
    if sys.platform!='win32' or platform.machine().lower() not in ('amd64','x86_64'):
        raise OSError('Dieses Medien-Setup benötigt Windows x64. Andere Builds bitte manuell einrichten.')
    folder=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    destination=folder/'bin'
    with tempfile.TemporaryDirectory(prefix='OrbitDrop-download-') as temp:
        root=Path(temp);archive=root/'ffmpeg.zip';checksum=root/'ffmpeg.sha256'
        download(SOURCE+'.sha256',checksum)
        download(SOURCE,archive,progress=True)
        checkpoint(message='Download wird geprüft …')
        verify_checksum(archive,checksum.read_text(encoding='utf-8-sig'))
        install_archive(archive,destination)
    return destination


def main():
    if sys.platform!='win32':
        print('Dieses Setup ist fuer Windows x64 vorgesehen.');return 1
    import platform
    if platform.machine().lower() not in ('amd64','x86_64'):
        print('Dieser Download ist fuer Windows x64. Andere Architekturen bitte manuell einrichten.');return 1
    destination=Path(__file__).resolve().parent/'bin'
    print('Installiert FFmpeg und FFprobe lokal fuer OrbitDrop.')
    print('Quelle: '+SOURCE)
    print('Download nur hier beim expliziten Aufruf dieses Setups; keine Dateien werden hochgeladen.')
    print('Bitte OrbitDrop vorher beenden. Keine Administratorrechte erforderlich.\n')
    try:
        install_media()
        print('Fertig. Jetzt Start.cmd ausfuehren und die MP4 erneut ziehen.')
        return 0
    except Exception as error:
        print('\nEinrichtung fehlgeschlagen: '+str(error))
        print('Manuell: FFmpeg/FFprobe von https://ffmpeg.org/download.html#build-windows beziehen und die beiden EXEs im Ordner bin ablegen.')
        return 1

if __name__=='__main__':sys.exit(main())
