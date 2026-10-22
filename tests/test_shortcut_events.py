import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from preferences import DEFAULTS,KEY_CODES
from shortcut_events import ShortcutEvents,ShortcutEvent,physical_key
from activation_guard import ActivationContext,classify_window
from orbitdrop import Controller

class ShortcutEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_tap_is_preserved_after_release_and_repeat_is_not_a_new_event(self):
        q=ShortcutEvents(DEFAULTS);q.feed(0xa0,True,True,(1,2),1);q.feed(0xa0,True,True,(1,2),1.01);q.feed(0xa0,False,True,(1,2),1.02)
        self.assertEqual(q.drain(),[ShortcutEvent('convert',(1,2),1)]);self.assertEqual(q.drain(),[])
        q.feed(ord('Z'),True,True,(1,2));self.assertNotIn(ord('Z'),q.down);self.assertFalse(q.drain())
    def test_chord_and_both_modifier_sides(self):
        q=ShortcutEvents(dict(DEFAULTS,convert_key='Shift+F8'))
        q.feed(0xa0,True,True,(1,2));q.feed(0xa1,True,True,(1,2));q.feed(0xa0,False,True,(1,2))
        q.feed(KEY_CODES['F8'],True,True,(1,2));self.assertEqual(q.drain()[0].mode,'convert')
        q.feed(KEY_CODES['F8'],False,True,(1,2));q.feed(0xa1,False,True,(1,2));q.feed(KEY_CODES['F8'],True,True,(1,2));self.assertFalse(q.drain())
        q=ShortcutEvents(DEFAULTS);q.feed(0xa2,True,True,(1,2));q.feed(0xa5,True,True,(1,2));self.assertFalse(q.drain())
        q=ShortcutEvents(DEFAULTS);q.feed(0xa0,True,True,(1,2));q.feed(0xa2,True,True,(1,2));self.assertFalse(q.drain())
        self.assertEqual(physical_key(0x10,0x36,0),0xa1);self.assertEqual(physical_key(0x11,0,2),0xa3)
    def test_pause_clears_pending_and_held_repeat_does_not_reactivate(self):
        q=ShortcutEvents(DEFAULTS);q.feed(0xa0,True,True,(1,2));q.configure(DEFAULTS,enabled=False);self.assertFalse(q.drain())
        q.feed(0xa0,False,True,(1,2));q.feed(0xa0,True,True,(1,2));q.configure(DEFAULTS,enabled=True)
        q.feed(0xa0,True,True,(1,2));self.assertFalse(q.drain());q.feed(0xa0,False,True,(1,2));q.feed(0xa0,True,True,(1,2));self.assertTrue(q.drain())
    def test_bounded_queue_and_reconfiguration_discards_previous_bindings(self):
        q=ShortcutEvents(DEFAULTS)
        for i in range(50):q.feed(0xa0,True,True,(1,2),i);q.feed(0xa0,False,True,(1,2),i)
        self.assertEqual(len(q.events),16);q.configure(dict(DEFAULTS,convert_key='F8'));self.assertFalse(q.drain())
    def controller(self):
        c=Controller.__new__(Controller);c.prefs=SimpleNamespace(values=DEFAULTS);c.wheel=Mock();c.wheel.isVisible.return_value=False
        c.shortcut_events=ShortcutEvents(DEFAULTS);c.was_keys={};c.shortcuts_paused=False;c.released=0;c.selection_pending=False;c.selection_revision=0
        c.activation_guard=Mock();c.activation_guard.context.return_value=ActivationContext((1,2),True,False)
        return c
    def poll(self,c,codes=()):
        with patch('orbitdrop.sys.platform','win32'),patch('orbitdrop.ctypes.windll',SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda code:0x8000 if code in codes else 0)),create=True):c.poll()
    def test_desktop_tap_missed_by_polling_still_opens_once(self):
        c=self.controller();c.shortcut_events.feed(0xa0,True,True,(1,2));c.shortcut_events.feed(0xa0,False,True,(1,2))
        self.poll(c,{1});c.wheel.open.assert_called_once_with(automatic=True,mode='convert');self.poll(c,{1});c.wheel.open.assert_called_once()
    def test_key_held_before_left_button_is_accepted_on_new_desktop_gesture(self):
        c=self.controller();self.poll(c,{0x10});c.wheel.open.assert_not_called();self.poll(c,{0x10,1});c.wheel.open.assert_called_once()
        self.poll(c,{0x10,1});c.wheel.open.assert_called_once()
    def test_expired_released_changed_window_game_and_modal_events_are_discarded(self):
        for token,age,left,context,modal in [((1,2),1,True,ActivationContext((1,2),True),False),((1,2),0,False,ActivationContext((1,2),True),False),((5,6),0,True,ActivationContext((1,2),True),False),((1,2),0,True,ActivationContext((1,2)),False),((1,2),0,True,ActivationContext((1,2),True),True)]:
            c=self.controller();c.shortcut_events.events.append(ShortcutEvent('convert',token,time.monotonic()-age));c.activation_guard.context.return_value=context
            with patch('orbitdrop.QApplication.activeModalWidget',return_value=object() if modal else None):self.poll(c,{1} if left else set())
            c.wheel.open.assert_not_called();self.assertFalse(c.shortcut_events.drain())
    def test_transient_empty_foreground_preserves_event_but_game_does_not(self):
        for recovery in (ActivationContext((1,2),True),ActivationContext((3,4))):
            c=self.controller();c.shortcut_events.feed(0xa0,True,True,(1,2));c.shortcut_events.feed(0xa0,False,True,(1,2));c.activation_guard.context.return_value=ActivationContext()
            self.poll(c,{1});c.wheel.open.assert_not_called();c.activation_guard.context.return_value=recovery;self.poll(c,{1})
            if recovery.drag:c.wheel.open.assert_called_once()
            else:c.wheel.open.assert_not_called();self.assertFalse(c.pending_shortcuts)
    def test_visible_menu_survives_brief_missing_focus_but_not_a_game(self):
        c=self.controller();c.wheel.isVisible.return_value=True;c.wheel.automatic=True
        c.activation_guard.context.return_value=ActivationContext()
        with patch('orbitdrop.time.monotonic',return_value=100):self.poll(c,{1})
        c.wheel.hide.assert_not_called()
        with patch('orbitdrop.time.monotonic',return_value=100.2):self.poll(c,{1})
        c.wheel.hide.assert_called_once()
        c.wheel.hide.reset_mock();c.activation_guard.context.return_value=ActivationContext((3,4))
        self.poll(c,{1});c.wheel.hide.assert_called_once()
    def test_modal_dialog_discards_retry_from_previous_foreground_gap(self):
        c=self.controller();c.pending_shortcuts=[ShortcutEvent('convert',(1,2),time.monotonic())]
        with patch('orbitdrop.QApplication.activeModalWidget',return_value=object()):self.poll(c,{1})
        self.assertFalse(c.pending_shortcuts);self.poll(c,{1});c.wheel.open.assert_not_called()
    def test_retry_cannot_survive_additional_altgr_modifiers(self):
        c=self.controller();c.pending_shortcuts=[ShortcutEvent('edit',(1,2),time.monotonic())]
        self.poll(c,{1,0x11,0x12});c.wheel.open.assert_not_called()
    def test_desktop_child_classes_still_require_explorer_process(self):
        for cls in ('SHELLDLL_DefView','SysListView32'):
            self.assertTrue(classify_window(1,2,'explorer.exe',cls,own_pid=3).drag)
            self.assertFalse(classify_window(1,2,'game.exe',cls,own_pid=3).drag)
    @unittest.skipUnless(sys.platform=='win32','Native Windows Raw Input registration')
    def test_native_message_window_registration_and_shutdown(self):
        q=ShortcutEvents(DEFAULTS).start();self.addCleanup(q.close)
        self.assertTrue(q.ready.wait(3));self.assertEqual(q.error,'');self.assertTrue(q.available)
        q.close();self.assertFalse(q.thread.is_alive());self.assertFalse(q.available)

if __name__=='__main__':unittest.main()
