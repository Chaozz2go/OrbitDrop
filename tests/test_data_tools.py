import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,unittest,hashlib
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QTimer
from data_formats import parse,serialize,json_repair,DataProblem,read_text,available_targets,records,read_table
from admin_tools import text_transform,table_transform,log_lines,file_hashes,compare_files,certificate_report,certificate_bytes
from filetypes import inspect_file
from converter import convert
from circle_menu import edit_actions,direct_actions
from file_actions import available_file_actions
from data_editor_ui import DataEditor
from admin_tools_ui import AdminToolsDialog
from task_runtime import TaskControl,Cancelled

class DataToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def source(self,name,text,encoding='utf-8'):
        p=self.root/name;p.write_text(text,encoding=encoding,newline='');return p
    def wait(self,condition):
        deadline=time.monotonic()+10
        while not condition() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def close_editor(self,d):d.editor.document().setModified(False);d.close();self.app.processEvents()
    def test_json_errors_locate_missing_comma_and_repair_is_explicit(self):
        text='{\n  "server": "localhost"\n  "port":8080\n}'
        with self.assertRaises(DataProblem) as caught:parse(text,'JSON')
        self.assertEqual((caught.exception.line,caught.exception.column),(3,3));self.assertIn('Komma',str(caught.exception))
        title,result=json_repair(text);self.assertEqual(parse(result,'JSON')['port'],8080);self.assertNotEqual(result,text)
        for malformed in ('{"x":1,}','[1,2,]','{"x" 1}','{"x":1'):
            proposal=json_repair(malformed);self.assertIsNotNone(proposal);parse(proposal[1],'JSON')
        self.assertIsNone(json_repair('{"x": nope}'))
    def test_duplicate_keys_are_never_silently_overwritten(self):
        for text,line in [('{"x":1,\n"x":2}',2),('{"a":{"x":1,"x":2}}',1)]:
            with self.assertRaises(DataProblem) as caught:parse(text,'JSON')
            self.assertEqual(caught.exception.line,line);self.assertIn('Doppelter',str(caught.exception));self.assertIsNone(json_repair(text))
        self.assertEqual(parse('{"a":{"x":1},"b":{"x":2}}','JSON')['b']['x'],2)
        with self.assertRaises(DataProblem):parse('x: 1\nx: 2','YAML')
    def test_decimal_precision_survives_format_and_cross_format(self):
        value=parse('{"x":1.234567890123456789,"n":999999999999999999999999999}','JSON')
        self.assertEqual(value['x'],Decimal('1.234567890123456789'))
        for target in ('JSON','YAML','TOML'):
            result=serialize(value,target);self.assertEqual(parse(result,target),value)
        for text in ('{"x":NaN}','{"x":Infinity}'):
            with self.assertRaises(DataProblem):parse(text,'JSON')
    def test_yaml_unsafe_tags_aliases_and_excess_depth_are_rejected(self):
        for text in ('!!python/object/apply:os.system [echo bad]','x: &a [1]\ny: *a','x: !custom abc'):
            with self.assertRaises(DataProblem):parse(text,'YAML')
        with self.assertRaises(ValueError):parse('['*70+'0'+']'*70,'JSON')
        with self.assertRaises(ValueError):parse('x: '+ '['*70+'0'+']'*70,'YAML')
    def test_toml_error_location_and_unrepresentable_values(self):
        with self.assertRaises(DataProblem) as c:parse('name = "ok"\nport = @','TOML')
        self.assertEqual(c.exception.line,2)
        self.assertNotIn('TOML',available_targets({'x':None},'JSON'))
        self.assertNotIn('TOML',available_targets([{'x':'y'}],'JSON'))
        self.assertNotIn('JSON',available_targets(parse('d = 2026-10-24','TOML'),'TOML'))
    def test_xml_conversion_is_structural_and_external_entities_never_load(self):
        text='<root a="v"><child>hey</child>mixed<child /></root>';value=parse(text,'XML');result=serialize(value,'JSON');again=serialize(parse(result,'JSON'),'XML')
        self.assertEqual(parse(again,'XML'),value)
        self.assertNotIn('XML',available_targets({'a':1},'JSON'))
        for text in ('<!DOCTYPE x SYSTEM "file:///secret"><x />','<!DOCTYPE x [<!ENTITY e "bad">]><x>&e;</x>'):
            with self.assertRaises(DataProblem):parse(text,'XML')
        with self.assertRaises(DataProblem) as c:parse('<a>\n</b>','XML')
        self.assertEqual(c.exception.line,2)
    def test_csv_preserves_text_and_refuses_lossy_nested_export(self):
        value=read_table('name;id\n"a;b";001\n','CSV');self.assertEqual(value,[{'name':'a;b','id':'001'}])
        for target in ('CSV','TSV'):self.assertEqual(parse(serialize(value,target),target),value)
        for bad in ([{'x':None}],[{'x':{'y':1}}],[{'x':1},{'y':2}]):
            with self.assertRaises(ValueError):serialize(bad,'CSV')
        rows,_=records({'data':[{'name':'a'}]},'/data');self.assertEqual(rows,[{'name':'a'}])
        for bad in ('a,a\n1,2','a,b\n1,2,3'):
            with self.assertRaises(ValueError):read_table(bad)
    def test_pointer_escapes_and_empty_keys_are_preserved(self):
        value={'data':{'':[{'x':1}]},'a/b':[{'x':2}]}
        self.assertEqual(records(value,'/data/')[0],[{'x':1}]);self.assertEqual(records(value,'/a~1b')[0],[{'x':2}])
        for pointer in ('data','/missing','/a~2b'):
            with self.assertRaises(ValueError):records(value,pointer)
    def test_large_csv_is_bounded_before_building_records(self):
        header=','.join('column'+str(n) for n in range(1000))
        text=header+'\n'+((','*999+'\n')*101)
        with self.assertRaisesRegex(ValueError,'100000 Zellen'):read_table(text)
    def test_jsonl_reports_actual_line_and_converts_back(self):
        value=parse('{"x":1}\n\n{"x":2}\n','JSONL');self.assertEqual(parse(serialize(value,'JSONL'),'JSONL'),value)
        with self.assertRaises(DataProblem) as c:parse('{"x":1}\n\n{"x":}\n','JSONL')
        self.assertEqual(c.exception.line,3)
    def test_detection_includes_invalid_files_and_keeps_existing_document_actions(self):
        for name,kind,text in [('bad.json','JSON','{"x":}'),('config.yaml','YAML','port: 80'),('cfg.toml','TOML','port = 80'),('data.xml','XML','<data/>'),('log.jsonl','JSONL','{"x":1}')]:
            source=self.source(name,text);info=inspect_file(source);self.assertEqual(info.kind,kind);self.assertIn('DATEN PRÜFEN',edit_actions([source],kind));self.assertIn('DATEN PRÜFEN',available_file_actions([source]))
        self.assertEqual(inspect_file(self.source('note.txt','a note')).kind,'TXT')
        self.assertEqual(inspect_file(self.source('readme.md','# Heading')).kind,'MD')
        self.assertEqual(inspect_file(self.source('script.ps1','Write-Output "hello"')).kind,'Text')
    def test_native_data_conversion_preserves_source_and_reserves_output(self):
        source=self.source('data.json','{"name":"Jürgen","x":1.23}');before=source.read_bytes()
        yaml=convert(source,'YAML');toml=convert(yaml,'TOML');self.assertEqual(parse(read_text(toml)[0],'TOML')['name'],'Jürgen');self.assertEqual(source.read_bytes(),before)
        self.assertNotEqual(convert(source,'YAML'),yaml)
        bad=self.source('bad.json','{"x":}');self.assertEqual(inspect_file(bad).actions,())
    def test_text_encoding_newlines_replacement_and_deduplication(self):
        source=self.source('text.txt','Ä\r\nB\r\nÄ\r\n','utf-16');text,codec=read_text(source);self.assertEqual(codec,'utf-16')
        result=text_transform(text,'Ä','A',True,True,True);self.assertEqual(result,'1\tA\r\n2\tB\r\n')
        with self.assertRaises(ValueError):read_text(self.source('bad.txt','ä','cp1252'))
        self.assertEqual(read_text(self.root/'bad.txt','cp1252')[0],'ä')
    def test_table_select_sort_deduplicate_and_delimiter_conversion(self):
        text='Name;ID\nZ;002\nA;001\nA;001\n';result=table_transform(text,'CSV','Name,ID','Name',True,delimiter='|')
        self.assertEqual(result,'Name|ID\nA|001\nZ|002\n');self.assertIn('"001"',table_transform(text,'CSV',target='JSON'))
        with self.assertRaises(ValueError):table_transform(text,'CSV','Missing')
    def test_log_stream_filter_time_and_tail(self):
        source=self.source('app.log','2026-10-24T07:00:00Z INFO first\n2026-10-24T08:00:00Z ERROR second\nno timestamp\n2026-10-24T09:00:00Z ERROR last\n')
        result=''.join(log_lines(source,needle='error',start='2026-10-24T08:00:00Z',end='2026-10-24T08:30:00Z'));self.assertIn('second',result);self.assertNotIn('last',result)
        crlf=self.source('windows.log','INFO ready\r\nERROR test\r\n');self.assertEqual(''.join(log_lines(crlf,needle='ERROR')),'ERROR test\r\n')
        self.assertIn('last',''.join(log_lines(source,tail=1)));self.assertNotIn('first',''.join(log_lines(source,tail=1)))
        large=self.source('large.log','ä'*250+'\n');large.write_bytes(large.read_bytes()*10000)
        self.assertEqual(len(''.join(log_lines(large,tail=3)).splitlines()),3)
        with self.assertRaises(ValueError):list(log_lines(source,start='invalid'))
        ctrl=TaskControl();ctrl.cancel()
        with ctrl.activate(),self.assertRaises(Cancelled):list(log_lines(source))
    def test_hash_and_comparison_work_for_binary_and_text(self):
        a=self.source('a.txt','a\nb\n');b=self.source('b.txt','a\nc\n');expected=hashlib.sha256(a.read_bytes()).hexdigest()
        self.assertIn('STIMMT ÜBEREIN',file_hashes([a],expected));self.assertIn('STIMMT NICHT ÜBEREIN',file_hashes([a],'0'*64));self.assertIn('-b',compare_files([a,b]))
        b.write_bytes(a.read_bytes());self.assertIn('bytegenau identisch',compare_files([a,b]));b.write_bytes(b'\0binary');self.assertIn('Binärdatei',compare_files([a,b]))
    def cert(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        key=rsa.generate_private_key(65537,2048);name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'orbit.test')]);now=datetime.now(timezone.utc)
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(100).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=10)).add_extension(x509.SubjectAlternativeName([x509.DNSName('orbit.test')]),False).sign(key,hashes.SHA256())
        return key,cert
    def test_certificate_details_pem_der_pfx_and_no_private_export(self):
        from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption,BestAvailableEncryption,pkcs12
        key,cert=self.cert();pem=self.root/'cert.pem';pem.write_bytes(key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption())+cert.public_bytes(Encoding.PEM))
        report=certificate_report(pem);self.assertIn('orbit.test',report);self.assertIn('SAN:',report);self.assertNotIn('BEGIN PRIVATE KEY',report)
        der=self.root/'cert.der';der.write_bytes(certificate_bytes(pem,'DER'));self.assertIn('orbit.test',certificate_report(der));self.assertNotIn(b'PRIVATE',certificate_bytes(pem,'PEM'))
        pfx=self.root/'secret.pfx';pfx.write_bytes(pkcs12.serialize_key_and_certificates(b'cert',key,cert,None,BestAvailableEncryption(b'secret')))
        with self.assertRaises(ValueError):certificate_report(pfx,'wrong')
        self.assertIn('orbit.test',certificate_report(pfx,'secret'));self.assertNotIn(b'PRIVATE',certificate_bytes(pfx,'PEM','secret'))
        self.assertEqual(inspect_file(pem).kind,'Zertifikat');self.assertIn('DER',inspect_file(pem).actions)
    def test_editor_validates_invalid_json_and_tree_search_paths(self):
        source=self.source('broken.json','{\n"name":"test"\n"port":80\n}');d=DataEditor(source,'JSON');self.addCleanup(lambda:self.close_editor(d));d.show();self.wait(lambda:d.issue is not None)
        self.assertTrue(d.goto.isEnabled());self.assertTrue(d.fix.isEnabled());self.assertFalse(d.save.isEnabled());d.goto_error();self.assertEqual(d.editor.textCursor().blockNumber(),2)
        before=source.read_bytes()
        with patch('data_editor_ui.ChangePreview.exec',return_value=QDialogAccepted()):d.preview_repair()
        self.wait(lambda:d.save.isEnabled());self.assertEqual(source.read_bytes(),before);self.assertEqual(d.tree.topLevelItemCount(),1)
        item=d.tree.topLevelItem(0).child(1);d.tree.setCurrentItem(item);d.copy_tree_path();self.assertEqual(self.app.clipboard().text(),'/port')
        d.save_current();self.wait(lambda:'gespeichert:' in d.status.text());self.assertEqual(source.read_bytes(),before);self.assertFalse(d.editor.document().isModified())
    def test_modal_editors_reject_exits_the_dialog_loop(self):
        source=self.source('config.json','{"x":1}')
        for dialog in (DataEditor(source,'JSON'),AdminToolsDialog([source],'hash')):
            timeout=[];guard=QTimer();guard.setSingleShot(True)
            guard.timeout.connect(lambda d=dialog:(timeout.append(True),d.done(0)));guard.start(1500)
            QTimer.singleShot(100,dialog.reject);result=dialog.exec();guard.stop()
            self.assertFalse(timeout);self.assertFalse(dialog.isVisible());self.assertEqual(result,0)
    def test_admin_ui_tabs_are_contextual_and_hash_is_async(self):
        source=self.source('app.log','hello\n');d=AdminToolsDialog([source],'log');self.addCleanup(d.close);self.assertIn('log',d.pages);self.assertNotIn('certificate',d.pages);d.hash_files();self.wait(lambda:d.job is None);self.assertIn(hashlib.sha256(source.read_bytes()).hexdigest(),d.view.toPlainText())
        csv=self.source('data.csv','x\n1');e=AdminToolsDialog([csv],'table');self.addCleanup(e.close);self.assertIn('table',e.pages)
        self.assertIn('SHA-256',available_file_actions([source]));self.assertIn('VERGLEICHEN',available_file_actions([source,csv]));self.assertNotIn('VERGLEICHEN',available_file_actions([source]))
        self.assertIn('edit:LOG ANSEHEN',direct_actions([source],'LOG',[]))

def QDialogAccepted():return 1
if __name__=='__main__':unittest.main()
