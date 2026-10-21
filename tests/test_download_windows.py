import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import Qt
from preferences import Preferences
from orbitdrop import Controller
from app_ui import TasksWindow
from window_focus import present
from download_ui import DownloadDialog

class DownloadWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_last_download_folder_persists_separately(self):
        controller=Controller.__new__(Controller);controller.prefs=Preferences(self.root/'prefs');controller.submit=Mock();folder=self.root/'downloads';folder.mkdir()
        controller.submit_download('https://example.org/v','audio',str(folder),0)
        prefs=Preferences(controller.prefs.root);self.assertEqual(prefs.values['download_dir'],str(folder.resolve()));self.assertEqual(prefs.values['output_dir'],'');controller.submit.assert_called_once()
        controller.tasks=QWidget();self.addCleanup(controller.tasks.close);controller.show_tasks=Mock()
        with patch('download_ui.DownloadDialog') as dialog:
            dialog.return_value.result.return_value=0;controller.download_dialog()
            self.assertEqual(dialog.call_args.args[2],str(folder.resolve()));self.assertEqual(dialog.call_args.kwargs['parent'],controller.tasks)
        self.app.processEvents()
    def test_new_task_restores_minimized_history(self):
        window=TasksWindow(Preferences(self.root/'prefs'));self.addCleanup(window.close);window.showMinimized();self.app.processEvents();self.assertTrue(window.isMinimized())
        job=Mock();job.control.cancelled.is_set.return_value=False;window.add(job,'Neuer Download');self.app.processEvents();self.assertFalse(window.isMinimized());self.assertEqual(window.tree.currentItem().text(0),'Neuer Download')
    def test_dialog_stays_above_history_and_is_raised(self):
        parent=QWidget();self.addCleanup(parent.close);dialog=DownloadDialog(None,'audio',str(self.root),lambda *a:None,parent);self.addCleanup(dialog.close)
        self.assertIs(dialog.parentWidget(),parent);self.assertTrue(dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        present(dialog);self.app.processEvents();self.assertTrue(dialog.isVisible())

if __name__=='__main__':unittest.main()
