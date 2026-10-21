"""Per-user settings/history and opt-in Windows startup registration."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

DEFAULTS={'check_updates':False,'favorite_actions':[],'workflows':[],'quick_actions':[],'hidden_formats':[],'download_dir':'','output_dir':'','image_quality':92,'video_profile':'Ausgewogen','video_height':0,
          'convert_key':'Shift','edit_key':'Strg','files_key':'Alt','autostart':False,'check_backends':True}
KEY_CODES={'Shift':0x10,'Strg':0x11,'Alt':0x12}

class Preferences:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.values=DEFAULTS.copy();self.history=[]
        try:
            data=json.loads((self.root/'settings.json').read_text(encoding='utf-8'))
            if not isinstance(data,dict):raise ValueError('Ungültige Einstellungen.')
            # Old two-key setups used Ctrl for Tools; migrate to the new three-key defaults.
            if 'edit_key' not in data:data={**data,'convert_key':'Shift','edit_key':'Strg','files_key':'Alt'}
            self.values.update({key:data[key] for key in DEFAULTS if key in data})
            self.values=self.validate(self.values)
        except (OSError,ValueError,TypeError):self.values=DEFAULTS.copy()
        try:
            records=json.loads((self.root/'history.json').read_text(encoding='utf-8'))
            self.history=[dict(time=str(record.get('time','')),title=str(record.get('title','Auftrag')),outputs=[str(path) for path in record.get('outputs',[])],errors=[str(error) for error in record.get('errors',[])],status=str(record.get('status',''))) for record in records[-50:] if isinstance(record,dict) and isinstance(record.get('outputs',[]),list) and isinstance(record.get('errors',[]),list)] if isinstance(records,list) else []
        except (OSError,ValueError):pass
    def _save(self,name,data):
        fd,temp=tempfile.mkstemp(dir=self.root,prefix='.orbit-',suffix='.json')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as handle:json.dump(data,handle,ensure_ascii=False,indent=2)
            os.replace(temp,self.root/name)
        finally:Path(temp).unlink(missing_ok=True)
    def validate(self,values):
        result={key:values.get(key,value) for key,value in DEFAULTS.items()}
        keys=[result[name] for name in ('convert_key','edit_key','files_key')]
        if any(key not in KEY_CODES for key in keys):raise ValueError('Ungültige Taste.')
        if len(set(keys))!=3:raise ValueError('Konvertieren, Bearbeiten und Tools benötigen drei unterschiedliche Tasten.')
        from quick_actions import validate_presets
        result['quick_actions']=validate_presets(result['quick_actions'])
        from workflows import validate_workflows
        result['workflows']=validate_workflows(result['workflows'])
        favorites=result['favorite_actions']
        if not isinstance(favorites,list) or len(favorites)>120 or any(not isinstance(key,str) or len(key)>100 or ':' not in key for key in favorites):raise ValueError('Ungültige Favoritenliste.')
        result['favorite_actions']=list(dict.fromkeys(favorites))
        hidden=result['hidden_formats']
        if not isinstance(hidden,list) or len(hidden)>100 or any(not isinstance(value,str) or len(value)>40 for value in hidden):raise ValueError('Ungültige Formatliste.')
        result['hidden_formats']=sorted(set(hidden))
        quality=int(result['image_quality'])
        if not 10<=quality<=100:raise ValueError('Bildqualität muss zwischen 10 und 100 liegen.')
        result['image_quality']=quality
        if result['video_profile'] not in ('Hohe Qualität','Ausgewogen','Kleine Datei'):raise ValueError('Ungültige Videoqualität.')
        if int(result['video_height']) not in (0,480,720,1080,1440,2160):raise ValueError('Ungültige Videogröße.')
        result['video_height']=int(result['video_height'])
        if not isinstance(result['download_dir'],str):raise ValueError('Ungültiger Downloadordner.')
        if not isinstance(result['output_dir'],str):raise ValueError('Ungültiger Ausgabeordner.')
        for key in ('autostart','check_backends','check_updates'):result[key]=bool(result[key])
        return result
    def update(self,values):
        values=self.validate(values)
        self._save('settings.json',values);self.values=values
    def record(self,title,outputs,errors,status):
        self.history.append({'time':datetime.now().astimezone().isoformat(timespec='seconds'),'title':title,
                             'outputs':list(outputs),'errors':list(errors),'status':status})
        self.history=self.history[-50:];self._save('history.json',self.history)
    def clear_history(self):self.history=[];self._save('history.json',[])


def startup_command():
    if getattr(sys,'frozen',False):return subprocess.list2cmdline([sys.executable])
    interpreter=Path(sys.executable)
    windowless=interpreter.with_name('pythonw.exe')
    if windowless.is_file():interpreter=windowless
    return subprocess.list2cmdline([str(interpreter),str(Path(__file__).resolve().parent/'orbitdrop.py')])


def set_autostart(enabled):
    if sys.platform!='win32':
        if enabled:raise OSError('Autostart ist nur unter Windows verfügbar.')
        return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            command=startup_command()
            if len(command)>260:raise ValueError('Installationspfad ist für den Windows-Autostart zu lang.')
            winreg.SetValueEx(key,'OrbitDrop',0,winreg.REG_SZ,command)
        else:
            try:winreg.DeleteValue(key,'OrbitDrop')
            except FileNotFoundError:pass


def pressed_mode(values,states,previous):
    # A lone AltGr chord (Ctrl+Alt) must not open a palette while dragging.
    if states.get('Strg') and states.get('Alt'):return None
    for setting,mode in [('convert_key','convert'),('edit_key','edit'),('files_key','files')]:
        key=values[setting]
        if states.get(key) and not previous.get(key):return mode
    return None


def shortcut_hint(values):
    return f"{values['convert_key']}: Konvertieren · {values['edit_key']}: Bearbeiten · {values['files_key']}: Tools"
