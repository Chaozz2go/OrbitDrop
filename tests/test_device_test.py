import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import array,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QSystemTrayIcon
from PySide6.QtMultimedia import QAudioFormat
from device_test_ui import DeviceTestDialog,audio_peak
from orbitdrop import Controller
from preferences import DEFAULTS,KEY_CODES

class DeviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_pcm_peaks_are_bounded_and_handle_silence(self):
        F=QAudioFormat.SampleFormat
        self.assertEqual(audio_peak(bytes([128]*100),F.UInt8),0)
        self.assertEqual(audio_peak(bytes([0,255]),F.UInt8),1)
        for code,fmt,value in [('h',F.Int16,16384),('i',F.Int32,1073741824),('f',F.Float,.5)]:
            self.assertAlmostEqual(audio_peak(array.array(code,[0,value]).tobytes(),fmt),.5)
        self.assertEqual(audio_peak(array.array('f',[float('nan'),float('inf'),2]).tobytes(),F.Float),1)
        self.assertEqual(audio_peak(b'\0',F.Int16),0)
    def test_open_and_refresh_never_start_devices(self):
        with patch('device_test_ui.QMediaDevices.videoInputs',return_value=[]),patch('device_test_ui.QMediaDevices.audioInputs',return_value=[]),patch('device_test_ui.QCamera') as camera,patch('device_test_ui.QAudioSource') as audio:
            d=DeviceTestDialog();d.show();self.app.processEvents();d.refresh()
            self.assertFalse(d.camera_button.isEnabled());self.assertFalse(d.microphone_button.isEnabled())
            camera.assert_not_called();audio.assert_not_called();d.close()
    def test_explicit_microphone_start_meter_and_close_release(self):
        device=Mock();device.description.return_value='Testmikro';device.preferredFormat.return_value.sampleFormat.return_value=QAudioFormat.SampleFormat.Int16
        source=Mock();source.error.return_value=SimpleNamespace(value=0);io=source.start.return_value;io.readAll.return_value=array.array('h',[16384]).tobytes()
        with patch('device_test_ui.QMediaDevices.videoInputs',return_value=[]),patch('device_test_ui.QMediaDevices.audioInputs',return_value=[device]),patch('device_test_ui.QAudioSource',return_value=source) as ctor:
            d=DeviceTestDialog();ctor.assert_not_called();d.toggle_microphone();source.start.assert_called_once();d.read_audio();d.update_meter();self.assertEqual(d.level.value(),50)
            d.close();source.stop.assert_called_once();self.assertIsNone(d.audio_io);self.assertFalse(d.meter_timer.isActive())
    def test_camera_stop_detaches_session_and_error_is_readable(self):
        d=DeviceTestDialog();camera=Mock();session=Mock();d.session=session;d.camera=camera
        d.camera_error(None,'Zugriff verweigert');camera.stop.assert_called_once();session.setCamera.assert_called_with(None);session.setVideoOutput.assert_called_with(None)
        self.assertIn('Zugriff verweigert',d.camera_status.text());self.assertIsNone(d.camera);d.close()
    def test_tray_left_click_opens_home_circle(self):
        c=Controller.__new__(Controller);c.wheel=Mock();c.show_dashboard=Mock()
        c.activated(QSystemTrayIcon.ActivationReason.Context);c.wheel.open.assert_not_called()
        c.activated(QSystemTrayIcon.ActivationReason.Trigger);c.wheel.open.assert_called_once_with();c.show_dashboard.assert_not_called()
    def test_alt_blank_surface_remains_open_after_release_and_escape_closes(self):
        c=Controller.__new__(Controller);c.prefs=SimpleNamespace(values=DEFAULTS);c.wheel=Mock();c.wheel.isVisible.return_value=False;c.shortcuts_paused=False;c.was_keys={};c.released=0;c.selection_revision=0;c.activation_guard=Mock();c.activation_guard.context.return_value=SimpleNamespace(drag=True,selection=False)
        def poll(codes):
            with patch('orbitdrop.sys.platform','win32'),patch('orbitdrop.ctypes.windll',SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda key:0x8000 if key in codes else 0)),create=True):c.poll()
        poll({1,KEY_CODES['Alt']});c.wheel.open.assert_called_once_with(automatic=False,mode='files')
        c.wheel.isVisible.return_value=True;c.wheel.automatic=False;c.activation_guard.context.return_value=SimpleNamespace(drag=False,selection=False)
        for _ in range(20):poll(set())
        c.wheel.hide.assert_not_called();poll({0x1b});c.wheel.hide.assert_called_once()
    def test_tools_has_device_check_without_files(self):
        from circle_menu import direct_actions
        self.assertIn('app:WEBCAM / MIKRO',direct_actions([],None,[],files_only=True))

if __name__=='__main__':unittest.main()
