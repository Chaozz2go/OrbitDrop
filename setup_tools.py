"""Explicit setup actions and quiet, read-only readiness checks."""
import shutil,sys
from pathlib import Path
from filetypes import backend,run

TOOLS={
 'media':{'title':'Audio & Video · FFmpeg + FFprobe','purpose':'Erkennen, umwandeln, schneiden und komprimieren; Tonspuren aus Downloads erstellen. Im Windows-Paket bereits enthalten.','optional':False,'url':'https://ffmpeg.org/download.html#build-windows'},
 'office':{'title':'Office-Dokumente · LibreOffice','purpose':'Word-, Excel- und PowerPoint-Dateien sowie zusätzliche Office-Formate umwandeln und als PDF ausgeben. Nur für diese Formate nötig.','optional':True,'package':'TheDocumentFoundation.LibreOffice','url':'https://www.libreoffice.org/download/download-libreoffice/'},
 'pandoc':{'title':'Dokumente & E-Books · Pandoc','purpose':'Zusätzliche Text-, Dokument- und E-Book-Formate umwandeln, etwa Markdown, DOCX und EPUB.','optional':True,'package':'JohnMacFarlane.Pandoc','url':'https://pandoc.org/installing.html'},
 'javascript':{'title':'YouTube-Downloads · JavaScript-Laufzeit','purpose':'Deno, Node oder QuickJS hilft yt-dlp beim Lesen geschützter Player-Skripte. Für viele YouTube-Links nötig. Die Einrichtung installiert Deno.','optional':True,'package':'DenoLand.Deno','url':'https://docs.deno.com/runtime/getting_started/installation/'},
 'ocr':{'title':'Text erkennen · Deutsch & Englisch','purpose':'Lokale Texterkennung aus Bildern und gescannten PDFs. Lädt bei Bedarf nur die Sprachdaten; deine Dateien bleiben auf dem Computer. Im Windows-Paket enthalten.','optional':True,'url':'https://github.com/tesseract-ocr/tessdata_fast'},
}


def office_probe(executable,platform=None):
    if (platform or sys.platform)=='win32':
        path=Path(executable)
        console=path.with_suffix('.com')
        if console.is_file():executable=str(console)
        elif path.suffix.lower()!='.com':return None
    return [executable,'--headless','--version']


def check_tools(state_root):
    from extended import soffice
    from ocr_data import find_tessdata
    rows=[]
    for key in TOOLS:
        try:
            if key=='ocr':
                path=find_tessdata('deu+eng',state_root)
                if not path:raise OSError('Deutsche und englische Sprachdaten fehlen.')
                detail=str(path)
            else:
                if key=='media':executables=[(backend(name),['-version']) for name in ('ffmpeg','ffprobe')]
                elif key=='office':
                    path=soffice();executables=[(path,None)]
                elif key=='pandoc':executables=[(backend('pandoc'),['--version'])]
                else:
                    paths=[(backend(name),['-v'] if name=='qjs' else ['--version']) for name in ('deno','node','qjs')]
                    executables=next(([item] for item in paths if item[0]),[(None,[])])
                details=[]
                for path,args in executables:
                    if not path:raise OSError('Programm noch nicht gefunden. Einrichten oder vorhandene Installation neu prüfen.')
                    command=office_probe(path) if key=='office' else [path,*args]
                    if command is None:
                        details.append(str(path)+' · gefunden; GUI-Versionsabfrage ausgelassen.');continue
                    result=run(command,timeout=10)
                    if result.returncode:raise OSError((result.stderr or result.stdout or 'Programm konnte nicht gestartet werden.')[:800])
                    version=(result.stdout or result.stderr or 'Startbereit').splitlines()[0]
                    details.append(str(path)+'\n'+version)
                detail='\n'.join(details)
            rows.append({'id':key,'ready':True,'detail':detail})
        except Exception as error:rows.append({'id':key,'ready':False,'detail':str(error)})
    return rows


def winget_command(key):
    if key not in TOOLS or 'package' not in TOOLS[key]:raise ValueError('Unbekanntes Zusatzprogramm.')
    if sys.platform!='win32':raise OSError('Diese Einrichtung ist für Windows vorgesehen.')
    executable=shutil.which('winget')
    if not executable:raise OSError('Windows-App-Installer (winget) fehlt. Bitte die Downloadseite verwenden und danach erneut prüfen.')
    return [executable,'install','--id',TOOLS[key]['package'],'--exact','--source','winget','--silent','--disable-interactivity','--accept-package-agreements','--accept-source-agreements']


def install_tool(key,state_root):
    from task_runtime import checkpoint
    if key not in TOOLS:raise ValueError('Unbekanntes Zusatzprogramm.')
    checkpoint(0,TOOLS[key]['title']+' wird eingerichtet …')
    if key=='media':
        from media_setup import install_media
        return str(install_media())
    if key=='ocr':
        from ocr_data import install_languages
        return str(install_languages(Path(state_root)/'tessdata'))
    result=run(winget_command(key),timeout=1800)
    if result.returncode:
        raise OSError('Windows-Einrichtung nicht abgeschlossen. Eventuelle Windows-Rückfrage prüfen oder die Downloadseite verwenden.\n'+(result.stderr or result.stdout)[-1800:])
    return 'Einrichtung abgeschlossen. Status wird erneut geprüft.'
