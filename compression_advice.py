"""Read-only compression preflight; estimates never promise visual quality."""
from pathlib import Path
import tempfile
from orbit_compression import probe_media,audio_target_bitrate,video_target_bitrate


def size_text(size):
    return f'{size/1_000_000:.2f} MB' if size>=1_000_000 else f'{size/1000:.1f} KB'


def inspect_compression(files,kind,stopped):
    records=[]
    for file in files:
        if stopped.is_set():return []
        path=Path(file);record={'name':path.name,'size':path.stat().st_size}
        if kind in ('Audio','Video'):
            record['duration'],record['audio']=probe_media(path)
        elif kind=='PDF':
            import pymupdf
            with tempfile.TemporaryDirectory(prefix='orbit-pdf-check-') as temp:
                output=Path(temp)/'preview.pdf'
                with pymupdf.open(path) as pdf:
                    if pdf.needs_pass:raise ValueError(path.name+': Verschlüsseltes PDF wird nicht unterstützt.')
                    pdf.save(output,garbage=4,deflate=True,clean=True)
                record['optimized']=output.stat().st_size
        records.append(record)
    return records


def compression_advice(kind,records,p):
    if not records:return 'Vorprüfung läuft …',False
    target=int(p['target_mb']*1_000_000);notes=[];allowed=True
    if kind=='PDF':
        total=sum(r['optimized'] for r in records);before=sum(r['size'] for r in records)
        notes.append('Verlustfreie Probe: '+size_text(total)+' gesamt'+(f' · {100*(1-total/before):.0f} % kleiner.' if total<before else ' · Keine Einsparung: PDF ist bereits kompakt.'))
        if target and any(r['optimized']>target for r in records):notes.append('Zielgröße wird verlustfrei nicht erreicht. Limit erhöhen.');allowed=False
        notes.append('Der Regler setzt nur das Größenlimit; PDF-Qualität und Auflösung bleiben erhalten.')
    elif kind in ('Audio','Video'):
        rates=[]
        for record in records:
            try:
                rate=audio_target_bitrate(record['duration'],target,p['audio_kbps']) if kind=='Audio' else video_target_bitrate(record['duration'],target,record['audio']) if target else None
                if rate:rates.append(rate)
            except ValueError as error:notes.append(record['name']+': '+str(error));allowed=False
        if kind=='Audio' and rates and allowed:
            estimate=sum(r['duration']*rate*125 for r,rate in zip(records,rates))
            notes.append('Geschätzte MP3-Größe: ca. '+size_text(estimate)+' gesamt (zuzüglich kleinem Container-Overhead).')
            notes.append(f'Audio-Bitrate: {min(rates)}'+(f'–{max(rates)}' if min(rates)!=max(rates) else '')+' kbit/s.')
            if min(rates)<96:notes.append('Starke Reduktion: Musik kann hörbar leiden. Zielgröße erhöhen oder vor dem Export probehören.')
        elif kind=='Video' and rates:
            notes.append(f'Geplante Videobitrate: {min(rates)/1000:.0f}'+(f'–{max(rates)/1000:.0f}' if min(rates)!=max(rates) else '')+' kbit/s · zwei Durchläufe.')
            if min(rates)<500_000:notes.append('Sehr niedrige Bitrate: sichtbare Verluste möglich. Videohöhe reduzieren oder Zielgröße erhöhen.')
            notes.append('Die Qualität hängt von Auflösung, Bewegung und Inhalt ab; dies ist eine technische Vorprüfung.')
        elif kind=='Video' and allowed:notes.append('Dauer geprüft. Ohne Größenlimit hängt die Ergebnisgröße vom Bildinhalt und der Qualitätsstufe ab.')
    if target and any(target>=r['size'] for r in records):notes.append('Das Limit liegt bei mindestens einer Datei über der aktuellen Größe; Einsparung ist damit nicht garantiert.')
    return '\n'.join(notes),allowed
