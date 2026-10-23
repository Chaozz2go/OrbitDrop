import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from preferences import Preferences
from diagnostics import DiagnosticStore,recognition_report
from filetypes import FileInfo
from orbitdrop import Inspection,Wheel
from diagnostics_ui import DiagnosticsDialog

class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.prefs=Preferences(self.root/'prefs')
    def test_technical_report_no_bytes_tags_or_paths(self):
        source=self.root/'private-name.unknown';source.write_bytes(b'SECRET DOCUMENT CONTENT')
        info=FileInfo('Unbekannt',(),f'Cannot read {source}')
        with patch('diagnostics.backend',return_value=None),patch('diagnostics.environment',return_value={'app_version':'0.8.1'}):report=recognition_report(source,info)
        self.assertEqual(report['size_bytes'],23);self.assertEqual(report['name'],source.name)
        self.assertNotIn(str(self.root),json.dumps(report));self.assertNotIn('SECRET',json.dumps(report))
        store=DiagnosticStore(self.prefs);store.add([report]);store.add([report]);self.assertEqual(len(store.records),1);self.assertEqual(store.records[0]['occurrences'],2)
        restored=DiagnosticStore(self.prefs);self.assertEqual(restored.records,store.records)
        exported=self.root/'report.json';restored.export(exported);data=exported.read_text();self.assertNotIn('private-name',data);self.assertNotIn(str(self.root),data)
        with self.assertRaises(FileExistsError):restored.export(exported)
        self.assertEqual(source.read_bytes(),b'SECRET DOCUMENT CONTENT')
        self.assertIn('private-name',json.dumps(restored.export_data(True)))
        restored.clear();self.assertEqual(DiagnosticStore(self.prefs).records,[]);self.assertTrue(source.exists())
    def test_background_report_is_saved_on_controller_callback(self):
        from orbitdrop import Controller,DiagnosticJob
        from PySide6.QtCore import QThreadPool
        import time
        source=self.root/'unsupported.weird';source.write_bytes(b'content')
        controller=Controller.__new__(Controller);controller.diagnostics=DiagnosticStore(self.prefs);controller.diagnostic_jobs=set();controller.pool=QThreadPool.globalInstance()
        with patch('diagnostics.backend',return_value=None),patch('diagnostics.environment',return_value={}):
            controller.record_diagnostics([(str(source),FileInfo('Unbekannt',(),'Unsupported'))])
            deadline=time.monotonic()+3
            while controller.diagnostic_jobs and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertFalse(controller.diagnostic_jobs);self.assertEqual(len(controller.diagnostics.records),1)
        self.assertEqual(DiagnosticStore(self.prefs).records[0]['extension'],'.weird')

    def test_bound_and_ui_and_program_menu(self):
        store=DiagnosticStore(self.prefs);store.add([{'name':str(i),'extension':'.x','reason':'unsupported','kind':'Unbekannt'} for i in range(110)])
        self.assertEqual(len(store.records),100)
        dialog=DiagnosticsDialog(store);self.addCleanup(dialog.close);self.assertEqual(dialog.tree.topLevelItemCount(),100);self.assertFalse(dialog.names.isChecked())
        wheel=Wheel(object());self.addCleanup(wheel.close);wheel.open();wheel.navigate('more');self.assertNotIn('app:DEBUGGING',wheel.labels)
    def test_inspection_only_logs_individual_unavailable_formats(self):
        files=[]
        for index in range(2):
            file=self.root/f'{index}.x';file.write_bytes(b'x');files.append(str(file))
        def report(path,info):return {'name':Path(path).name,'reason':info.message}
        with patch('orbitdrop.inspect_file',side_effect=[FileInfo('Bild',('PNG',)),FileInfo('Audio',('MP3',))]),patch('diagnostics.recognition_report',side_effect=report):
            job=Inspection(files);job.run();self.assertEqual(job.reports,[])
        with patch('orbitdrop.inspect_file',side_effect=[FileInfo('Bild',('PNG',)),FileInfo('Unbekannt',(),'Unsupported')]),patch('diagnostics.recognition_report',side_effect=report):
            job=Inspection(files);job.run();self.assertEqual(job.reports,[(files[1],FileInfo('Unbekannt',(),'Unsupported'))])

if __name__=='__main__':unittest.main()
