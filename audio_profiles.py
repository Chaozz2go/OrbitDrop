"""Factory tone profiles and bounded, atomically stored personal profiles."""
from copy import deepcopy
from pathlib import Path
import json,os,tempfile,uuid
from audio_dsp import FX_DEFAULTS,FX_KEYS,fx_settings

FACTORY=[
 ('neutral','Neutral / zurücksetzen','Keine Klangfärbung. Lautheit und Spitzenschutz bleiben separat wählbar.',{}),
 ('podcast','Podcast · natürlich','Klarere Sprache, sanfte Kompression und zurückhaltende S-Laut-Absenkung.',{'eq_enabled':True,'eq':[0,0,0,-2,-1,0,1,1.5,0,0],'highpass':75,'compressor':True,'comp_threshold':-20,'comp_ratio':2,'deesser':True,'deess_intensity':.2,'deess_amount':.3}),
 ('warm','Stimme · warm','Dezente Wärme und weichere Höhen; ohne Tonhöhenänderung.',{'eq_enabled':True,'eq':[0,0,1.5,.5,0,0,0,0,-1,-1],'highpass':60,'compressor':True,'comp_ratio':1.8,'deesser':True,'deess_intensity':.2}),
 ('radio','Radio · Moderation','Dichter und präsenter. Das Ausgabe-Lautheitsziel wird getrennt gewählt.',{'eq_enabled':True,'eq':[0,0,1,-1.5,-1,0,1.5,2,.5,0],'highpass':80,'compressor':True,'comp_threshold':-24,'comp_ratio':3.2,'comp_attack':8,'comp_release':140,'comp_makeup':2,'deesser':True,'deess_intensity':.35}),
 ('interview','Interview / Besprechung','Weniger Rumpeln und ausgeglichenere Sprache. Kein Rauschfilter in dieser Ausbaustufe.',{'eq_enabled':True,'eq':[0,0,0,-2,-1,0,1.5,1,0,0],'highpass':95,'compressor':True,'comp_ratio':2.5,'comp_attack':12,'comp_release':220,'deesser':True,'deess_intensity':.15}),
 ('reading','Hörbuch / Vorlesen','Natürlich und zurückhaltend für längeres Zuhören.',{'eq_enabled':True,'eq':[0,0,.5,-1,0,0,.5,0,-.5,0],'highpass':65,'compressor':True,'comp_ratio':1.6,'comp_attack':25,'comp_release':250,'deesser':True,'deess_intensity':.15}),
 ('music','Musik · sanft','Breite, dezente Klangkorrektur. Sprachfilter und Kompressor sind zunächst aus.',{'eq_enabled':True,'eq':[0,.5,.5,0,0,0,0,0,.5,.5]})]

def factory_profile(identifier):
    for key,name,hint,settings in FACTORY:
        if identifier==key:return fx_settings({**deepcopy(FX_DEFAULTS),**deepcopy(settings)})
    raise ValueError('Audio-Profil nicht gefunden.')

class AudioProfileStore:
    def __init__(self,root):self.root=Path(root);self.path=self.root/'audio-profiles.json';self.items=[];self.error='';self.load()
    def load(self):
        if not self.path.exists():return
        try:
            if self.path.stat().st_size>512*1024:raise ValueError('Profil-Datei zu groß.')
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('profiles'),list) or len(data['profiles'])>32:raise ValueError('Ungültige Profil-Datei.')
            items=[];seen=set()
            for item in data['profiles']:
                if not isinstance(item,dict) or not isinstance(item.get('id'),str) or len(item['id'])!=32 or any(c not in '0123456789abcdef' for c in item['id']) or item['id'] in seen:raise ValueError('Ungültige Profil-ID.')
                name=self.valid_name(item.get('name'));params=item.get('parameters')
                if not isinstance(params,dict):raise ValueError('Ungültige Profilwerte.')
                items.append({'id':item['id'],'name':name,'parameters':fx_settings(params)});seen.add(item['id'])
            self.items=items
        except (OSError,ValueError,TypeError) as error:self.error='Eigene Profile konnten nicht geladen werden: '+str(error)
    @staticmethod
    def valid_name(name):
        if not isinstance(name,str) or not name.strip() or len(name.strip())>60 or any(ord(c)<32 for c in name):raise ValueError('Profilname: 1 bis 60 Zeichen, ohne Steuerzeichen.')
        return name.strip()
    def save(self,items):
        if self.error:raise ValueError(self.error+' Bitte die Datei im Einstellungsordner prüfen; sie wird nicht überschrieben.')
        self.root.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix='.audio-profiles-',dir=self.root)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as handle:json.dump({'version':1,'profiles':items},handle,ensure_ascii=False,indent=2)
            os.replace(tmp,self.path);self.items=items
        finally:Path(tmp).unlink(missing_ok=True)
    def add(self,name,settings):
        name=self.valid_name(name)
        if len(self.items)>=32:raise ValueError('Maximal 32 eigene Audio-Profile.')
        if any(p['name'].casefold()==name.casefold() for p in self.items):raise ValueError('Dieser Profilname existiert bereits. Bitte einen anderen Namen wählen.')
        item={'id':uuid.uuid4().hex,'name':name,'parameters':fx_settings(settings)};self.save(self.items+[item]);return item['id']
    def remove(self,identifier):self.save([p for p in self.items if p['id']!=identifier])
