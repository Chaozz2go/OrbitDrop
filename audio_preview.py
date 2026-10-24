"""Short, cancellable PCM A/B previews, with non-destructive playback matching."""
from dataclasses import dataclass
from pathlib import Path
from array import array
import json,math,shutil,sys,tempfile,wave
from audio_tools import audio_settings,render_audio
from audio_dsp import require_filters
from filetypes import backend,run
from preview_runtime import source_key
from task_runtime import checkpoint


def audio_probe(path):
    if not backend('ffmpeg') or not backend('ffprobe'):raise ValueError('FFmpeg und FFprobe fehlen. Im Dashboard unter Einrichtung prüfen.')
    result=run([backend('ffprobe'),'-v','error','-protocol_whitelist','file,pipe','-select_streams','a:0','-show_entries','format=duration:stream=channels','-of','json',str(path)],timeout=30)
    if result.returncode:raise ValueError('Audio konnte nicht geöffnet werden: '+result.stderr[-400:])
    try:
        data=json.loads(result.stdout);duration=float(data['format']['duration']);channels=int(data['streams'][0]['channels'])
        if not math.isfinite(duration) or duration<=0 or channels<1:raise ValueError()
    except (KeyError,ValueError,IndexError,TypeError):raise ValueError('Keine lesbare Audiospur mit bekannter Dauer gefunden.')
    return duration,channels

def preview_settings(values):
    # Edge operations refer to the complete file, not an arbitrary excerpt.
    p=audio_settings(values);p.update(trim=False,fade_in=0.,fade_out=0.,format='WAV');return p

def preview_key(path,values,start,length):
    p=preview_settings(values)
    return source_key('audio-ab',path,float(start),float(length),json.dumps(p,sort_keys=True))

def pcm_stats(path):
    total=0;squares=0.;peak=0
    with wave.open(str(path),'rb') as audio:
        if audio.getsampwidth()!=2:raise ValueError('Die Hörvorschau benötigt 16-Bit-PCM.')
        duration=audio.getnframes()/audio.getframerate()
        while block:=audio.readframes(32768):
            checkpoint();samples=array('h');samples.frombytes(block)
            if sys.byteorder!='little':samples.byteswap()
            total+=len(samples);squares+=sum(float(n)*n for n in samples);peak=max(peak,max((abs(n) for n in samples),default=0))
    return {'rms':math.sqrt(squares/max(1,total))/32768,'peak':peak/32768,'duration':duration}

def matched_gains(before,after):
    target=min(before,after)
    if target<1e-7:return 1.,1.
    return min(1.,target/before),min(1.,target/after)

@dataclass
class AudioPreview:
    root:Path
    before:Path
    after:Path
    key:tuple
    duration:float
    before_rms:float
    after_rms:float
    def cleanup(self):
        shutil.rmtree(self.root,ignore_errors=True);return not self.root.exists()

def build_preview(path,values,start=0.,length=15.):
    start=float(start);length=float(length)
    if not math.isfinite(start) or start<0 or not math.isfinite(length) or not .05<=length<=30:raise ValueError('Vorschau: gültigen Start und höchstens 30 Sekunden wählen.')
    p=preview_settings(values);require_filters(p);key=preview_key(path,values,start,length);duration,channels=audio_probe(path)
    if start>=duration-.02:raise ValueError('Vorschau beginnt hinter dem Ende der Datei.')
    length=min(length,duration-start);root=Path(tempfile.mkdtemp(prefix='orbit-audio-preview-'));before=root/'before.wav';after=root/'after.wav'
    try:
        checkpoint(0,'Originalausschnitt wird vorbereitet …')
        result=run([backend('ffmpeg'),'-hide_banner','-nostdin','-y','-v','error','-ss',f'{start:.6f}','-protocol_whitelist','file,pipe','-i',str(path),'-t',f'{length:.6f}','-map','0:a:0','-vn','-ac',str(1 if channels==1 else 2),'-ar','48000','-c:a','pcm_s16le','-map_metadata','-1',str(before)],timeout=120)
        if result.returncode:raise ValueError(result.stderr[-600:] or 'Originalausschnitt konnte nicht gelesen werden.')
        original=pcm_stats(before)
        if original['duration']<.02:raise ValueError('Ausschnitt ist zu kurz oder leer.')
        render_audio(before,after,p,original['duration'],codec=['-c:a','pcm_s16le'])
        processed=pcm_stats(after)
        if abs(original['duration']-processed['duration'])>.05:raise ValueError('Vorschau-Dauern stimmen nicht überein. Bitte andere Effekte oder einen anderen Ausschnitt wählen.')
        if source_key('audio-ab',path,*key[4:])!=key:raise ValueError('Quelldatei wurde während der Vorschau geändert. Bitte erneut laden.')
        checkpoint(100,'Hörvorschau bereit')
        return AudioPreview(root,before,after,key,original['duration'],original['rms'],processed['rms'])
    except Exception:shutil.rmtree(root,ignore_errors=True);raise
