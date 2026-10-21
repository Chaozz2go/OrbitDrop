import json
import math
from pathlib import Path
import tempfile
from converter import reserve
from filetypes import backend,run,inspect_file
from task_runtime import checkpoint,copy_stream


def export_audio(source,parameters,options):
    source=Path(source).resolve();folder=Path(options.get('output_dir') or source.parent)
    if inspect_file(source).kind!='Audio':raise ValueError('Bitte genau eine Audiodatei wählen.')
    if not backend('ffmpeg') or not backend('ffprobe'):raise ValueError('FFmpeg/FFprobe fehlen.')
    probe=run([backend('ffprobe'),'-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration','-of','json',str(source)],timeout=30)
    duration=float(json.loads(probe.stdout)['format']['duration']);ranges=[tuple(map(float,r)) for r in parameters.get('ranges',[(0,duration)])]
    last=0
    if not ranges:raise ValueError('Keine Abschnitte gewählt.')
    for start,end in ranges:
        if not all(math.isfinite(x) for x in (start,end)) or start<last or end<=start or end>duration+.05:raise ValueError('Ungültige Audioabschnitte.')
        last=end
    created=[]
    try:
        with tempfile.TemporaryDirectory(prefix='orbit-audio-') as directory:
            root=Path(directory);parts=[]
            for i,(start,end) in enumerate(ranges):
                checkpoint(i/max(1,len(ranges))*80,'Audioabschnitt wird geschnitten …');part=root/f'part{i:04}.wav';parts.append(part)
                result=run([backend('ffmpeg'),'-v','error','-nostdin','-y','-protocol_whitelist','file,pipe','-ss',str(start),'-i',str(source),'-t',str(end-start),'-map','0:a:0','-vn','-ac','2','-ar','48000','-c:a','pcm_s16le',str(part)],timeout=7200,duration=end-start)
                if result.returncode:raise ValueError(result.stderr[-1000:])
            groups=[[part] for part in parts] if parameters.get('separate') else [parts]
            for i,group in enumerate(groups):
                checkpoint(85,'MP3 wird gespeichert …');manifest=root/'parts.txt';manifest.write_text(''.join(f"file '{part.name}'\n" for part in group),encoding='utf-8')
                output=reserve(source.with_name(source.stem+('_Abschnitt'+str(i+1) if parameters.get('separate') else '_Schnitt')),'.mp3',folder);created.append(output)
                result=run([backend('ffmpeg'),'-v','error','-nostdin','-y','-protocol_whitelist','file,pipe','-f','concat','-safe','1','-i',str(manifest),'-c:a','libmp3lame','-b:a','192k',str(output)],timeout=7200)
                if result.returncode or not output.stat().st_size:raise ValueError(result.stderr[-1000:] or 'Audioexport fehlgeschlagen.')
            checkpoint(100,'Audioschnitt fertig');return [str(p) for p in created]
    except BaseException:
        for p in created:p.unlink(missing_ok=True)
        raise
