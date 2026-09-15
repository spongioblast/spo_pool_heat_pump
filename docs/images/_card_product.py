"""Cut a white-studio product shot onto the same dark card as the wiring diagrams."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

# Same slate as dialog-*.png and dr164-parallel-tap.png
BG = (42, 45, 51)
CARD = (54, 58, 66)
TEAL = (56, 189, 212)
WHITE = (243, 244, 246)
MUTED = (163, 163, 168)


def font(size: int, bold: bool = False):
    for name in ("segoeuib.ttf" if bold else "segoeui.ttf", "arialbd.ttf" if bold else "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def cutout_white(src: Image.Image) -> Image.Image:
    im = src.convert("RGBA")
    w, h = im.size
    pix = im.load()

    def bg(x: int, y: int) -> bool:
        r, g, b, _a = pix[x, y]
        return r >= 250 and g >= 250 and b >= 250

    q: deque[tuple[int, int]] = deque()
    seen: set[tuple[int, int]] = set()
    for x in range(w):
        for y in (0, h - 1):
            if bg(x, y):
                q.append((x, y))
                seen.add((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if (x, y) not in seen and bg(x, y):
                q.append((x, y))
                seen.add((x, y))
    while q:
        x, y = q.popleft()
        pix[x, y] = (0, 0, 0, 0)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen:
                r, g, b, _a = pix[nx, ny]
                if r >= 248 and g >= 248 and b >= 248:
                    seen.add((nx, ny))
                    q.append((nx, ny))
    return im


def bbox_opaque(im: Image.Image) -> tuple[int, int, int, int]:
    alpha = im.split()[-1]
    return alpha.getbbox() or (0, 0, im.size[0], im.size[1])


def card(cut: Image.Image, title: str, dest: Path) -> None:
    box = bbox_opaque(cut)
    cut = cut.crop(box)
    pad = 56
    title_h = 72
    inner_w, inner_h = cut.size
    # Fit the product into a wide card without blowing up tiny shots.
    max_inner_w = 1100
    if inner_w > max_inner_w:
        scale = max_inner_w / inner_w
        cut = cut.resize((int(inner_w * scale), int(inner_h * scale)), Image.Resampling.LANCZOS)
        inner_w, inner_h = cut.size
    cw = inner_w + pad * 2
    ch = inner_h + pad * 2 + title_h
    canvas_w = cw + 80
    canvas_h = ch + 80
    canvas = Image.new("RGB", (canvas_w, canvas_h), BG)
    draw = ImageDraw.Draw(canvas)
    card_box = (40, 40, 40 + cw, 40 + ch)
    draw.rounded_rectangle(card_box, radius=28, fill=CARD, outline=TEAL, width=3)
    draw.text((40 + pad, 58), title, font=font(36, bold=True), fill=WHITE)
    canvas.paste(cut, (40 + pad, 40 + title_h + pad // 2), cut)
    canvas.save(dest, "PNG")
    print(dest)


def main() -> None:
    jobs = (
        (HERE / "_usr-dr164-src.png", "USR-DR164", HERE / "usr-dr164.png"),
        (HERE / "_uts-t02-src.png", "UTS-T02", HERE / "uts-t02.png"),
    )
    for src, title, dest in jobs:
        card(cutout_white(Image.open(src)), title, dest)


if __name__ == "__main__":
    main()
