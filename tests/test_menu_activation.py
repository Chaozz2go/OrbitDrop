import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from types import SimpleNamespace
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,QPointF,QRect
from PySide6.QtGui import QImage
from orbitdrop import Wheel,Controller
from octagon_menu import configure,geometry,MORE
from preferences import DEFAULTS
from shortcuts import tapped_mode

class MenuActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_compact_opens_at_cursor_without_outer_ring_footprint(self):
        w=Wheel(SimpleNamespace());self.addCleanup(w.close)
        with patch('orbitdrop.QCursor.pos',return_value=QPoint(400,400)):w.open(mode='convert')
        self.assertLessEqual(w.width(),420);self.assertLessEqual(w.height(),420)
        self.assertEqual(w.menu_center+QPointF(w.pos()),QPointF(400,400))
        self.assertEqual(w.menu_anchor,QPointF(400,400))
        # Windows layered hit testing skips fully transparent pixels. Keep the
        # complete compact drag target alive, including gaps, without a footer.
        image=w.grab().toImage();self.assertGreater(image.pixelColor(2,2).alpha(),0)
        self.assertLessEqual(image.pixelColor(2,2).alpha(),2)
    def test_expansion_at_edge_keeps_inner_actions_anchored_and_reachable(self):
        w=Wheel(SimpleNamespace());self.addCleanup(w.close);w.open(mode='edit')
        w.files=['test.png'];w.kind='Bild';w.formats=['PNG'];w.menu_area=QRect(0,0,1280,960)
        for anchor in (QPointF(220,220),QPointF(1000,700),QPointF(640,480)):
            w.menu_anchor=anchor;w.menu_expanded=False;w.display_mode()
            before={k:p+QPointF(w.pos()) for k,_,p,_ in geometry(w)}
            w.select_action(MORE)
            self.assertTrue(w.menu_expanded)
            for key,path,point,_ in geometry(w):
                if key in before:self.assertEqual(point+QPointF(w.pos()),before[key])
                self.assertTrue(w.rect().contains(path.boundingRect().toAlignedRect()))
            self.assertTrue(w.menu_area.contains(w.geometry()))
    def test_quick_taps_only_recover_single_bindings_and_not_modifier_chords(self):
        self.assertEqual(tapped_mode(DEFAULTS,{'Shift':1},{}),'convert')
        self.assertEqual(tapped_mode(DEFAULTS,{'Strg':1},{}),'edit')
        self.assertIsNone(tapped_mode(DEFAULTS,{'Shift':1},{'Shift':True}))
        self.assertIsNone(tapped_mode(DEFAULTS,{'Shift':1,'Alt':1},{}))
        self.assertIsNone(tapped_mode(DEFAULTS,{'Shift':1,'Alt':0x8000},{}))
        self.assertIsNone(tapped_mode(dict(DEFAULTS,convert_key='Shift+F8'),{'Shift':1,'F8':1},{}))
    def test_same_mode_does_not_rebuild_or_reset_active_drag(self):
        w=Wheel(SimpleNamespace());self.addCleanup(w.close);w.open(mode='convert')
        with patch.object(w,'display_mode') as rebuild:w.switch_mode('convert');rebuild.assert_not_called()
    def test_short_tap_recovery_still_obeys_game_guard(self):
        c=Controller.__new__(Controller);c.prefs=SimpleNamespace(values=DEFAULTS);c.wheel=Mock();c.wheel.isVisible.return_value=False
        c.was_keys={};c.shortcuts_paused=False;c.selection_pending=False;c.released=0;c.activation_guard=Mock()
        for safe in (False,True):
            c.was_keys={};c.wheel.reset_mock();c.activation_guard.context.return_value=SimpleNamespace(drag=safe,selection=False)
            def raw(code):return 0x8000 if code==1 else 1 if code==0x10 else 0
            with patch('orbitdrop.sys.platform','win32'),patch('orbitdrop.ctypes.windll',SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=raw)),create=True):c.poll()
            if safe:c.wheel.open.assert_called_once_with(automatic=True,mode='convert')
            else:c.wheel.open.assert_not_called()

if __name__=='__main__':unittest.main()
