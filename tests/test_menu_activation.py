import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,QPointF
from orbitdrop import Wheel,Controller
from preferences import Preferences
from direct_wheel import geometry
from circle_menu import direct_actions

class MenuActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_classic_home_opens_at_pointer_with_clickable_segments(self):
        w=Wheel(SimpleNamespace());self.addCleanup(w.close)
        with patch('orbitdrop.QCursor.pos',return_value=QPoint(400,400)):w.open()
        self.assertEqual(w.mapToGlobal(QPoint(190,190)),QPoint(400,400))
        self.assertEqual(w.labels,['KONVERTIEREN','BEARBEITEN','TOOLS'])
        self.assertEqual(w.segment(QPointF(298,127)),0);self.assertEqual(w.segment(QPointF(190,190)),-1)
        self.assertEqual(w.height(),380)
    def test_file_tools_have_no_program_actions_or_explorer(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'file.txt';p.write_text('test')
            keys=direct_actions([str(p)],'Text',['TXT'],files_only=True)
            self.assertIn('tool:KOPIEREN',keys);self.assertIn('tool:TERMINAL',keys)
            self.assertNotIn('tool:EXPLORER',keys);self.assertFalse(any(key.startswith('app:') for key in keys))
    def test_link_has_only_audio_video_and_files_menu_waits_for_a_file(self):
        w=Wheel(SimpleNamespace());self.addCleanup(w.close);w.open(mode='files')
        self.assertEqual(w.all_actions,[])
        w.open_link('https://example.org/video');self.assertEqual(w.labels,['download:AUDIO LADEN','download:VIDEO LADEN'])
        for key,path,point,index in geometry(w):self.assertEqual(w.segment(point),index)
    def test_global_search_does_not_reuse_a_previous_file_or_link(self):
        c=Controller.__new__(Controller);c.prefs=SimpleNamespace(values={})
        c.wheel=SimpleNamespace(action_titles={},files=['old.png'],formats=['PNG'],kind='Bild',link='https://example.org/old',context_actions=lambda:['format:PNG'])
        with patch('action_search.ActionSearchDialog') as dialog:
            dialog.return_value.exec.return_value=False;c.search_actions([],'OrbitDrop')
            args=dialog.call_args.args;self.assertIn('app:EINSTELLUNGEN',args[0]);self.assertFalse(any(key.startswith(('format:','edit:','tool:')) for key in args[0]))
            self.assertEqual(args[3],[]);self.assertEqual(args[5],[]);self.assertIsNone(args[6])
        with patch('action_search.ActionSearchDialog') as dialog:
            dialog.return_value.exec.return_value=False;c.search_actions([],'Link')
            self.assertEqual(dialog.call_args.args[0],['download:AUDIO LADEN','download:VIDEO LADEN']);self.assertEqual(dialog.call_args.args[6],c.wheel.link)
    def test_program_functions_remain_in_tray_and_no_extra_input_thread_starts(self):
        with tempfile.TemporaryDirectory() as d:
            prefs=Preferences(d);prefs.update(dict(prefs.values,check_updates=False,check_backends=False))
            with patch('orbitdrop.QTimer.singleShot'):c=Controller(self.app,prefs)
            self.addCleanup(c.timer.stop);self.addCleanup(c.tray.hide);self.addCleanup(c.wheel.close);self.addCleanup(c.shelf.close);self.addCleanup(c.tasks.close)
            names=[action.text() for action in c.tray.contextMenu().actions()]
            for name in ('Audio/Video herunterladen','Einstellungen','Updates','Anleitung','Bildabläufe','Schnellaktionen','Debugging','Aktion suchen'):self.assertIn(name,names)
            self.assertFalse(hasattr(c,'shortcut_events'));self.assertEqual(c.timer.interval(),10)

if __name__=='__main__':unittest.main()
