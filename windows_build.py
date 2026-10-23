"""One Windows build path for local builds and CI, with a frozen-app smoke test."""
import argparse,hashlib,json,platform,re,shutil,subprocess,sys,zipfile
import importlib.metadata
from pathlib import Path


def collect_notices(root):
    target=root/'build'/'third-party';target.mkdir(parents=True,exist_ok=True)
    packages=[]
    for dist in importlib.metadata.distributions():
        name=dist.metadata.get('Name','unknown');version=dist.version
        packages.append(name+'=='+version)
        for file in dist.files or []:
            parts=Path(str(file)).parts
            if not any(part.endswith(('.dist-info','.egg-info')) for part in parts):continue
            if not any(token in file.name.lower() for token in ('license','copying','notice','copyright')):continue
            source=Path(dist.locate_file(file))
            if source.is_file():
                destination=target/re.sub(r'[^A-Za-z0-9_.-]','_',name)/Path(*parts[1:])
                destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
    (target/'packages.txt').write_text('\n'.join(sorted(packages))+'\n',encoding='utf-8')
    shutil.copyfile(root/'THIRD-PARTY-NOTICES.md',target/'THIRD-PARTY-NOTICES.md')
    return target


def build(onefile=False):
    if sys.platform!='win32':raise SystemExit('Windows-x64-Build muss unter Windows ausgeführt werden.')
    root=Path(__file__).resolve().parent
    version=re.search(r"StringStruct\('ProductVersion','([^']+)'",(root/'version_info.txt').read_text()).group(1)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile' if onefile else '--onedir','--windowed','--name','OrbitDrop','--version-file','version_info.txt']
    for package in ('pillow_heif','pymupdf','av','vtracer','yt_dlp','yt_dlp_ejs'):args+=['--collect-all',package]
    notices=collect_notices(root)
    args+=['--add-data','README.md;.','--add-data','LICENSE;.','--add-data',str(notices)+';third-party']
    for file in (root/'bin').glob('*'):
        if file.is_file():args+=['--add-binary' if file.suffix.lower() in ('.exe','.dll') else '--add-data',str(file)+';bin']
    if (root/'tessdata').is_dir():args+=['--add-data','tessdata;tessdata']
    args+=['orbitdrop.py'];subprocess.run(args,cwd=root,check=True)
    if onefile:return
    output=root/'dist'/'release';output.mkdir(parents=True,exist_ok=True)
    app=root/'dist'/'OrbitDrop';report=output/'windows-smoke.json'
    process=subprocess.Popen([str(app/'OrbitDrop.exe'),'--self-test',str(report)],cwd=app)
    code=process.wait(timeout=180)
    if code or not report.is_file() or not json.loads(report.read_text()).get('ok'):raise RuntimeError('Test der gebündelten EXE fehlgeschlagen. windows-smoke.json prüfen.')
    with zipfile.ZipFile(output/f'OrbitDrop-{version}-Windows-x64-Portable.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in app.rglob('*'):
            if path.is_file():archive.write(path,'OrbitDrop/'+path.relative_to(app).as_posix())
    iscc=shutil.which('ISCC.exe') or str(Path(platform_system_programs())/'Inno Setup 6'/'ISCC.exe')
    if not Path(iscc).is_file():raise RuntimeError('Inno Setup 6 fehlt. Portable ZIP liegt bereits in dist/release.')
    subprocess.run([iscc,'/DAppVersion='+version,str(root/'installer'/'OrbitDrop.iss')],cwd=root,check=True)
    checks=[]
    for path in output.iterdir():
        if path.suffix in ('.exe','.zip'):checks.append(hashlib.file_digest(path.open('rb'),'sha256').hexdigest()+'  '+path.name)
    (output/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='utf-8')
    subprocess.run([sys.executable,'-m','pip','freeze'],stdout=(output/'build-packages.txt').open('w'),check=True)
    print('Build und EXE-Test erfolgreich:',output)


def platform_system_programs():
    import os
    return os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--onefile',action='store_true');build(parser.parse_args().onefile)
