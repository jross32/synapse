"""Generate original Synapse installer wizard artwork.

Produces the 164x314 sidebar and 150x57 header expected by NSIS.
Drawn procedurally with Pillow; no externally hosted assets or bundled fonts.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)
RNG = random.Random(209)
CYAN = (34, 211, 238, 255)
BLUE = (62, 99, 255, 255)
VIOLET = (142, 67, 255, 255)
PINK = (215, 76, 244, 255)


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    path = Path("C:/Windows/Fonts") / name
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def background(size: tuple[int, int], cx: float, cy: float) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    pix = image.load()
    for y in range(height):
        for x in range(width):
            blue = math.exp(-(((x - cx) / (width * 0.45)) ** 2 + ((y - cy) / (height * 0.32)) ** 2) * 1.7)
            violet = math.exp(-(((x - (cx + 28)) / (width * 0.5)) ** 2 + ((y - (cy + 35)) / (height * 0.4)) ** 2) * 2.2)
            pix[x, y] = (6 + int(18 * violet + 3 * blue), 10 + int(9 * blue), 27 + int(31 * blue + 14 * violet))
    return image.convert("RGBA")


def curve(p0, p1, p2, p3, steps: int = 50) -> list[tuple[float, float]]:
    return [
        ((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t * t * p2[0] + t ** 3 * p3[0],
         (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t * t * p2[1] + t ** 3 * p3[1])
        for t in (i / steps for i in range(steps + 1))
    ]


def paint_brain(image: Image.Image, center: tuple[int, int], radius: int) -> Image.Image:
    x, y = center
    overlay = Image.new("RGBA", image.size)
    lines = ImageDraw.Draw(overlay)
    points = [
        (-.78, -.24), (-.58, -.66), (-.18, -.83), (.25, -.71), (.7, -.56),
        (.91, -.15), (.66, .2), (.81, .57), (.39, .79), (-.03, .66),
        (-.51, .8), (-.87, .41), (-.4, -.18), (.02, -.27), (.36, .15), (-.05, .35)
    ]
    verts = [(x + px * radius, y + py * radius) for px, py in points]
    edges = [
        (0,1),(1,2),(2,3),(3,4),(4,5),(5,6),(6,7),(7,8),(8,9),
        (9,10),(10,11),(11,0),(0,12),(12,13),(13,14),(14,15),
        (15,9),(15,10),(12,11),(12,1),(13,3),(14,5),(14,6),(13,15),
        (2,12),(4,14),(1,13),(6,8),(9,12),(10,0)
    ]
    for i, (a, b) in enumerate(edges):
        pa, pb = verts[a], verts[b]
        mid = ((pa[0]+pb[0])/2 + math.sin(i) * radius * .11, (pa[1]+pb[1])/2 + math.cos(i) * radius * .09)
        polyline = curve(pa, mid, mid, pb, 22)
        lines.line(polyline, fill=(45, 190, 255, 185) if i % 3 else (194, 80, 255, 205), width=2 if i % 4 else 1)
    # Lobes and a faint midline: recognizable neural network rather than fake photograph.
    lines.arc((x-radius*.97,y-radius*.95,x+radius*.96,y+radius*.94), 148, 404, fill=BLUE, width=2)
    lines.arc((x-radius*.76,y-radius*.84,x+radius*.79,y+radius*.77), 18, 190, fill=VIOLET, width=2)
    lines.line(curve((x,y-radius*.75),(x-radius*.13,y-radius*.2),(x+radius*.25,y+radius*.2),(x,y+radius*.78)),fill=CYAN,width=2)
    for i, (px,py) in enumerate(verts):
        r=2.3 if i % 3 else 3.2
        lines.ellipse((px-r,py-r,px+r,py+r),fill=CYAN if i % 3 else PINK)
    glow = overlay.filter(ImageFilter.GaussianBlur(max(4, radius//8)))
    image = Image.alpha_composite(image, glow)
    image = Image.alpha_composite(image, overlay)
    return image


def sidebar() -> None:
    image = background((164,314), 84,165)
    stars = ImageDraw.Draw(image)
    for _ in range(35):
        x, y = RNG.randrange(164), RNG.randrange(55,263)
        stars.point((x,y), fill=(115, 120, 241, RNG.randrange(50,130)))
    image = paint_brain(image,(82,146),72)
    draw=ImageDraw.Draw(image)
    draw.line((18,244,146,244), fill=(65,79,151,150),width=1)
    draw.text((82,22),"S Y N A P S E",fill=(234,239,255),font=font(12,True),anchor="mm")
    draw.text((82,261),"YOUR CONNECTED",fill=(217,225,250),font=font(11,True),anchor="mm")
    draw.text((82,276),"BRAIN",fill=(123,169,255),font=font(15,True),anchor="mm")
    draw.text((82,301),"All your AI. One workspace.",fill=(169,179,218),font=font(8),anchor="mm")
    image.convert("RGB").save(OUT/"synapse-sidebar.bmp",format="BMP")


def header() -> None:
    image = background((150,57),20,25)
    image = paint_brain(image,(26,28),23)
    draw=ImageDraw.Draw(image)
    draw.text((60,18),"SYNAPSE",fill=(239,243,255),font=font(15,True))
    draw.text((60,35),"Your Connected Brain",fill=(157,185,250),font=font(8))
    image.convert("RGB").save(OUT/"synapse-header.bmp",format="BMP")


if __name__ == "__main__":
    sidebar()
    header()
    for path in sorted(OUT.glob("synapse-*.bmp")):
        with Image.open(path) as image:
            print(f"{path}: {image.width}x{image.height} {path.stat().st_size} bytes")
