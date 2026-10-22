import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from activation_guard import ActivationContext, ActivationGuard, classify_window
from orbitdrop import Controller
from preferences import DEFAULTS, KEY_CODES, Preferences


class ActivationGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def controller(self, context):
        c = Controller.__new__(Controller)
        c.prefs = SimpleNamespace(values=dict(DEFAULTS))
        c.wheel = Mock(); c.wheel.isVisible.return_value = False; c.wheel.automatic = True
        c.was_keys = {}; c.selection_pending = False; c.selection_revision = 0
        c.selection_job = None; c.selection_origin = None; c.released = 0
        c.shortcuts_paused = False; c.request_selection = Mock()
        c.activation_guard = Mock(); c.activation_guard.context.return_value = context
        return c

    def poll(self, c, codes):
        with patch('orbitdrop.sys.platform', 'win32'), patch('orbitdrop.ctypes.windll',
                SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda key: 0x8000 if key in codes else 0)), create=True):
            c.poll()

    def test_windowed_games_and_unknown_windows_are_excluded(self):
        for name in ('cs2.exe', 'valorant.exe', 'game.exe', 'steamwebhelper.exe', 'unknown.exe'):
            context = classify_window(100, 500, 'C:\\Games\\'+name, 'UnrealWindow', own_pid=42)
            self.assertFalse(context.drag); self.assertFalse(context.selection)
            for key in ('Shift', 'Strg', 'Alt'):
                c = self.controller(context)
                self.poll(c, {KEY_CODES[key], 1})
                c.wheel.open.assert_not_called(); c.request_selection.assert_not_called()
                c.was_keys = {}; self.poll(c, {KEY_CODES[key]})
                c.request_selection.assert_not_called()

    def test_explorer_desktop_managers_and_own_windows_allow_drag(self):
        for name, cls in [('explorer.exe', 'CabinetWClass'), ('explorer.exe', 'Progman'),
                          ('explorer.exe', 'WorkerW'), ('TOTALCMD64.EXE', 'TTOTAL_CMD'), ('dopus.exe', 'DOpus')]:
            context = classify_window(100, 500, 'C:\\Apps\\'+name, cls, own_pid=42, fullscreen=True)
            self.assertTrue(context.drag)
            c = self.controller(context); self.poll(c, {KEY_CODES['Shift'], 1})
            c.wheel.open.assert_called_once_with(automatic=True, mode='convert')
        self.assertTrue(classify_window(100, 42, '', 'QtWindow', own_pid=42).drag)
        self.assertFalse(classify_window(100, 500, 'game.exe', 'CabinetWClass', own_pid=42).drag)
        self.assertFalse(classify_window(0, 500, 'explorer.exe', 'CabinetWClass').drag)

    def test_browser_requires_separate_key_without_mouse_and_not_fullscreen(self):
        browser = classify_window(100, 500, 'chrome.exe', 'Chrome_WidgetWin_1', own_pid=42)
        self.assertFalse(browser.drag); self.assertTrue(browser.selection)
        c = self.controller(browser); self.poll(c, {KEY_CODES['Shift'], 1})
        c.wheel.open.assert_not_called(); c.request_selection.assert_not_called()
        self.poll(c, set()); self.poll(c, {KEY_CODES['Shift']})
        c.request_selection.assert_called_once()
        full = classify_window(100, 500, 'chrome.exe', 'Chrome_WidgetWin_1', own_pid=42, fullscreen=True)
        self.assertFalse(full.selection)

    def test_focus_change_hides_automatic_wheel_without_retriggering_held_key(self):
        c = self.controller(ActivationContext((1, 2), True, False))
        self.poll(c, {KEY_CODES['Shift'], 1}); c.wheel.open.reset_mock()
        c.wheel.isVisible.return_value = True
        c.activation_guard.context.return_value = ActivationContext((3, 4))
        self.poll(c, {KEY_CODES['Shift'], 1}); c.wheel.hide.assert_called_once()
        c.wheel.isVisible.return_value = False
        c.activation_guard.context.return_value = ActivationContext((1, 2), True, False)
        self.poll(c, {KEY_CODES['Shift'], 1}); c.wheel.open.assert_not_called()
        self.poll(c, {1}); self.poll(c, {KEY_CODES['Shift'], 1})
        c.wheel.open.assert_called_once()

    def test_pause_blocks_shortcuts_and_clears_pending_selection(self):
        c = self.controller(ActivationContext((1, 2), True, True)); c.tray = Mock()
        c.selection_pending = True; c.pause_shortcuts(True)
        self.assertFalse(c.selection_pending)
        self.poll(c, {KEY_CODES['Shift'], 1})
        c.wheel.open.assert_not_called(); c.request_selection.assert_not_called()
        c.wheel.hide.reset_mock(); self.poll(c, {0x1B})
        c.wheel.hide.assert_called_once()

    def test_late_link_result_is_discarded_after_window_change_or_pause(self):
        c = self.controller(ActivationContext((1, 2), False, True)); c.selection_revision = 7; c.selection_origin = (1, 2)
        job = object(); c.selection_job = job
        c.activation_guard.context.return_value = ActivationContext((9, 9))
        c.selection_ready(job, 7, 'https://example.org/video'); c.wheel.open_link.assert_not_called()
        c.activation_guard.context.return_value = ActivationContext((1, 2), False, True)
        c.selection_ready(job, 7, 'https://example.org/video'); c.wheel.open_link.assert_called_once()
        c.wheel.open_link.reset_mock(); c.shortcuts_paused = True
        c.selection_ready(job, 7, 'https://example.org/video'); c.wheel.open_link.assert_not_called()

    def test_default_start_checks_migration_and_explicit_opt_out(self):
        with tempfile.TemporaryDirectory() as root:
            prefs = Preferences(root); self.assertTrue(prefs.values['check_updates'])
            old = dict(DEFAULTS, check_updates=False, image_quality=65); old.pop('startup_update_policy')
            Path(root, 'settings.json').write_text(json.dumps(old))
            prefs = Preferences(root); self.assertTrue(prefs.values['check_updates']); self.assertEqual(prefs.values['image_quality'], 65)
            prefs.update(dict(prefs.values, check_updates=False))
            self.assertFalse(Preferences(root).values['check_updates'])

    def test_start_update_does_not_wait_for_daily_marker_or_duplicate_jobs(self):
        c = Controller.__new__(Controller); c.prefs = SimpleNamespace(values=dict(DEFAULTS)); c.update_job = None; c.pool = Mock()
        with patch('update_ui.UpdateJob') as job:
            c.auto_update_check(); c.auto_update_check()
            job.assert_called_once(); c.pool.start.assert_called_once()
        c.update_job = None; c.prefs.values['check_updates'] = False
        with patch('update_ui.UpdateJob') as job:
            c.auto_update_check(); job.assert_not_called()

    def test_each_start_schedules_check_even_with_recent_old_marker(self):
        with tempfile.TemporaryDirectory() as root:
            prefs = Preferences(root); prefs.update(dict(prefs.values, check_backends=False))
            Path(root, 'update-check.time').write_text('999999999999')
            for enabled in (True, True, False):
                prefs.update(dict(prefs.values, check_updates=enabled))
                with patch('orbitdrop.QTimer.singleShot') as schedule:
                    c = Controller(self.app, prefs)
                    try:
                        calls = [call for call in schedule.call_args_list if call.args[0] == 1500]
                        self.assertEqual(len(calls), int(enabled))
                    finally:
                        c.timer.stop(); c.tray.hide(); c.wheel.close(); c.shelf.close(); c.tasks.close()

    @unittest.skipUnless(sys.platform == 'win32', 'Win32 ABI smoke test')
    def test_native_api_queries_current_process_and_foreground_safely(self):
        import ctypes
        from ctypes import wintypes
        guard = ActivationGuard(); user, kernel = guard._windows_api()
        handle = kernel.OpenProcess(0x1000, False, os.getpid()); self.assertTrue(handle)
        try:
            buffer = ctypes.create_unicode_buffer(32768); size = wintypes.DWORD(len(buffer))
            self.assertTrue(kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)))
            self.assertTrue(buffer.value)
        finally:
            kernel.CloseHandle(handle)
        self.assertIsInstance(guard.context(), ActivationContext)


if __name__ == '__main__':
    unittest.main()
