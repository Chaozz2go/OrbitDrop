import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import math,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF,QRect,QMimeData,QUrl,Qt
from PySide6.QtGui import QDragMoveEvent,QDropEvent
from orbitdrop import Wheel
from preferences import Preferences
from octagon_menu import geometry,octagon,configure,MORE,NEXT,PREVIOUS

class OctagonMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.prefs=Preferences(self.root/'prefs')
        self.calls=[];self.target=SimpleNamespace(prefs=self.prefs,circle_action=lambda *a:self.calls.append(a))
        self.w=Wheel(self.target);self.addCleanup(self.w.close);self.w.open(mode='edit')
        self.w.kind='Bild';self.w.files=[str(self.root/'image.png')];self.w.formats=['PNG','JPG'];self.w.display_mode()
    def test_regular_equal_tiles_stable_when_expanded_and_no_intersections(self):
        before={key:(path.boundingRect(),point) for key,path,point,_ in geometry(self.w)}
        position=self.w.pos();self.w.select_action(MORE)
        layout=geometry(self.w);size=self.w.tile_size
        self.assertEqual(position,self.w.pos())
        for key,path,point,_ in layout:
            self.assertAlmostEqual(path.boundingRect().width(),size)
            self.assertAlmostEqual(path.boundingRect().height(),size)
            if key in before:self.assertEqual((path.boundingRect(),point),before[key])
            edges=[]
            for i in range(8):
                a,b=path.elementAt(i),path.elementAt((i+1)%8)
                edges.append(math.hypot(a.x-b.x,a.y-b.y))
            self.assertLess(max(edges)-min(edges),1e-8)
            for other_key,other,_,_ in layout:
                if other_key!=key:self.assertFalse(path.intersects(other),(key,other_key))
        self.assertEqual(octagon(QPointF(),size).boundingRect().size(),layout[0][1].boundingRect().size())
    def test_all_actions_reachable_outer_pages_keep_inner_fixed(self):
        self.w.all_actions=['edit:CUSTOM'+str(i) for i in range(40)];self.w.display_page()
        self.w.select_action(MORE);inner={key:point for key,_,point,_ in geometry(self.w) if key not in self.w.secondary_actions and key not in (NEXT,PREVIOUS)}
        seen=set()
        for _ in range(self.w.secondary_pages):
            for key,_,point,_ in geometry(self.w):
                seen.add(key)
                if key in inner:self.assertEqual(point,inner[key])
            self.w.select_action(NEXT)
        self.assertTrue(set(self.w.all_actions)<=seen)
        self.assertEqual(self.w.outer_page,0)
        self.w.select_action(PREVIOUS);self.assertEqual(self.w.outer_page,self.w.secondary_pages-1)
    def test_drag_hover_expands_once_and_drop_on_more_keeps_open(self):
        file=Path(self.w.files[0]);file.write_bytes(b'test')
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(file))])
        point=next(point for key,_,point,_ in geometry(self.w) if key==MORE)
        move=QDragMoveEvent(point.toPoint(),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        self.w.dragMoveEvent(move);self.assertTrue(move.isAccepted());self.assertTrue(self.w.page_timer.isActive())
        self.w.hover_navigation();self.assertTrue(self.w.menu_expanded)
        self.w.dragMoveEvent(move);self.assertFalse(self.w.page_timer.isActive())
        drop=QDropEvent(point,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        self.w.dropEvent(drop);self.assertTrue(self.w.menu_expanded);self.assertTrue(self.w.isVisible());self.assertTrue(self.w.latched);self.assertFalse(self.calls)
        self.w.hide();self.assertFalse(self.w.page_timer.isActive())
    def test_bounds_negative_monitor_and_small_screen_search_fallback(self):
        self.w.menu_expanded=True
        area=QRect(-1920,-100,1920,1040);configure(self.w,area)
        self.assertTrue(area.contains(self.w.geometry()))
        area=QRect(10,20,640,480);configure(self.w,area)
        self.assertFalse(self.w.outer_supported);self.assertFalse(self.w.menu_expanded);self.assertTrue(area.contains(self.w.geometry()))
        self.w.select_action(MORE);self.app.processEvents();self.assertEqual(self.calls[0][1],'AKTIONSSUCHE')
    def test_hidden_action_favorite_and_expanded_preference(self):
        self.prefs.update(dict(self.prefs.values,menu_expanded=True,hidden_actions=['edit:ZUSCHNEIDEN'],favorite_actions=['edit:BITMAP']))
        self.w.open(mode='edit');self.w.files=['test.png'];self.w.kind='Bild';self.w.formats=['PNG'];self.w.display_mode()
        self.assertTrue(Preferences(self.prefs.root).values['menu_expanded']);self.assertTrue(self.w.menu_expanded)
        self.assertNotIn('edit:ZUSCHNEIDEN',self.w.all_actions)
        self.assertIn(('edit:BITMAP',0,4),self.w._octagon_slots)
        self.w.navigate('edit');self.assertIn(('edit:ZURÜCK',0,4),self.w._octagon_slots)

if __name__=='__main__':unittest.main()
