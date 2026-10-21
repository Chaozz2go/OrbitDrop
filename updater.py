"""Public GitHub release checks and SHA-256-verified setup downloads."""
import hashlib,json,os,re,tempfile
from pathlib import Path
from urllib.parse import urlsplit
from app_version import VERSION
from task_runtime import checkpoint

REPOSITORY='Chaozz2go/OrbitDrop'
RELEASE_PAGE='https://github.com/'+REPOSITORY+'/releases'
API='https://api.github.com/repos/'+REPOSITORY+'/releases/latest'
MAX_SETUP=1_500_000_000


def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'v?\d{1,5}\.\d{1,5}\.\d{1,5}',value):raise ValueError('Ungültige Updateversion.')
    return tuple(int(part) for part in value.removeprefix('v').split('.'))


def release_info(data,current=VERSION):
    if not isinstance(data,dict) or data.get('draft') or data.get('prerelease'):raise ValueError('Kein freigegebenes Release.')
    tag=data.get('tag_name');version_tuple(tag);version=tag.removeprefix('v');filename=f'OrbitDrop-{version}-Windows-x64-Setup.exe';assets=data.get('assets',[])
    selected={}
    for name in (filename,'SHA256SUMS.txt'):
        candidates=[item for item in assets if isinstance(item,dict) and item.get('name')==name]
        if len(candidates)!=1:raise ValueError('Release enthält kein eindeutiges Windows-Setup mit Prüfsumme.')
        url=candidates[0].get('browser_download_url','');parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.netloc!='github.com' or parsed.path!=f'/{REPOSITORY}/releases/download/{tag}/{name}' or parsed.query or parsed.fragment:raise ValueError('Unzulässige Updatequelle.')
        selected[name]=url
    return {'version':version,'newer':version_tuple(tag)>version_tuple(current),'filename':filename,'setup_url':selected[filename],'checksum_url':selected['SHA256SUMS.txt'],'notes':str(data.get('body') or '')[:20000]}


def latest_release(current=VERSION):
    import requests
    try:
        response=requests.get(API,headers={'User-Agent':'OrbitDrop/'+current,'Accept':'application/vnd.github+json'},timeout=(10,30))
        if response.status_code==404:raise ValueError('Kein öffentlich erreichbares Release. Das Repository ist eventuell noch privat. Releases im Browser öffnen.')
        if response.status_code==403:raise ValueError('GitHub lehnt die Updateprüfung momentan ab (z. B. Zugriffslimit). Später erneut versuchen.')
        response.raise_for_status()
        if len(response.content)>2_000_000:raise ValueError('Updateantwort zu groß.')
        return release_info(response.json(),current)
    except requests.RequestException as error:raise OSError('Updateprüfung nicht erreichbar. Internetverbindung prüfen.') from error


def checksum_for(text,filename):
    matches=[]
    for line in text.splitlines():
        match=re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?(.+)',line.strip())
        if match and match[2]==filename:matches.append(match[1].lower())
    if len(matches)!=1:raise ValueError('Keine eindeutige SHA-256-Prüfsumme für das Setup.')
    return matches[0]


def download_release(info,state_root,progress=None,stopped=None):
    import requests
    # Validate again: no arbitrary URL or output name may enter the downloader.
    version_tuple(info['version']);filename=f"OrbitDrop-{info['version']}-Windows-x64-Setup.exe"
    for key,name in [('setup_url',filename),('checksum_url','SHA256SUMS.txt')]:
        parsed=urlsplit(info[key]);prefix=f'/{REPOSITORY}/releases/download/'
        if parsed.scheme!='https' or parsed.netloc!='github.com' or parsed.query or parsed.fragment or parsed.path not in (prefix+'v'+info['version']+'/'+name,prefix+info['version']+'/'+name):raise ValueError('Unzulässige Updatequelle.')
    if info.get('filename')!=filename:raise ValueError('Unzulässiger Update-Dateiname.')
    folder=Path(state_root)/'updates'/info['version'];folder.mkdir(parents=True,exist_ok=True);partial=None
    def check():
        checkpoint()
        if stopped and stopped.is_set():raise RuntimeError('Update-Download abgebrochen.')
    try:
        with requests.get(info['checksum_url'],timeout=(10,30),stream=True) as response:
            response.raise_for_status();checksum_data=bytearray()
            for block in response.iter_content(8192):
                check();checksum_data.extend(block)
                if len(checksum_data)>100_000:raise ValueError('Prüfsummenliste zu groß.')
        expected=checksum_for(checksum_data.decode('utf-8-sig'),filename);fd,path=tempfile.mkstemp(prefix='.download-',suffix='.part',dir=folder);partial=Path(path);digest=hashlib.sha256();size=0
        with os.fdopen(fd,'wb') as output,requests.get(info['setup_url'],timeout=(10,60),stream=True) as response:
            response.raise_for_status();total=int(response.headers.get('Content-Length','0'))
            if total>MAX_SETUP:raise ValueError('Update-Setup zu groß.')
            for block in response.iter_content(1024*1024):
                check();size+=len(block)
                if size>MAX_SETUP:raise ValueError('Update-Setup zu groß.')
                output.write(block);digest.update(block)
                if progress:progress(min(99,round(size/max(1,total)*100)) if total else 0)
        if digest.hexdigest()!=expected:raise ValueError('Prüfsumme stimmt nicht. Das Setup wird nicht gestartet.')
        with partial.open('rb') as handle:
            if handle.read(2)!=b'MZ':raise ValueError('Kein Windows-Setup erhalten.')
        target=folder/filename;os.replace(partial,target);partial=None
        return {'path':str(target),'sha256':expected,'version':info['version']}
    finally:
        if partial:partial.unlink(missing_ok=True)


def verify_installer(installer,state_root):
    version_tuple(installer['version']);path=Path(installer['path']).resolve();folder=(Path(state_root)/'updates'/installer['version']).resolve()
    if path.parent!=folder or path.name!=f"OrbitDrop-{installer['version']}-Windows-x64-Setup.exe" or path.is_symlink():raise ValueError('Unzulässiger Setup-Pfad.')
    with path.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
    if digest!=installer['sha256']:raise ValueError('Setup wurde nach dem Download verändert. Erneut herunterladen.')
    return path
