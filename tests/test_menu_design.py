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
    def test_outer_labels_are_targets_and_side_cards_are_clickable(self):
        calls=[]
        class Target:
            def circle_action(self,files,action,kind):calls.append(action)
        wheel=Wheel(Target());self.addCleanup(wheel.close);wheel.open();self.app.processEvents()
        self.assertEqual(wheel.segment(QPointF(402,88)),0)
        QTest.mouseClick(wheel,Qt.MouseButton.LeftButton,pos=QPointF(402,88).toPoint());self.app.processEvents();self.assertEqual(wheel.node,'formats');self.assertGreater(wheel.width(),800)
        wheel.navigate('svg');self.app.processEvents();self.assertEqual(action_color('svg','SVG SCHNELL'),action_color('formats','PNG'))
        QTest.mouseClick(wheel,Qt.MouseButton.LeftButton,pos=QPointF(550,150).toPoint());self.app.processEvents();self.assertEqual(calls,['SVG SCHNELL'])

if __name__=='__main__':unittest.main()
