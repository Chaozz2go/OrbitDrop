import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile,time,unittest
from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication
from image_editor import ImageEditor
from tools import tool_outputs
from photo_effects import adjust_photo
from direct_wheel import geometry
from orbitdrop import Wheel

class PhotoEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=self.root/'alpha.png'
        Image.new('RGBA',(80,40),(160,60,20,96)).save(self.source)
    def wait(self,condition):
        end=time.monotonic()+8
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def test_export_applies_crop_rotation_colors_resize_and_preserves_alpha(self):
        before=self.source.read_bytes()
        result=tool_outputs('Bild bearbeiten',[self.source],{'angle':90,'crop':(0,0,20,40),'adjustments':{'grayscale':True,'brightness':1.5},'resize':{'width':10,'keep_ratio':True}},{} )[0]
        with Image.open(result) as image:
            self.assertEqual(image.size,(10,20));r,g,b,a=image.getpixel((5,5));self.assertEqual(r,g);self.assertEqual(g,b);self.assertEqual(a,96)
        self.assertEqual(self.source.read_bytes(),before)
    def test_invalid_adjustment_cleans_output_and_rejects_huge_resize(self):
        before=set(self.root.iterdir())
        for params in ({'adjustments':{'brightness':float('nan')}},{'resize':{'width':30000,'height':30000,'keep_ratio':False}}):
            with self.assertRaises(ValueError):tool_outputs('Bild bearbeiten',[self.source],params,{})
        self.assertEqual(set(self.root.iterdir()),before)
    def test_preview_preserves_crop_and_reset_clears_changes(self):
        calls=[];editor=ImageEditor(self.source,lambda *args:calls.append(args));self.addCleanup(editor.close)
        editor.canvas.selection=QRectF(2,2,30,20);editor.fields['saturation'].setValue(0);editor.fields['brightness'].setValue(1.3)
        self.wait(lambda:editor.processed is not None and editor.save_button.isEnabled())
        self.assertEqual(editor.canvas.crop_box(),(2,2,32,22));color=editor.processed.pixelColor(10,10);self.assertEqual(color.red(),color.green());self.assertEqual(color.alpha(),96)
        editor.compare_original(True);editor.compare_original(False);editor.rotate(90);self.wait(lambda:editor.job is None and editor.save_button.isEnabled())
        editor.width.setValue(20);editor.reset();self.wait(lambda:editor.job is None and editor.save_button.isEnabled())
        self.assertEqual(editor.angle,0);self.assertIsNone(editor.canvas.crop_box());self.assertEqual(editor.width.value(),0);self.assertEqual(editor.fields['saturation'].value(),1)
        editor.save();self.assertEqual(calls[0][2]['adjustments']['brightness'],1)
    def test_dense_menu_exposes_all_targets_without_overlap(self):
        wheel=Wheel(object());self.addCleanup(wheel.close);wheel.open();wheel.node='direct';wheel.all_actions=['format:F'+str(i) for i in range(28)]+['format:ZURÜCK'];wheel.display_page();self.app.processEvents()
        layout=geometry(wheel);self.assertEqual(len(layout),29)
        for key,path,point,index in layout:
            self.assertEqual(wheel.segment(point),index,key)
            self.assertEqual(sum(other.contains(point) for _,other,_,_ in layout),1,key)

if __name__=='__main__':unittest.main()
