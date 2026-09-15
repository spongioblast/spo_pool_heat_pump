"""One-shot renderer for uts-t02-parallel-tap.png. Run from this folder."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("uts-t02-parallel-tap.png")
W, H = 1600, 900
# Same slate as dialog-*.png and dr164-parallel-tap.png
BG = (42, 45, 51)
CARD = (54, 58, 66)
TEAL = (56, 189, 212)
ORANGE = (245, 158, 11)
BLUE = (59, 130, 246)
GREY = (156, 163, 175)
WHITE = (243, 244, 246)
MUTED = (163, 163, 168)
WIRE_A = (96, 165, 250)
WIRE_B = (251, 191, 36)
WIRE_G = (212, 212, 216)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        "segoeui.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "arial.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box, fill, outline, width=3, radius=28) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def pill(draw, xy, letter, fill, text_fill=WHITE) -> None:
    x, y = xy
    r = 26
    draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)
    f = font(28, bold=True)
    bbox = draw.textbbox((0, 0), letter, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x - tw / 2, y - th / 2 - 2), letter, font=f, fill=text_fill)


def main() -> None:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    left = (80, 70, 700, 720)
    right = (900, 70, 1520, 720)
    rounded(d, left, CARD, TEAL)
    rounded(d, right, CARD, ORANGE)

    title = font(40, bold=True)
    sub = font(22)
    body = font(20)
    wire_f = font(20)
    foot = font(22)

    d.text((110, 100), "UTS-T02", font=title, fill=WHITE)
    d.text((110, 160), "USB  ·  RS-485  ·  listen only", font=sub, fill=MUTED)

    d.text((930, 100), "Heat pump", font=title, fill=WHITE)
    d.text((930, 160), "display / RS-485 bus — factory WiFi / DTU port", font=sub, fill=MUTED)

    rows = [
        (290, "A+TXD", "A", WIRE_A, BLUE, "RS-485 A", "A", "bus A"),
        (400, "B-RXD", "B", WIRE_B, ORANGE, "RS-485 B", "B", "bus B"),
        (510, "GND", "G", WIRE_G, GREY, "common ground", "G", "ground"),
    ]
    for y, l_lab, l_letter, wcol, pcol, mid, r_letter, r_lab in rows:
        d.text((110, y - 12), l_lab, font=body, fill=MUTED)
        pill(d, (430, y), l_letter, pcol)
        pill(d, (1170, y), r_letter, pcol)
        d.line((456, y, 1144, y), fill=wcol, width=4)
        bbox = d.textbbox((0, 0), mid, font=wire_f)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) / 2, y - 36), mid, font=wire_f, fill=wcol)
        d.text((1210, y - 12), r_lab, font=body, fill=MUTED)

    d.text((110, 590), "Switch on RS485 (not RS232).", font=body, fill=MUTED)
    d.text((110, 622), "USB 5 V, no pump 12 V. RTS held low.", font=body, fill=MUTED)
    d.text((930, 590), "Same three pins as the WiFi module.", font=body, fill=MUTED)
    d.text((930, 622), "Parallel tap. Leave the factory module", font=body, fill=MUTED)
    d.text((930, 654), "plugged in and the display cable intact.", font=body, fill=MUTED)

    d.text((80, 760), "Swap A and B if every frame fails CRC.", font=foot, fill=MUTED)
    d.text((80, 796), "TX LED must stay dark. Do not cut the panel cable.", font=foot, fill=MUTED)

    im.save(OUT, "PNG")
    print(OUT)


if __name__ == "__main__":
    main()
