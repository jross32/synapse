from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import math, random
root=Path(__file__).resolve().parent/'assets'
root.mkdir(exist_ok=True)
random.seed(32)
font_path=r'C:\Windows\Fonts\segoeui.ttf'
bold_path=r'C:\Windows\Fonts\segoeuib.ttf'
def font(sz,bold=False):
    try:return ImageFont.truetype(bold_path if bold else font_path,sz)
    except:return ImageFont.load_default()
def bg(w,h):
    im=Image.new('RGB',(w,h));px=im.load()
    for y in range(h):
        for x in range(w):
            t=y/max(1,h-1);v=x/max(1,w-1)
            px[x,y]=(int(11+17*t+14*v),int(10+8*t+5*v),int(29+38*t+29*v))
    return im
def glow(im,xy,radius,color):
    layer=Image.new('RGBA',im.size,(0,0,0,0));d=ImageDraw.Draw(layer)
    cx,cy=xy
    d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=(*color,155))
    layer=layer.filter(ImageFilter.GaussianBlur(radius*.65))
    return Image.alpha_composite(im.convert('RGBA'),layer)
def brain(d,cx,cy,scale):
    pts=[]
    for side in [-1,1]:
        x=cx+side*32*scale
        for k in range(4):
            yy=cy+(k-1.5)*25*scale
            rr=7*scale
            d.ellipse((x-rr,yy-rr,x+rr,yy+rr),outline=(159,107,255,235),width=max(1,int(2*scale)))
            pts.append((x,yy))
        for k in range(3):
            d.line([(x,cy+(k-1.5)*25*scale),(cx+side*15*scale,cy+(k-1)*16*scale)],fill=(175,95,255,170),width=max(1,int(scale*2)))
    d.rounded_rectangle((cx-48*scale,cy-52*scale,cx+48*scale,cy+52*scale),radius=int(22*scale),outline=(171,113,255,180),width=max(2,int(2*scale)))
    d.line([(cx,cy-38*scale),(cx,cy+38*scale)],fill=(190,139,255,185),width=max(1,int(2*scale)))
# Left artwork shown during welcome/finish: actual NSIS bitmap 164x314
w,h=164,314
im=bg(w,h).convert('RGBA')
im=glow(im,(91,126),74,(102,32,210));im=glow(im,(146,241),65,(52,34,130))
art=Image.new('RGBA',(w,h),(0,0,0,0));d=ImageDraw.Draw(art)
for i in range(8):
    y=25+i*41
    d.line([(0,y+25),(164,y-35)],fill=(126,75,216,max(20,85-i*8)),width=1)
brain(d,82,112,.77)
d.text((15,202),'SYNAPSE',font=font(23,True),fill=(243,232,255,255))
d.text((16,232),'INTELLIGENT',font=font(11,True),fill=(186,151,248,255))
d.text((16,249),'WORKSPACE',font=font(11,True),fill=(186,151,248,255))
d.rounded_rectangle((16,286,86,289),radius=2,fill=(151,80,255,255))
im=Image.alpha_composite(im,art).convert('RGB')
im.save(root/'installer-sidebar.bmp')
# Top banner on inner pages
w,h=150,57
im=bg(w,h).convert('RGBA')
im=glow(im,(115,26),40,(124,61,235))
d=ImageDraw.Draw(im)
d.text((10,9),'SYNAPSE',font=font(20,True),fill=(245,235,255))
d.text((11,35),'SETUP  /  REPAIR',font=font(9,True),fill=(191,144,255))
d.line([(142,5),(142,51)],fill=(176,99,255),width=2)
im.convert('RGB').save(root/'installer-header.bmp')
print('ASSETS',[(x.name, x.stat().st_size) for x in root.glob('*.bmp')])
