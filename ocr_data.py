"""Pinned public Tesseract language models; documents never leave the computer."""
import hashlib,os,sys,tempfile
from pathlib import Path
from task_runtime import checkpoint

COMMIT='87416418657359cb625c412a48b6e1d6d41c29bd'
FILES={'eng.traineddata':(4113088,'bbef4675053b5b468cdb477053e28b1c698ba08e'),'deu.traineddata':(1525436,'97ed7b2b60f2771c07040660ef0f6daf596dc7bf'),'LICENSE':(11358,'d645695673349e3947e8e5ae42332d0ac3164cd7')}
LANGUAGES=('deu+eng','deu','eng')


def install_languages(folder,stopped=None):
    import requests
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.orbit-ocr-',dir=folder) as tmp:
        for index,(name,(size,expected)) in enumerate(FILES.items()):
            checkpoint(index/len(FILES)*100,'OCR-Sprachdaten: '+name)
            url=f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{COMMIT}/{name}'
            digest=hashlib.sha1(f'blob {size}\0'.encode());count=0
            with requests.get(url,timeout=(10,60),stream=True) as response:
                response.raise_for_status()
                with (Path(tmp)/name).open('xb') as output:
                    for block in response.iter_content(256*1024):
                        checkpoint()
                        if stopped and stopped.is_set():raise RuntimeError('OCR-Einrichtung abgebrochen.')
                        count+=len(block)
                        if count>size:raise ValueError('Unerwartete OCR-Dateigröße.')
                        digest.update(block);output.write(block)
            if count!=size or digest.hexdigest()!=expected:raise ValueError('OCR-Sprachdatei stimmt nicht mit dem festgelegten Original überein.')
        for name in FILES:os.replace(Path(tmp)/name,folder/name)
    return folder


def find_tessdata(language='deu+eng',state_root=None):
    if language not in LANGUAGES:raise ValueError('Bitte Deutsch, Englisch oder beide Sprachen wählen.')
    candidates=[]
    if state_root:candidates.append(Path(state_root)/'tessdata')
    if getattr(sys,'frozen',False):candidates.append(Path(getattr(sys,'_MEIPASS',Path(sys.executable).parent))/'tessdata')
    candidates.append(Path(__file__).resolve().parent/'tessdata')
    if os.environ.get('TESSDATA_PREFIX'):candidates.append(Path(os.environ['TESSDATA_PREFIX']))
    try:
        import pymupdf
        candidates.append(Path(pymupdf.get_tessdata()))
    except (RuntimeError,OSError,AttributeError,TypeError):pass
    for folder in candidates:
        if all((folder/(lang+'.traineddata')).is_file() for lang in language.split('+')):return folder
    return None
