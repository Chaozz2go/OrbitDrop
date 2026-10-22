import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,subprocess,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QMessageBox
from backend_checks import probe_command,summary
from orbitdrop import BackendCheck,Controller
from extended import soffice

class BackendCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_windows_office_uses_console_launcher_headlessly_and_never_probes_gui_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'soffice.exe';exe.touch()
            self.assertIsNone(probe_command('LibreOffice',str(exe),'win32'))
            com=exe.with_suffix('.com');com.touch()
            self.assertEqual(probe_command('LibreOffice',str(exe),'win32'),[str(com),'--headless','--version'])
            with patch('extended.sys.platform','win32'),patch('extended.backend',return_value=str(exe)):
                self.assertEqual(soffice(),str(com))
        self.assertEqual(probe_command('ffmpeg','ffmpeg','win32'),['ffmpeg','-version'])
        self.assertEqual(probe_command('LibreOffice','/usr/bin/soffice','linux'),['/usr/bin/soffice','--headless','--version'])
    def test_gui_only_office_is_found_without_starting_it(self):
        job=BackendCheck();reports=[];job.signals.done.connect(lambda status,missing:reports.append((status,missing)))
        with patch('filetypes.backend',return_value=None),patch('extended.soffice',return_value='soffice.exe'),patch('backend_checks.probe_command',return_value=None),patch('filetypes.run') as run:
            job.run();run.assert_not_called()
        self.assertNotIn('LibreOffice',reports[0][1]);self.assertIn('übersprungen',' '.join(reports[0][0]))
    def test_probe_failure_reports_missing_without_interrupting_remaining_checks(self):
        job=BackendCheck();reports=[];job.signals.done.connect(lambda *args:reports.append(args))
        with patch('filetypes.backend',side_effect=lambda name:name),patch('extended.soffice',return_value='soffice'),patch('backend_checks.probe_command',side_effect=lambda name,exe:[exe,'--version']),patch('filetypes.run',side_effect=[OSError('broken'),subprocess.CompletedProcess([],0,'ffprobe 1',''),subprocess.CompletedProcess([],0,'pandoc 1',''),subprocess.CompletedProcess([],0,'LibreOffice 1','')]):job.run()
        self.assertEqual(reports[0][1],['ffmpeg']);self.assertEqual(len(reports[0][0]),4)
    def test_startup_optional_missing_is_quiet_and_manual_check_opens_explanation(self):
        c=Controller.__new__(Controller);c.tray=Mock();c.show_backend_when_ready=False
        c.backends_checked([],['pandoc','LibreOffice']);c.tray.showMessage.assert_not_called()
        c.backends_checked([],['ffmpeg']);self.assertIn('Audio und Video',c.tray.showMessage.call_args.args[0])
        c.show_backend_when_ready=True
        with patch.object(c,'show_backend_dialog') as show:c.backends_checked([],['pandoc']);show.assert_called_once()
        text=summary(['LibreOffice']);self.assertIn('Office-Dokumente',text);self.assertIn('Optionales Zusatzprogramm',text);self.assertIn('Audio und Video: Bereit',text)
    def test_dialog_keeps_paths_and_technical_messages_in_details(self):
        c=Controller.__new__(Controller);c.backend_status=['LibreOffice: C:/secret/path\nRaw error'];c.backend_missing=['LibreOffice']
        with patch('orbitdrop.QMessageBox') as box:
            box.return_value.clickedButton.return_value=None;c.show_backend_dialog()
            self.assertNotIn('C:/secret',box.return_value.setText.call_args.args[0]);box.return_value.setDetailedText.assert_called_once_with(c.backend_status[0])

if __name__=='__main__':unittest.main()
