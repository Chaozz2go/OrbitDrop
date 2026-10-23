import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,unittest
from pathlib import Path
from PIL import Image
from image_upscale import enlarge,target_size,upscale_settings
from tools import tool_outputs
from upscale_ui import UpscaleDialog
from PySide6.QtWidgets import QApplication
from circle_menu import edit_actions

class UpscaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def wait(self,condition):
        end=time.monotonic()+10
        while not condition() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())
    def test_sizes_methods_limits_and_alpha(self):
        image=Image.new('RGBA',(10,5),(120,30,10,70))
        for method in ('lanczos','bicubic','nearest'):
            result=enlarge(image,{'factor':4,'method':method});self.assertEqual(result.size,(40,20));self.assertEqual(result.getpixel((20,10))[3],70)
        self.assertEqual(target_size(image.size,{'width':30}),(30,15));self.assertEqual(target_size(image.size,{'width':40,'height':10}),(20,10))
        for values in ({'factor':float('nan')},{'factor':0},{'method':'AI'},{'sharpen':500}):
            with self.assertRaises(ValueError):upscale_settings(values)
        with self.assertRaises(ValueError):target_size((6000,4000),{'factor':4})
        with self.assertRaises(ValueError):target_size((10,5),{'width':5})
    def test_pixel_art_does_not_add_colors_or_sharpen(self):
        image=Image.new('RGBA',(2,1));image.putpixel((0,0),(255,0,0,255));image.putpixel((1,0),(0,0,255,80))
        result=enlarge(image,{'factor':4,'method':'nearest','denoise':True,'sharpen':200});self.assertEqual(set(result.getdata()),set(image.getdata()))
    def test_export_is_new_file_and_editor_crop_is_applied(self):
        source=self.root/'photo.png';Image.new('RGBA',(40,20),(120,50,20,90)).save(source);before=source.read_bytes()
        parameters={'upscale':{'factor':2,'denoise':True,'sharpen':40},'edit':{'angle':90,'crop':(0,0,10,20)}}
        result=Path(tool_outputs('Bild vergrößern',[source],parameters,{})[0]);self.assertNotEqual(result,source)
        with Image.open(result) as image:self.assertEqual(image.size,(20,40));self.assertEqual(image.getpixel((5,5))[3],90)
        self.assertEqual(source.read_bytes(),before)
    def test_dialog_preview_pixel_mode_and_submission(self):
        source=self.root/'photo.png';Image.new('RGB',(30,20),'red').save(source);calls=[];d=UpscaleDialog(source,lambda *args:calls.append(args));self.addCleanup(d.close);d.show()
        self.wait(lambda:d.save_button.isEnabled());self.assertIn('60 × 40',d.status.text());d.method.setCurrentIndex(2)
        self.wait(lambda:d.save_button.isEnabled());self.assertFalse(d.sharpen_field.isEnabled());d.save();self.assertEqual(calls[0][0],'Bild vergrößern');self.assertEqual(calls[0][2]['upscale']['method'],'nearest')
        self.assertIn('VERGRÖSSERN',edit_actions([str(source)],'Bild'))

if __name__=='__main__':unittest.main()
