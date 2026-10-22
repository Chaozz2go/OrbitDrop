"""Build a self-contained, searchable HTML manual from the in-app help."""
from pathlib import Path
import base64
import html
from app_version import VERSION
from preferences import DEFAULTS
from help_ui import handbook

ROOT = Path(__file__).resolve().parent
MANUAL = ROOT / 'docs' / 'OrbitDrop-Handbuch.html'


def build():
    sections = handbook(DEFAULTS, '%LOCALAPPDATA%/OrbitDrop')
    links = []; bodies = []
    illustrations = {'Bilder bearbeiten, drehen & beschriften': 'preview-photo-studio.png',
                     'Video- & Audioschnitt': 'preview-video-studio.png',
                     'PDF-Seiten & lokale OCR': 'preview-pdf-pages.png'}
    for i, (title, body) in enumerate(sections):
        anchor = 'thema-' + str(i)
        links.append('<li><a href="#' + anchor + '">' + html.escape(title) + '</a></li>')
        picture = ''
        if title in illustrations:
            path = ROOT / 'docs' / illustrations[title]
            picture = '<figure><img alt="' + html.escape(title) + ' · Programmvorschau" src="data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii') + '"><figcaption>Programmaufnahme; Dateinamen und Inhalte sind Beispieldaten.</figcaption></figure>'
        bodies.append('<section id="' + anchor + '"><h2>' + html.escape(title) + '</h2>' + body + picture + '</section>')
    document = '''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>OrbitDrop VERSION · Handbuch</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0c1420;color:#eaf2fc;font:16px/1.65 'Segoe UI',sans-serif}header{padding:35px max(24px,5vw);border-bottom:1px solid #344c66}h1{margin:0;font-size:36px}h2,h3{color:#8ce8c9;line-height:1.3}a{color:#91c9ff}code{color:#ffbe8a;overflow-wrap:anywhere}.layout{display:grid;grid-template-columns:290px minmax(0,1fr);max-width:1500px;margin:auto}nav{padding:24px;position:sticky;top:0;height:100vh;overflow:auto}nav ol{padding-left:20px}nav li{margin:10px 0}main{padding:24px 36px;min-width:0}section{padding:12px 0 32px;border-bottom:1px solid #344c66;scroll-margin-top:18px}section>h2{font-size:27px}section h2:not(:first-child){font-size:21px}input{width:100%;padding:12px;border:1px solid #43556d;border-radius:8px;color:#eaf2fc;background:#1b2b3f;font:inherit}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #43556d;padding:10px;text-align:left;vertical-align:top}img{max-width:100%;height:auto;border-radius:10px}figure{margin:24px 0}figcaption,.hint{color:#a8bed6;font-size:14px}[hidden]{display:none!important}footer{padding:30px}#empty{color:#ffbe83}@media(max-width:850px){.layout{display:block}nav{position:static;height:auto}main{padding:16px 24px}header{padding:24px}}@media print{:root{color-scheme:light}body{background:white;color:black;font-size:11pt}nav,.search,header .hint,#empty{display:none}.layout{display:block}section{break-inside:avoid}h2,h3{color:#163e35}a{color:inherit}img{max-height:500px}footer{font-size:9pt}}
</style></head><body><header><h1>OrbitDrop · Handbuch</h1><p>Version VERSION · Bedienung, Funktionen und Beispiele</p><p class="hint">Diese Datei funktioniert ohne Internet. Bilder und Suche sind enthalten. Externe Links öffnen erst durch deinen Klick.</p></header>
<div class="layout"><nav aria-label="Inhaltsverzeichnis"><label class="search" for="query">Im gesamten Handbuch suchen</label><input id="query" type="search" placeholder="Zum Beispiel schneiden, SVG, ZIP …"><ol>NAVIGATION</ol></nav><main><p id="empty" hidden>Keine passenden Themen gefunden.</p>CONTENT</main></div><footer>OrbitDrop von Chaozz2go · GNU AGPL v3. Die lokale Anleitung ist auch direkt unter Tools → Anleitung &amp; Info verfügbar.</footer>
<script>const q=document.querySelector('#query'),sections=[...document.querySelectorAll('main section')],links=[...document.querySelectorAll('nav li')];q.addEventListener('input',()=>{const words=q.value.toLocaleLowerCase('de').trim().split(/\\s+/).filter(Boolean);let count=0;sections.forEach((s,i)=>{const match=words.every(w=>s.textContent.toLocaleLowerCase('de').includes(w));s.hidden=!match;links[i].hidden=!match;if(match)count++});document.querySelector('#empty').hidden=count>0});</script></body></html>'''
    document = document.replace('VERSION', VERSION).replace('NAVIGATION', ''.join(links)).replace('CONTENT', ''.join(bodies))
    MANUAL.parent.mkdir(parents=True, exist_ok=True); MANUAL.write_text(document, encoding='utf-8')
    return MANUAL


if __name__ == '__main__':
    print(build())
