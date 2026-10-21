import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
from pathlib import Path
import unittest
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from orbitdrop import Wheel
from preferences import Preferences
from app_ui import SettingsDialog
from direct_wheel import geometry
from circle_menu import direct_actions
from image_processing_ui import ImageProcessingDialog

class DirectMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.image=self.root/'image.png';Image.new('RGB',(120,80),'red').save(self.image)
    def test_direct_actions_hidden_formats_and_click(self):
        calls=[]
        class Target:
            def __init__(self):self.prefs=Preferences(self_root/'prefs');self.prefs.update(dict(self.prefs.values,hidden_formats=['JPG','SVG']))
            def convert_files(self,files,action):calls.append((files,action))
        self_root=self.root;target=Target();wheel=Wheel(target);self.addCleanup(wheel.close);wheel.open();wheel.inspect([str(self.image)])
        deadline=time.monotonic()+5
        while wheel.checking and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertEqual(wheel.node,'home');self.assertEqual(wheel.labels,['KONVERTIEREN','BEARBEITEN','TOOLS'])
        wheel.select_action('BEARBEITEN');self.assertIn('edit:BITMAP',wheel.labels);self.assertFalse(any(key.startswith('format:') for key in wheel.labels))
        wheel.select_action('edit:ZURÜCK');self.assertEqual(wheel.node,'home');self.assertEqual(wheel.files,[str(self.image)])
        wheel.select_action('TOOLS');self.assertIn('tool:TERMINAL',wheel.labels);self.assertIn('app:EINSTELLUNGEN',wheel.labels)
        wheel.select_action('app:ZURÜCK');wheel.select_action('KONVERTIEREN')
        self.assertEqual(wheel.node,'direct');self.assertIn('format:PNG',wheel.labels);self.assertTrue(all(key.startswith('format:') for key in wheel.labels))
        self.assertNotIn('format:JPG',wheel.labels);self.assertNotIn('format:SVG SCHNELL',wheel.labels);self.assertNotIn('WEITER',wheel.labels)
        for key,path,point,index in geometry(wheel):self.assertEqual(wheel.segment(point),index,key)
        key,path,point,index=next(entry for entry in geometry(wheel) if entry[0]=='format:PNG');QTest.mouseClick(wheel,Qt.MouseButton.LeftButton,pos=point.toPoint());self.app.processEvents();self.assertEqual(calls,[([str(self.image)],'PNG')])
    def test_format_preferences_persist_and_dialog_checkboxes(self):
        prefs=Preferences(self.root/'prefs');dialog=SettingsDialog(prefs);self.addCleanup(dialog.close)
        for key in ('format:SVG SCHNELL','format:SVG ERWEITERT'):dialog.menu_items[key].setCheckState(0,Qt.CheckState.Unchecked)
        dialog.save();self.assertIn('SVG',Preferences(prefs.root).values['hidden_formats'])
    def test_sliders_and_values_stay_synchronized(self):
        for target in ('BITMAP','SVG'):
            dialog=ImageProcessingDialog(self.image,target,lambda *a:None);self.addCleanup(dialog.close);dialog.auto.setChecked(False)
            field=dialog.slider_fields['threshold'];field.slider.setValue(175);self.assertEqual(dialog.fields['threshold'].value(),175)
            dialog.fields['threshold'].setValue(140);self.assertEqual(field.slider.value(),140)
            contrast=dialog.slider_fields['contrast'];contrast.slider.setValue(175);self.assertAlmostEqual(dialog.fields['contrast'].value(),1.75)
            dialog.auto.setChecked(True);self.assertFalse(field.slider.isEnabled());dialog.close()

if __name__=='__main__':unittest.main()
