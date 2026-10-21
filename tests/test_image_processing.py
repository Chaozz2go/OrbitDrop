import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import struct
import tempfile
import time
import threading
from unittest.mock import patch
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage,QPainter
from PySide6.QtCore import Qt
from converter import convert
from tools import tool_outputs
from image_processing import prepare_image,load_image,trace_svg
from image_processing_ui import ImageProcessingDialog
from filetypes import inspect_file
from orbitdrop import Wheel

class ImageProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=self.root/'image.png'
        image=Image.new('RGB',(200,120),'white');draw=ImageDraw.Draw(image);draw.rectangle((20,20,100,100),fill='black');draw.rectangle((40,40,80,80),fill='white');draw.ellipse((130,20,180,70),fill='red');image.save(self.source)
    def test_gray_and_true_one_bit_bmp_and_original(self):
        before=self.source.read_bytes();gray=tool_outputs('Bild aufbereiten',[self.source],{'target':'PNG','processing':{'mode':'gray'}},{})[0]
        with Image.open(gray) as image:self.assertEqual(image.mode,'L');self.assertEqual(image.size,(200,120))
        output=tool_outputs('Bild aufbereiten',[self.source],{'target':'BITMAP','processing':{'mode':'binary'}},{})[0]
        self.assertEqual(struct.unpack_from('<H',Path(output).read_bytes(),28)[0],1)
        with Image.open(output) as image:self.assertEqual(image.mode,'1');self.assertEqual(image.getpixel((25,25)),0);self.assertEqual(image.getpixel((50,50)),255)
        self.assertEqual(self.source.read_bytes(),before)
    def test_threshold_invert_dither_and_transparency(self):
        image=Image.new('L',(256,1));image.putdata(list(range(256)));rgb=image.convert('RGB')
        result,_=prepare_image(rgb,{'auto_threshold':False,'threshold':100});self.assertEqual(result.getpixel((100,0)),0);self.assertEqual(result.getpixel((101,0)),255)
        inverted,_=prepare_image(rgb,{'auto_threshold':False,'threshold':100,'invert':True});self.assertEqual(inverted.getpixel((0,0)),255)
        dither,_=prepare_image(rgb,{'dither':True});self.assertEqual(dither.mode,'1')
        path=self.root/'alpha.png';Image.new('RGBA',(10,10),(0,0,0,0)).save(path);self.assertEqual(load_image(path).getpixel((0,0)),(255,255,255))
    def test_svg_is_paths_and_renders_holes(self):
        self.assertIn('SVG',inspect_file(self.source).actions);output=convert(self.source,'SVG');xml=output.read_text();root=ET.fromstring(xml)
        self.assertNotIn('<image',xml);self.assertNotIn('base64',xml);self.assertTrue(any(e.tag.endswith('path') for e in root.iter()));self.assertEqual(root.attrib['viewBox'],'0 0 200 120')
        renderer=QSvgRenderer(xml.encode());self.assertTrue(renderer.isValid());canvas=QImage(200,120,QImage.Format.Format_ARGB32);canvas.fill(Qt.GlobalColor.white);painter=QPainter(canvas);renderer.render(painter);painter.end()
        self.assertLess(canvas.pixelColor(25,25).red(),30);self.assertGreater(canvas.pixelColor(50,50).red(),230)
    def test_advanced_preview_and_submit(self):
        calls=[];dialog=ImageProcessingDialog(self.source,'SVG',lambda *a:calls.append(a));dialog.show();self.addCleanup(dialog.close)
        renderer_threads=[];main_thread=threading.get_ident()
        def render_on_gui(*args):
            renderer_threads.append(threading.get_ident());return QSvgRenderer(*args)
        with patch('image_processing_ui.QSvgRenderer',side_effect=render_on_gui):
            deadline=time.monotonic()+10
            while not dialog.valid and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertEqual(renderer_threads,[main_thread]);self.assertTrue(dialog.valid);self.assertTrue(dialog.save_button.isEnabled());dialog.save();self.assertEqual(calls[0][2]['target'],'SVG');self.assertEqual(calls[0][2]['processing']['mode'],'binary')
    def test_svg_menu_quick_and_advanced(self):
        calls=[]
        class Target:
            def circle_action(self,files,action,kind):calls.append((files,action,kind))
        wheel=Wheel(Target());self.addCleanup(wheel.close);wheel.open();wheel.files=[str(self.source)];wheel.kind='Bild';wheel.formats=['PNG','SVG'];wheel.node='direct';wheel.all_actions=['format:SVG SCHNELL','format:SVG ERWEITERT'];wheel.display_page()
        self.assertEqual(wheel.node,'direct');self.assertEqual(wheel.labels,['format:SVG SCHNELL','format:SVG ERWEITERT'])
        wheel.select_action('format:SVG ERWEITERT');self.app.processEvents();self.assertEqual(calls[0][1],'SVG ERWEITERT')
    def test_invalid_settings_cleanup_reserved_output(self):
        before=set(self.root.iterdir())
        with self.assertRaises(ValueError):tool_outputs('Bild aufbereiten',[self.source],{'target':'SVG','processing':{'threshold':900}},{})
        self.assertEqual(set(self.root.iterdir()),before)

if __name__=='__main__':unittest.main()
