"""Validated numeric audio controls shared by previews and exports."""
import math,re
from functools import lru_cache
from pathlib import Path
from filetypes import backend,run
from task_runtime import checkpoint

EQ_FREQUENCIES=(31,63,125,250,500,1000,2000,4000,8000,16000)
FX_DEFAULTS={'strength':100.,'eq_enabled':False,'eq':[0.]*10,'highpass':0.,'compressor':False,'comp_threshold':-20.,'comp_ratio':2.,'comp_attack':15.,'comp_release':180.,'comp_makeup':0.,'comp_knee':2.828,'deesser':False,'deess_intensity':.25,'deess_amount':.35,'deess_focus':.55}
FX_KEYS=tuple(FX_DEFAULTS)

def fx_settings(values):
    p={k:values.get(k,v) for k,v in FX_DEFAULTS.items()}
    for key,low,high in [('strength',0,100),('highpass',0,250),('comp_threshold',-45,0),('comp_ratio',1,8),('comp_attack',.1,100),('comp_release',10,1000),('comp_makeup',0,12),('comp_knee',1,8),('deess_intensity',0,1),('deess_amount',0,1),('deess_focus',0,1)]:
        try:value=float(p[key])
        except (ValueError,TypeError):raise ValueError('Ungültiger Audiowert: '+key)
        if not math.isfinite(value) or not low<=value<=high:raise ValueError('Ungültiger Audiowert: '+key)
        p[key]=value
    eq=p['eq']
    if not isinstance(eq,(list,tuple)) or len(eq)!=10:raise ValueError('Equalizer benötigt genau zehn Frequenzbänder.')
    p['eq']=[]
    for value in eq:
        value=float(value)
        if not math.isfinite(value) or not -12<=value<=12:raise ValueError('Equalizer: maximal ±12 dB pro Band.')
        p['eq'].append(value)
    for key in ('eq_enabled','compressor','deesser'):
        if not isinstance(p[key],bool):raise ValueError('Audio-Schalter muss true oder false sein: '+key)
    return p

def effect_filters(p):
    s=p['strength']/100
    if not s:return []
    filters=[]
    if p['highpass']:filters.append(f"highpass=f={max(1,p['highpass']*s):.5f}:p=2")
    if p['eq_enabled']:
        for frequency,gain in zip(EQ_FREQUENCIES,p['eq']):
            if gain:filters.append(f'equalizer=f={frequency}:t=o:w=1:g={gain*s:.5f}')
    if p['compressor']:
        threshold=10**(p['comp_threshold']/20);ratio=1+(p['comp_ratio']-1)*s;makeup=10**(p['comp_makeup']*s/20)
        filters.append(f"acompressor=threshold={threshold:.8f}:ratio={ratio:.6f}:attack={p['comp_attack']}:release={p['comp_release']}:makeup={makeup:.6f}:knee={p['comp_knee']}:link=maximum:detection=rms")
    if p['deesser'] and p['deess_intensity'] and p['deess_amount']:
        filters.append(f"deesser=i={p['deess_intensity']*s:.6f}:m={p['deess_amount']}:f={p['deess_focus']}:s=o")
    return filters

def parse_filter_names(text):
    # FFmpeg builds differ in status flags and in stdout/stderr routing.
    text=re.sub(r'\x1b\[[0-9;]*m','',text);names=set()
    for line in text.splitlines():
        parts=line.split()
        for i,part in enumerate(parts):
            if '->' in part and i and re.fullmatch(r'[a-z][a-z0-9_]*',parts[i-1]):names.add(parts[i-1])
    return names

@lru_cache(maxsize=4)
def _filter_names(executable,size,modified):
    result=run([executable,'-hide_banner','-filters'],timeout=30)
    if result.returncode:raise ValueError('FFmpeg-Filter konnten nicht geprüft werden.')
    return parse_filter_names(result.stdout+'\n'+result.stderr)

def require_filters(p):
    checkpoint()
    executable=backend('ffmpeg')
    if not executable:raise ValueError('FFmpeg fehlt. Im Dashboard unter Einrichtung prüfen.')
    stamp=Path(executable).stat();available=_filter_names(executable,stamp.st_size,stamp.st_mtime_ns)
    required={f.split('=',1)[0] for f in effect_filters(p)}|{'asetpts','aresample','atrim'}
    if p['normalize']:required.add('loudnorm')
    if p['protect']:required.add('alimiter')
    if p['trim']:required.add('silencedetect')
    if p['fade_in'] or p['fade_out']:required.add('afade')
    missing=required-available
    if missing:raise ValueError('Dieser FFmpeg-Build unterstützt diese Effekte nicht: '+', '.join(sorted(missing))+'. Effekte ausschalten oder FFmpeg im Dashboard aktualisieren.')
