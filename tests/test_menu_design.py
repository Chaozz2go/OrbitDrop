import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF,Qt
from PySide6.QtTest import QTest
from orbitdrop import Wheel
from circle_menu import action_color

class MenuDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_direct_ring_targets_are_clickable(self):
        from direct_wheel import geometry
        calls=[]
        class Target:
            def circle_action(self,files,action,kind):calls.append(action)
        wheel=Wheel(Target());self.addCleanup(wheel.close);wheel.open();wheel.all_actions=['format:SVG SCHNELL','format:SVG ERWEITERT','app:EINSTELLUNGEN'];wheel.display_page();self.app.processEvents()
        point=next(entry[2] for entry in geometry(wheel) if entry[0]=='format:SVG SCHNELL')
        QTest.mouseClick(wheel,Qt.MouseButton.LeftButton,pos=point.toPoint());self.app.processEvents();self.assertEqual(calls,['SVG SCHNELL'])

if __name__=='__main__':unittest.main()
