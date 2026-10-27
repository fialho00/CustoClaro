from io import BytesIO
from unittest import TestCase
from PIL import Image, ImageDraw
from app import prepare_image

class ImageInputs(TestCase):
    def test_different_label_images_are_normalized_without_metadata(self):
        for fmt, label in [('JPEG','CHUVEIRO 5500 W'), ('PNG','GELADEIRA 120 W'),
                           ('WEBP','LAMPADA 9 W'), ('PNG','127 V 10 A'),
                           ('JPEG','600 W / 1200 W')]:
            with self.subTest(fmt=fmt,label=label):
                image = Image.new('RGB',(500,200),'white')
                ImageDraw.Draw(image).text((25,80),label,fill='black')
                file = BytesIO(); image.save(file,format=fmt)
                prepared,mime=prepare_image(BytesIO(file.getvalue()))
                self.assertEqual(mime,'image/jpeg')
                with Image.open(BytesIO(prepared)) as result:
                    self.assertEqual(result.format,'JPEG')
                    self.assertFalse(result.getexif())
