"""生成应用图标 assets/pyenv.ico(多尺寸, Pillow)。

用法: python scripts/make_icon.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]
BASE = 256  # 以 256 为基准绘制再缩放

PRIMARY = (61, 109, 242)      # #3d6df2
PRIMARY_DARK = (43, 82, 214)
WHITE = (255, 255, 255)


def _rounded_gradient(base: int) -> Image.Image:
    """绘制圆角渐变方块底。"""
    img = Image.new("RGBA", (base, base), (0, 0, 0, 0))
    # 垂直渐变
    grad = Image.new("RGBA", (base, base))
    top, bottom = PRIMARY, PRIMARY_DARK
    for y in range(base):
        t = y / max(base - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for _ in range(1):
            pass
        ImageDraw.Draw(grad).line([(0, y), (base, y)], fill=(r, g, b, 255))
    # 圆角蒙版
    mask = Image.new("L", (base, base), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, base - 1, base - 1], radius=int(base * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def _load_bold_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\calibrib.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def build_icon(out_path: str) -> None:
    base_img = _rounded_gradient(BASE)
    # "Py" 白色粗体居中
    font = _load_bold_font(int(BASE * 0.42))
    draw = ImageDraw.Draw(base_img)
    bbox = draw.textbbox((0, 0), "Py", font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (BASE - w) // 2 - bbox[0]
    y = (BASE - h) // 2 - bbox[1] - int(BASE * 0.02)
    draw.text((x, y), "Py", font=font, fill=WHITE)
    # 底部点缀条(呼应 UI 主色)
    bar_h = max(int(BASE * 0.045), 6)
    draw.rounded_rectangle(
        [int(BASE * 0.30), int(BASE * 0.80), int(BASE * 0.70),
         int(BASE * 0.80) + bar_h],
        radius=bar_h // 2, fill=(232, 238, 254, 230))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    frames = [base_img.resize((s, s), Image.LANCZOS) for s in SIZES]
    frames[-1].save(
        out_path, format="ICO",
        sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print(f"ICON_OK: {out_path}")


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build_icon(os.path.join(root, "assets", "pyenv.ico"))
