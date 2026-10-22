"""Quiet converter probes and explanations suitable for the settings dialog."""
import sys
from pathlib import Path

PURPOSES={
    'ffmpeg':('Audio und Video','Umwandeln, schneiden und komprimieren'),
    'ffprobe':('Medienerkennung','Dauer, Tonspuren und Videoeigenschaften erkennen'),
    'pandoc':('Textdokumente und E-Books','Zusätzliche Dokumentformate umwandeln'),
    'LibreOffice':('Office-Dokumente','Zusätzliche Office-Dateien und Präsentationen umwandeln'),
}
CORE=frozenset(('ffmpeg','ffprobe'))


def probe_command(name,executable,platform=None):
    """The Windows GUI launcher can open its own console for --version."""
    platform=platform or sys.platform
    if name=='LibreOffice':
        if platform=='win32':
            path=Path(executable)
            console=path.with_suffix('.com')
            if console.is_file():path=console
            elif path.suffix.lower()!='.com':return None
            executable=str(path)
        return [executable,'--headless','--version']
    return [executable,'-version' if name.startswith('ff') else '--version']


def summary(missing):
    rows=[]
    for name,(title,purpose) in PURPOSES.items():
        status=('Nicht verfügbar' if name in CORE else 'Optionales Zusatzprogramm fehlt oder ist nicht startbereit') if name in missing else 'Bereit'
        rows.append(f'{title}: {status}\n{purpose}.')
    return '\n\n'.join(rows)
