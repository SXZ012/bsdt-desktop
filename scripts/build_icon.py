from pathlib import Path
from PIL import Image, ImageDraw
root = Path(__file__).resolve().parents[1]
assets = root / 'build-assets'
assets.mkdir(exist_ok=True)
svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><rect x="32" y="32" width="960" height="960" rx="240" fill="#102b40"/><rect x="48" y="48" width="928" height="928" rx="224" fill="none" stroke="#284b60" stroke-width="16"/><g fill="#254a5d"><rect x="215" y="620" width="125" height="165" rx="26"/><rect x="410" y="540" width="125" height="245" rx="26"/><rect x="605" y="460" width="125" height="325" rx="26"/></g><path d="M225 574 L414 397 L559 460 L773 246" fill="none" stroke="#69dcc6" stroke-width="66" stroke-linecap="round" stroke-linejoin="round"/><circle cx="773" cy="246" r="44" fill="#e6faf5"/></svg>'''
(assets / 'bsdt.svg').write_text(svg,encoding='utf-8')
(root / 'frontend/src/brand-icon.svg').write_text(svg,encoding='utf-8')
im = Image.new('RGBA', (1024,1024), (0,0,0,0))
d = ImageDraw.Draw(im)
d.rounded_rectangle((32,32,992,992),radius=240,fill='#102b40')
d.rounded_rectangle((48,48,976,976),radius=224,outline='#284b60',width=16)
for x,y in [(215,620),(410,540),(605,460)]:
    d.rounded_rectangle((x,y,x+125,785),radius=26,fill='#254a5d')
points=[(225,574),(414,397),(559,460),(773,246)]
d.line(points,fill='#69dcc6',width=66,joint='curve')
for x,y in points:
    d.ellipse((x-33,y-33,x+33,y+33),fill='#69dcc6')
d.ellipse((729,202,817,290),fill='#e6faf5')
im.save(assets / 'bsdt.png')
im.save(assets / 'bsdt.ico',format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
im.resize((160,160),Image.Resampling.LANCZOS).save(assets / 'bsdt-preview.png')
print('New chart icon:',sorted(Image.open(assets / 'bsdt.ico').ico.sizes()))