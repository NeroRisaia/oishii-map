"""アプリアイコン（フォークとナイフの絵文字 🍴 を、えんじ色の角丸地に白丸で載せる）を作る。

    python -I tools/make_icons.py public/icons

絵文字は Windows の Segoe UI Emoji（カラー）で描く。
"""
import sys

from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
BG = (176, 58, 46, 255)
WHITE = (255, 255, 255, 255)


def make(size, path):
    img = Image.new("RGBA", (size, size), BG)
    d = ImageDraw.Draw(img)
    pad = size * 0.14
    d.ellipse([pad, pad, size - pad, size - pad], fill=WHITE)
    font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", int(size * 0.44))
    d.text((size / 2, size / 2), "\U0001F374", font=font, embedded_color=True, anchor="mm")
    img.save(path)


make(192, f"{OUT}/icon-192.png")
make(512, f"{OUT}/icon-512.png")
print("ok")
