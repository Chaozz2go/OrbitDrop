"""Local structured data inspection, precise diagnostics and explicit conversions."""
from dataclasses import dataclass
from decimal import Decimal
from datetime import date,datetime,time
from pathlib import Path
import csv,io,re
try:import tomllib
except ImportError:import tomli as tomllib
import simplejson as json
from task_runtime import checkpoint

MAX_TEXT=8*1024*1024
STRUCTURED={'JSON','YAML','TOML','XML','JSONL'}
TEXT_EXT={'.txt','.conf','.cfg','.ini','.env','.properties','.ps1','.psm1','.py','.sh','.bat','.cmd','.sql','.js','.ts','.css','.html','.md','.rst','.xml','.json','.yaml','.yml','.toml','.csv','.tsv','.log','.jsonl','.ndjson'}
DATA_EXT={'.json':'JSON','.yaml':'YAML','.yml':'YAML','.toml':'TOML','.xml':'XML','.csv':'CSV','.tsv':'TSV','.jsonl':'JSONL','.ndjson':'JSONL','.log':'LOG'}
CERT_EXT={'.pem','.crt','.cer','.der','.pfx','.p12'}

@dataclass
class DataProblem(ValueError):
    message:str
    line:int=1
    column:int=1
    position:int=0
    def __str__(self):return f'Zeile {self.line}, Spalte {self.column}: {self.message}'

def problem(text,message,pos=0):
    pos=max(0,min(len(text),pos));return DataProblem(message,text.count('\n',0,pos)+1,pos-text.rfind('\n',0,pos),pos)

def read_text(path,encoding='auto',limit=MAX_TEXT):
    path=Path(path)
    with path.open('rb') as f:raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError(f'Datei zu groß für diesen Editor (max. {limit//1024//1024} MiB). Für Logs den Log-Viewer verwenden.')
    if encoding=='auto':
        encoding='utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
    try:text=raw.decode(encoding)
    except UnicodeError as e:raise ValueError('Zeichenkodierung nicht lesbar. Im Textwerkzeug die richtige Eingangskodierung wählen.') from e
    if '\x00' in text:raise ValueError('NUL-Zeichen gefunden; bitte Kodierung prüfen. Binärdateien nicht als Text bearbeiten.')
    return text,encoding

def kind_for(path):
    path=Path(path);ext=path.suffix.lower()
    if ext in CERT_EXT:return 'Zertifikat'
    if ext in DATA_EXT:return DATA_EXT[ext]
    if ext in TEXT_EXT or path.name.lower() in ('dockerfile','makefile','.env','.gitignore'):return 'Text'
    return None

def _json_duplicates(text):
    stack=[]
    for match in re.finditer(r'"(?:[^"\\]|\\.)*"|[{}\[\],:]|[^\s{}\[\],:]+',text):
        token=match.group()
        if token=='{':stack.append({'keys':{},'key':True})
        elif token=='[':stack.append(None)
        elif token in ('}',']'):stack.pop()
        elif stack and stack[-1] is not None:
            current=stack[-1]
            if token==',':current['key']=True
            elif token==':':current['key']=False
            elif token.startswith('"') and current['key']:
                key=json.loads(token)
                if key in current['keys']:raise problem(text,f'Doppelter Schlüssel {key!r}. Werte würden sich gegenseitig ersetzen. Einen Schlüssel ändern oder entfernen.',match.start())
                current['keys'][key]=match.start()

def _bounded(value,depth=0,counter=None):
    counter=counter if counter is not None else [0];counter[0]+=1
    if depth>64 or counter[0]>100000:raise ValueError('Datenstruktur zu groß oder zu tief (max. 64 Ebenen / 100000 Werte).')
    if isinstance(value,dict):
        for k,v in value.items():
            if not isinstance(k,str):raise ValueError('Für den Datenaustausch müssen Objektschlüssel Text sein.')
            _bounded(v,depth+1,counter)
    elif isinstance(value,list):
        for v in value:_bounded(v,depth+1,counter)
    elif isinstance(value,Decimal):
        if not value.is_finite():raise ValueError('NaN und Infinity sind für diese Umwandlung nicht erlaubt.')
    elif isinstance(value,float):
        import math
        if not math.isfinite(value):raise ValueError('NaN und Infinity sind für diese Umwandlung nicht erlaubt.')
    elif value is not None and not isinstance(value,(str,bool,int,date,datetime,time)):raise ValueError('Dieser Datentyp wird nicht unterstützt: '+type(value).__name__)
    return value

def _yaml():
    from ruamel.yaml import YAML
    y=YAML(typ='safe',pure=True);y.version=(1,2);y.allow_duplicate_keys=False
    y.constructor.add_constructor('tag:yaml.org,2002:float',lambda loader,node:Decimal(loader.construct_scalar(node).replace('_','')))
    y.representer.add_representer(Decimal,lambda dumper,value:dumper.represent_scalar('tag:yaml.org,2002:float',str(value)))
    y.width=100;y.default_flow_style=False
    return y

def _xml_value(node):
    return {'tag':node.tag,'attributes':dict(node.attrib),'text':node.text,'tail':node.tail,'children':[_xml_value(c) for c in node]}

def parse(text,kind):
    if len(text.encode('utf-8'))>MAX_TEXT:raise ValueError('Daten zu groß (max. 8 MiB).')
    checkpoint(message='Struktur wird geprüft …')
    try:
        if kind=='JSON':
            value=json.loads(text,use_decimal=True,allow_nan=False);_json_duplicates(text)
        elif kind=='JSONL':
            value=[];offset=0
            lines=text.split('\n')
            for n,content in enumerate(lines,1):
                line=content+('\n' if n<len(lines) else '')
                checkpoint(message=f'JSONL · Zeile {n}')
                if line.strip():
                    try:value.append(parse(line,'JSON'))
                    except DataProblem as e:raise problem(text,e.message,offset+e.position)
                offset+=len(line)
        elif kind=='YAML':
            from ruamel.yaml.tokens import AliasToken,AnchorToken,TagToken
            y=_yaml();depth=0
            for index,token in enumerate(y.scan(text)):
                if index>200000:raise ValueError('Zu viele YAML-Elemente.')
                if isinstance(token,(AliasToken,AnchorToken,TagToken)):raise problem(text,'YAML-Anker, Aliase und explizite Tags werden hier nicht umgewandelt. So bleiben Verweise und Sondertypen unverändert.',token.start_mark.index)
                name=type(token).__name__
                if name in ('BlockMappingStartToken','BlockSequenceStartToken','FlowMappingStartToken','FlowSequenceStartToken'):depth+=1
                elif name in ('BlockEndToken','FlowMappingEndToken','FlowSequenceEndToken'):depth-=1
                if depth>64:raise ValueError('YAML ist zu tief verschachtelt.')
            value=y.load(text)
        elif kind=='TOML':value=tomllib.loads(text,parse_float=Decimal)
        elif kind=='XML':
            if re.search(r'<!\s*(DOCTYPE|ENTITY)',text,re.I):raise problem(text,'XML-DTDs und Entities werden nicht geladen.',text.find('<!'))
            from defusedxml import ElementTree
            depth=0
            for event,node in ElementTree.iterparse(io.StringIO(text),events=('start','end')):
                depth+=1 if event=='start' else -1
                if depth>48:raise ValueError('XML ist zu tief verschachtelt.')
            value=_xml_value(ElementTree.fromstring(text))
        elif kind in ('CSV','TSV'):return read_table(text,kind)
        else:raise ValueError('Kein unterstütztes Datenformat: '+kind)
        return _bounded(value)
    except DataProblem:raise
    except json.JSONDecodeError as e:
        message=e.msg
        if message.startswith("Expecting ',' delimiter"):message="Expecting ',' delimiter"
        if message.startswith("Expecting property name enclosed in double quotes"):message="Expecting property name enclosed in double quotes"
        explanation={'Expecting \',\' delimiter':'Zwischen zwei Einträgen fehlt vermutlich ein Komma. Die Ursache kann unmittelbar vor der markierten Stelle liegen.',"Expecting ':' delimiter":'Nach einem Schlüssel fehlt ein Doppelpunkt.', 'Expecting property name enclosed in double quotes':'Hier wird ein Schlüssel in doppelten Anführungszeichen erwartet. Prüfe auch ein überflüssiges Komma davor.','Expecting value':'Hier fehlt ein Wert oder es steht ein unerlaubtes Zeichen. JSON verwendet true, false und null in Kleinbuchstaben.','Extra data':'Nach dem JSON-Dokument folgen weitere Zeichen oder ein zweites Dokument.'}.get(message,'JSON-Syntaxfehler: '+e.msg)
        raise problem(text,explanation,e.pos) from e
    except Exception as e:
        mark=getattr(e,'problem_mark',None)
        if mark is not None:
            detail=str(getattr(e,'problem',str(e)))
            if type(e).__name__=='DuplicateKeyError':detail='Doppelter Schlüssel. Jeder Schlüssel darf in einem Objekt nur einmal vorkommen.'
            else:detail='Einrückung, Doppelpunkt oder Wert prüfen. '+detail
            raise problem(text,'YAML: '+detail,mark.index) from e
        if isinstance(e,tomllib.TOMLDecodeError):
            pos=getattr(e,'pos',None);m=re.search(r'\(at line (\d+), column (\d+)\)',str(e))
            if pos is None and m:pos=sum(len(v) for v in text.splitlines(keepends=True)[:int(m[1])-1])+int(m[2])-1
            raise problem(text,'TOML: '+str(e),len(text) if pos is None else pos) from e
        if hasattr(e,'position'):
            line,column=e.position;pos=sum(len(v) for v in text.splitlines(keepends=True)[:line-1])+column
            detail='Öffnendes und schließendes Element passen nicht zusammen.' if 'mismatched tag' in str(e) else 'XML-Struktur oder Zeichen prüfen.'
            raise problem(text,detail+' '+str(e),pos) from e
        raise

def json_repair(text):
    """Only propose one unambiguous punctuation change that passes strict parsing."""
    try:parse(text,'JSON');return None
    except DataProblem as issue:pass
    except Exception:return None
    try:json.loads(text,use_decimal=True,allow_nan=False)
    except json.JSONDecodeError as e:
        candidates=[]
        if e.msg.startswith("Expecting ',' delimiter"):
            position=e.pos
            while position>0 and text[position-1].isspace():position-=1
            candidates.append(('Fehlendes Komma ergänzen',text[:position]+','+text[position:]))
        if e.msg=="Expecting ':' delimiter":candidates.append(('Fehlenden Doppelpunkt ergänzen',text[:e.pos]+':'+text[e.pos:]))
        if e.pos<len(text) and text[e.pos] in '}]':
            before=e.pos-1
            while before>=0 and text[before].isspace():before-=1
            if before>=0 and text[before]==',':candidates.append(('Überflüssiges letztes Komma entfernen',text[:before]+text[before+1:]))
        if e.pos>=len(text.rstrip()) and not e.msg.startswith('Unterminated'):
            stack=[]
            for token in re.findall(r'"(?:[^"\\]|\\.)*"|[{}\[\]]',text):
                if token in ('{','['):stack.append('}' if token=='{' else ']')
                elif token in ('}',']'):
                    if not stack or stack.pop()!=token:stack=[];break
            if stack:candidates.append(('Fehlende schließende Klammer ergänzen',text+''.join(reversed(stack))))
        for title,candidate in candidates:
            try:parse(candidate,'JSON');return title,candidate
            except Exception:pass
    return None

def read_table(text,kind='CSV',delimiter=None):
    delimiter=delimiter or ('\t' if kind=='TSV' else None)
    if delimiter is None:
        try:delimiter=csv.Sniffer().sniff(text[:8192],delimiters=',;\t|').delimiter
        except csv.Error:delimiter=','
    if delimiter not in (',',';','\t','|'):raise ValueError('Ungültiges Trennzeichen.')
    rows=[];positions=[];cells=0;reader=csv.reader(io.StringIO(text,newline=''),delimiter=delimiter,strict=True)
    try:
        while True:
            start_line=reader.line_num
            try:row=next(reader)
            except StopIteration:break
            checkpoint(message='Tabellenzeilen werden geprüft …');cells+=len(row)
            if cells>100000:raise ValueError('Tabelle zu groß (max. 100000 Zellen). Für große Exporte zuerst einen Ausschnitt verwenden.')
            rows.append(row);positions.append(start_line)
            if len(rows)>100000 or len(row)>1000:raise ValueError('Tabelle zu groß.')
    except csv.Error as e:
        offset=sum(len(line) for line in text.splitlines(keepends=True)[:max(0,reader.line_num-1)])
        raise problem(text,'CSV: Anführungszeichen oder Trennzeichen prüfen. '+str(e),offset) from e
    if not rows:raise ValueError('Die Tabelle ist leer.')
    header=rows[0]
    if not header or any(not v for v in header) or len(set(header))!=len(header):raise problem(text,'CSV braucht eindeutige, nicht leere Spaltennamen in der ersten Zeile.')
    for index,row in enumerate(rows[1:],1):
        if len(row)!=len(header):
            offset=sum(len(line) for line in text.splitlines(keepends=True)[:positions[index]])
            raise problem(text,'Zeile hat eine andere Spaltenzahl als die Kopfzeile. Trennzeichen prüfen.',offset)
    return [dict(zip(header,row)) for row in rows[1:]]

def records(value,path=''):
    if path:
        if not path.startswith('/'):raise ValueError('JSON-Pointer muss mit / beginnen.')
        for part in path[1:].split('/'):
            if re.search(r'~(?![01])',part):raise ValueError('Ungültige JSON-Pointer-Escape-Sequenz.')
            part=part.replace('~1','/').replace('~0','~')
            try:
                if isinstance(value,list):
                    if not re.fullmatch(r'0|[1-9][0-9]*',part):raise ValueError('Ungültiger Listenindex.')
                    value=value[int(part)]
                else:value=value[part]
            except (KeyError,IndexError,TypeError):raise ValueError('Dieser JSON-Pointer ist nicht in den Daten vorhanden.')
    if not isinstance(value,list) or not value or any(not isinstance(r,dict) for r in value):raise ValueError('Für CSV eine nicht leere Liste von Objekten auswählen (JSON-Pointer, z. B. /daten).')
    keys=list(value[0]);expected=set(keys)
    if not keys or any(set(row)!=expected for row in value):raise ValueError('CSV benötigt Datensätze mit denselben Spalten.')
    if any(isinstance(v,(dict,list)) or v is None for row in value for v in row.values()):raise ValueError('Verschachtelte Werte oder null können nicht verlustfrei als CSV dargestellt werden. Einen anderen Teil auswählen.')
    return value,keys

def _json_compatible(value):
    if isinstance(value,(datetime,date,time)):raise ValueError('Datums-/Zeitwerte sind eigene TOML-/YAML-Typen. Für JSON vorab ausdrücklich in Text ändern.')
    if isinstance(value,dict):return {k:_json_compatible(v) for k,v in value.items()}
    if isinstance(value,list):return [_json_compatible(v) for v in value]
    return value

def serialize(value,target,compact=False,sort=False,delimiter=','):
    _bounded(value)
    if sort:
        def ordered(v):return {k:ordered(v[k]) for k in sorted(v)} if isinstance(v,dict) else [ordered(x) for x in v] if isinstance(v,list) else v
        value=ordered(value)
    if target in ('JSON','JSONL'):
        value=_json_compatible(value)
        kw=dict(ensure_ascii=False,use_decimal=True,allow_nan=False)
        if target=='JSONL':
            if not isinstance(value,list):raise ValueError('JSONL benötigt eine Liste von Einträgen.')
            return ''.join(json.dumps(row,**kw,separators=(',',':'))+'\n' for row in value)
        result=json.dumps(value,**kw,indent=None if compact else 2,separators=(',',':') if compact else None)+'\n'
        return re.sub('[\ud800-\udfff]',lambda m:'\\u'+format(ord(m.group()),'04x'),result)
    if target=='YAML':
        out=io.StringIO();_yaml().dump(value,out);return out.getvalue()
    if target=='TOML':
        import tomli_w
        if not isinstance(value,dict):raise ValueError('TOML benötigt ein Objekt als Wurzel.')
        try:return tomli_w.dumps(value)
        except (TypeError,ValueError) as e:raise ValueError('Nicht als TOML darstellbar (z. B. null): '+str(e)) from e
    if target=='XML':
        from xml.etree import ElementTree as ET
        def node(v):
            if not isinstance(v,dict) or set(v)!={'tag','attributes','text','tail','children'}:raise ValueError('XML benötigt die Struktur tag / attributes / text / tail / children. Es werden keine XML-Elementnamen geraten.')
            if not isinstance(v['tag'],str) or not re.fullmatch(r'(?:\{[^{}]+\})?[A-Za-z_][\w.:-]*',v['tag']):raise ValueError('Ungültiger XML-Elementname.')
            if not isinstance(v['attributes'],dict) or any(not isinstance(k,str) or not isinstance(val,str) for k,val in v['attributes'].items()):raise ValueError('XML-Attribute müssen Text sein.')
            if v['text'] is not None and not isinstance(v['text'],str) or v['tail'] is not None and not isinstance(v['tail'],str):raise ValueError('XML-Text muss Text oder null sein.')
            e=ET.Element(v['tag'],v['attributes']);e.text=v['text'];e.tail=v['tail']
            if not isinstance(v['children'],list):raise ValueError('XML children muss eine Liste sein.')
            e.extend(node(c) for c in v['children']);return e
        root=node(value)
        mixed=any(len(n) and n.text and n.text.strip() or any(c.tail and c.tail.strip() for c in n) or n.attrib.get('{http://www.w3.org/XML/1998/namespace}space')=='preserve' for n in root.iter())
        if not compact and not mixed:ET.indent(root,space='  ')
        result=ET.tostring(root,encoding='unicode');parse(result,'XML');return result
    if target in ('CSV','TSV'):
        rows,keys=records(value);out=io.StringIO(newline='');writer=csv.writer(out,delimiter='\t' if target=='TSV' else delimiter,lineterminator='\n');writer.writerow(keys)
        for row in rows:writer.writerow([str(row[k]).lower() if isinstance(row[k],bool) else str(row[k]) for k in keys])
        return out.getvalue()
    raise ValueError('Unbekanntes Zielformat.')

def available_targets(value,kind):
    result=[]
    for target in ('JSON','YAML','TOML','XML','CSV','TSV','JSONL'):
        try:serialize(value,target).encode('utf-8');result.append(target)
        except (ValueError,TypeError,OverflowError):pass
    return tuple(result)

def data_info(path):
    kind=kind_for(path)
    if kind is None:return None
    from filetypes import FileInfo
    if kind=='Zertifikat':
        targets=()
        if Path(path).suffix.lower() not in ('.pfx','.p12'):
            try:
                from admin_tools import load_certificates
                certs=load_certificates(path);targets=('PEM','DER') if len(certs)==1 else ('PEM',)
            except (ValueError,TypeError):pass
        return FileInfo(kind,targets,'Zertifikat lokal prüfen. Keine Vertrauens-/Sperrlistenprüfung.')
    if kind=='Text' and Path(path).suffix.lower() in ('.txt','.md','.html','.htm','.markdown'):return None
    if kind not in STRUCTURED|{'CSV','TSV'}:return FileInfo(kind,(), 'Text-/Logwerkzeuge im Bearbeiten- und Tools-Kreis.')
    try:
        text,_=read_text(path);value=parse(text,kind);targets=available_targets(value,kind)
        if kind in ('CSV','TSV'):
            from extended import document_actions
            targets=tuple(dict.fromkeys(targets+document_actions(kind)))
        return FileInfo(kind,targets,'Daten lokal prüfen und bearbeiten. Konvertierung kann Kommentare und Formatierung verändern; Vorschau prüfen.')
    except Exception as e:return FileInfo(kind,(),str(e)+' · Prüfen & Bearbeiten öffnet auch ungültige Dateien.')

def convert_data(source,target,output):
    kind=kind_for(source);text,_=read_text(source);value=parse(text,kind);result=serialize(value,target)
    Path(output).write_text(result,encoding='utf-8',newline='');return output
