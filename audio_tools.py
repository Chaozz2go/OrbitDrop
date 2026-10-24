"""Audio fades, edge-only silence trimming and two-pass loudness normalization."""
import json,math,os,re
from pathlib import Path
from converter import reserve
from filetypes import backend,run
from orbit_compression import probe_media
from task_runtime import checkpoint
from audio_dsp import fx_settings,effect_filters,require_filters


def audio_settings(values=None):
    if values is not None and not isinstance(values,dict):raise ValueError('Ungültige Audioeinstellungen.')
    p={'protect':False,'peak':-1.5,'normalize':True,'lufs':-16.,'trim':False,'threshold':-45.,'padding':.1,'fade_in':0.,'fade_out':0.,'format':'FLAC',**(values or {})}
    for key,low,high in [('peak',-6,-1),('lufs',-30,-10),('threshold',-80,-20),('padding',0,2),('fade_in',0,30),('fade_out',0,30)]:
        p[key]=float(p[key])
        if not math.isfinite(p[key]) or not low<=p[key]<=high:raise ValueError('Ungültiger Audiowert: '+key)
    p.update(fx_settings(p))
    for key in ('normalize','trim','protect'):
        if not isinstance(p[key],bool):raise ValueError('Audio-Schalter muss true oder false sein: '+key)
    if p['format'] not in ('WAV','FLAC','MP3'):raise ValueError('Audioausgabe: WAV, FLAC oder MP3 wählen.')
    if not (p['normalize'] or p['trim'] or p['fade_in'] or p['fade_out'] or p['protect'] or effect_filters(p)):raise ValueError('Bitte mindestens eine Audiobearbeitung wählen.')
    return p


def edge_silence(stderr,duration,padding):
    intervals=[];start=None
    for match in re.finditer(r'silence_(start|end):\s*(-?\d+(?:\.\d+)?)',stderr):
        kind,value=match[1],float(match[2])
        if kind=='start':start=max(0,value)
        elif start is not None:intervals.append((start,min(duration,value)));start=None
    if start is not None:intervals.append((start,duration))
    left,right=0.,duration
    for start,end in intervals:
        if start<=.05:left=max(0,end-padding)
        if end>=duration-.05:right=min(duration,start+padding)
    if right-left<.02:raise ValueError('Keine ausreichend hörbare Audiospur. Stille-Schwelle absenken oder Stille entfernen ausschalten.')
    return left,right


def loudness_stats(stderr):
    match=re.search(r'\{[^{}]*"input_i"[^{}]*\}',stderr,re.S)
    if not match:raise ValueError('Lautheit konnte nicht gemessen werden.')
    values=json.loads(match[0]);result={}
    for name in ('input_i','input_tp','input_lra','input_thresh','target_offset'):
        result[name]=float(values[name])
        if not math.isfinite(result[name]):raise ValueError('Lautheit ist für diese Datei nicht bestimmbar (z. B. reine Stille).')
    return result


def render_audio(source,output,p,duration,start=0.,end=None,codec=None):
    """The same DSP and two-pass normalization for preview and full export."""
    end=duration if end is None else end;length=end-start
    if p['fade_in']+p['fade_out']>length:raise ValueError('Ein-/Ausblenden ist zusammen länger als der verbleibende Ton. Zeiten verkürzen.')
    common=[backend('ffmpeg'),'-hide_banner','-nostdin','-y','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:a:0','-vn']
    filters=['asetpts=PTS-STARTPTS',f'atrim=start={start:.6f}:end={end:.6f}','asetpts=PTS-STARTPTS','aresample=48000']+effect_filters(p)
    if p['fade_in']:filters.append(f"afade=t=in:st=0:d={p['fade_in']}")
    if p['fade_out']:filters.append(f"afade=t=out:st={length-p['fade_out']:.6f}:d={p['fade_out']}")
    if p['normalize']:
        checkpoint(message='Lautheit messen · erster Durchlauf …')
        normal=f"loudnorm=I={p['lufs']}:TP={p['peak']}:LRA=11"
        measured_result=run(common+['-af',','.join(filters+[normal+':print_format=json']),'-f','null',os.devnull],timeout=7200,duration=duration)
        if measured_result.returncode:raise ValueError(measured_result.stderr[-800:] or 'Lautheitsmessung fehlgeschlagen.')
        measured=loudness_stats(measured_result.stderr)
        filters.append(normal+f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true")
    if p['protect']:
        # Oversampled lookahead with auto-makeup disabled. Output remains 48 kHz.
        filters+=['aresample=192000',f"alimiter=limit={10**(p['peak']/20):.8f}:attack=5:release=50:level=false:latency=true",'aresample=48000']
    codec=codec or {'WAV':['-c:a','pcm_s24le'],'FLAC':['-c:a','flac','-compression_level','5'],'MP3':['-c:a','libmp3lame','-b:a','192k']}[p['format']]
    checkpoint(message='Audiodatei wird berechnet …')
    result=run(common+['-loglevel','error','-af',','.join(filters),'-ar','48000','-map_metadata','-1']+codec+[str(output)],timeout=7200,duration=duration)
    if result.returncode or not Path(output).is_file() or not Path(output).stat().st_size:raise ValueError(result.stderr[-800:] or 'Audio konnte nicht erstellt werden.')
    checkpoint();return output


def improve_audio(files,values,options):
    p=audio_settings(values);require_filters(p);created=[]
    from batch_rename import signature
    try:
        for index,file in enumerate(files):
            source=Path(file);stamp=signature(source);duration,has_audio=probe_media(source)
            if not has_audio:raise ValueError('Datei enthält keine Audiospur.')
            start,end=0.,duration
            if p['trim']:
                checkpoint(index/max(1,len(files))*100,'Stille an Anfang/Ende prüfen …')
                result=run([backend('ffmpeg'),'-hide_banner','-nostdin','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:a:0','-vn','-af',f"asetpts=PTS-STARTPTS,silencedetect=noise={p['threshold']}dB:d=0.15",'-f','null',os.devnull],timeout=7200,duration=duration)
                if result.returncode:raise ValueError(result.stderr[-800:] or 'Stille-Prüfung fehlgeschlagen.')
                start,end=edge_silence(result.stderr,duration,p['padding'])
            # Validate fades before reserving any output.
            if p['fade_in']+p['fade_out']>end-start:raise ValueError('Ein-/Ausblenden ist zusammen länger als der verbleibende Ton. Zeiten verkürzen.')
            output=reserve(source.with_name(source.stem+'_Audio'+'.'+p['format'].lower()),'.'+p['format'].lower(),options.get('output_dir'));created.append(output)
            render_audio(source,output,p,duration,start,end)
            if signature(source)!=stamp:raise ValueError('Quelldatei wurde während der Bearbeitung geändert: '+source.name)
        checkpoint(100,'Audiobearbeitung fertig');return [str(path) for path in created]
    except Exception:
        for path in created:path.unlink(missing_ok=True)
        raise
