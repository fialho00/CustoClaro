"""Live Gemma 4 evaluation; requires GEMINI_API_KEY. No image files are saved."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision import read_label, configured_api_key

CASES = [
    ('Chuveiro', 'CHUVEIRO ELETRICO\n127 V 60 Hz\nPOTENCIA: 5500 W', 5500),
    ('Geladeira', 'REFRIGERADOR\n220 V\nPOTENCIA NOMINAL 120 W', 120),
    ('Lâmpada', 'LAMPADA LED\nBIVOLT\nPOTENCIA: 9 W', 9),
    ('Sem watts', 'APARELHO DE TESTE\n127 V\nCORRENTE 10 A', None),
    ('Ambígua', 'MOTOR DOIS MODOS\nBAIXO 600 W\nALTO 1200 W', None),
]

def make_image(text):
    image = Image.new('RGB', (1100, 500), 'white')
    from pathlib import Path
    from PIL import ImageFont
    path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font = ImageFont.truetype(str(path), 44) if path.exists() else ImageFont.load_default()
    ImageDraw.Draw(image).multiline_text((55, 60), text, fill='black', font=font, spacing=30)
    data = BytesIO(); image.save(data, format='JPEG', quality=90)
    return data.getvalue()

if __name__ == '__main__':
    key = configured_api_key()
    if not key:
        raise SystemExit('Defina GEMINI_API_KEY para executar este teste real; nenhuma chamada foi feita.')
    for name, label, expected in CASES:
        try:
            reading = read_label(make_image(label), 'image/jpeg', api_key=key)
            actual = int(reading.power_watts) if reading.power_watts is not None else None
            print(f'{name}: esperado={expected}, modelo={actual}, evidencia={reading.evidence!r}, valido={actual==expected}')
        except Exception as error:
            print(f'{name}: falha={type(error).__name__}; nenhum valor confirmado')
