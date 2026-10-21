import tempfile
import unittest
from pathlib import Path
from PIL import Image
from converter import convert

class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)/'test.png'
        Image.new('RGBA', (12, 8), (255, 0, 0, 0)).save(self.source)

    def test_formats_and_original(self):
        before = self.source.read_bytes()
        for target in ['PNG', 'JPG', 'WEBP']:
            result = convert(self.source, target)
            with Image.open(result) as image:
                self.assertEqual(image.size, (12, 8))
                self.assertEqual(image.format, 'JPEG' if target == 'JPG' else target)
                if target == 'JPG':
                    self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
                else:
                    self.assertEqual(image.convert('RGBA').getpixel((0, 0))[3], 0)
        self.assertEqual(before, self.source.read_bytes())

    def test_collision(self):
        first = convert(self.source, 'PNG')
        before = first.read_bytes()
        second = convert(self.source, 'PNG')
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), before)

    def test_invalid_and_animation(self):
        bad = self.source.with_name('bad.txt')
        bad.write_text('not an image')
        with self.assertRaises(Exception):
            convert(bad, 'PNG')
        gif = self.source.with_suffix('.gif')
        Image.new('RGB', (4,4), 'red').save(gif, save_all=True, append_images=[Image.new('RGB', (4,4), 'blue')])
        with self.assertRaises(ValueError):
            convert(gif, 'PNG')
        self.assertFalse(gif.with_name('test_converted.png').exists())

if __name__ == '__main__':
    unittest.main()
