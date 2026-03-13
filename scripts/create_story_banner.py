"""썰알람 유튜브 채널 배너 생성"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "branding" / "banner"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WIDTH = 2560
HEIGHT = 1440
SAFE_W = 1546
SAFE_H = 423
SAFE_X = (WIDTH - SAFE_W) // 2
SAFE_Y = (HEIGHT - SAFE_H) // 2

NAVY = (8, 23, 54)
DEEP = (4, 13, 34)
CORAL = (255, 112, 122)
PINK = (255, 158, 147)
CREAM = (248, 245, 238)
CYAN = (97, 224, 212)
MUTED = (185, 194, 214)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ROOT / "assets" / "fonts" / name), size=size)


FONT_TITLE = _font("Paperlogy-9Black.ttf", 156)
FONT_SUB = _font("Paperlogy-6SemiBold.ttf", 50)
FONT_TAG = _font("Paperlogy-7Bold.ttf", 34)


def _vertical_gradient() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    px = img.load()
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        r = int(NAVY[0] * (1 - t) + DEEP[0] * t)
        g = int(NAVY[1] * (1 - t) + DEEP[1] * t)
        b = int(NAVY[2] * (1 - t) + DEEP[2] * t)
        for x in range(WIDTH):
            px[x, y] = (r, g, b)
    return img


def _add_background_glow(base: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=radius // 2))
    return Image.alpha_composite(base.convert("RGBA"), layer)


def _draw_speech_bubble(draw: ImageDraw.ImageDraw, bbox: tuple[int, int, int, int], outline: tuple[int, int, int], fill: tuple[int, int, int]):
    x1, y1, x2, y2 = bbox
    draw.rounded_rectangle(bbox, radius=48, fill=fill, outline=outline, width=10)
    tail = [(x1 + 72, y2 - 16), (x1 + 34, y2 + 72), (x1 + 140, y2 + 18)]
    draw.polygon(tail, fill=fill, outline=outline)
    draw.line([tail[0], tail[1], tail[2]], fill=outline, width=10, joint="curve")
    # inner story bars
    inner_x = x1 + 62
    draw.rounded_rectangle((inner_x, y1 + 60, x2 - 110, y1 + 92), radius=14, fill=(210, 228, 255))
    draw.rounded_rectangle((inner_x, y1 + 120, x2 - 160, y1 + 150), radius=14, fill=(210, 228, 255))
    draw.rounded_rectangle((inner_x, y1 + 178, x2 - 220, y1 + 206), radius=14, fill=(210, 228, 255))


def _draw_spotlight(draw: ImageDraw.ImageDraw, origin: tuple[int, int], target_box: tuple[int, int, int, int]):
    ox, oy = origin
    x1, y1, x2, y2 = target_box
    beam = [(ox + 76, oy - 70), (ox + 236, oy - 250), (x1 + 34, y2 - 8), (x1 + 108, y2 + 34)]
    draw.polygon(beam, fill=(255, 210, 210, 54))
    draw.ellipse((ox - 46, oy - 46, ox + 46, oy + 46), fill=CORAL)
    draw.rectangle((ox - 10, oy - 110, ox + 10, oy - 18), fill=CREAM)
    draw.pieslice((ox - 78, oy - 180, ox + 78, oy - 32), start=210, end=330, fill=CREAM)


def _draw_tag(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=FONT_TAG)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    pad_x = 26
    pad_y = 16
    draw.rounded_rectangle((x, y, x + w + pad_x * 2, y + h + pad_y * 2), radius=24, fill=(19, 42, 83))
    draw.text((x + pad_x, y + pad_y - 3), text, font=FONT_TAG, fill=(220, 230, 248))


def _compose_variant(kind: str) -> Image.Image:
    base = _vertical_gradient().convert("RGBA")
    base = _add_background_glow(base, (620, 670), 420, CORAL, 60)
    base = _add_background_glow(base, (1860, 720), 360, CYAN, 28)

    draw = ImageDraw.Draw(base)

    # decorative rings outside safe area
    draw.ellipse((90, 120, 780, 810), outline=(255, 170, 160, 58), width=8)
    draw.ellipse((1840, 890, 2470, 1520), outline=(110, 230, 220, 48), width=8)

    if kind == "v1":
        bubble = (SAFE_X + 130, SAFE_Y + 42, SAFE_X + 530, SAFE_Y + 320)
        spotlight_origin = (SAFE_X + 16, SAFE_Y + 352)
        title_x = SAFE_X + 640
        sub = "짧지만 오래 남는 실화 · 반전 쇼츠"
        tag_x = title_x
        tag_y = SAFE_Y + 278
        tags = ["실화", "반전", "사이다", "감동"]
    else:
        bubble = (SAFE_X + 180, SAFE_Y + 70, SAFE_X + 560, SAFE_Y + 330)
        spotlight_origin = (SAFE_X + 42, SAFE_Y + 338)
        title_x = SAFE_X + 650
        sub = "매일 새로운 썰이 도착하는 스토리 채널"
        tag_x = title_x
        tag_y = SAFE_Y + 282
        tags = ["사연", "황당썰", "레전드", "쇼츠"]

    _draw_spotlight(draw, spotlight_origin, bubble)
    _draw_speech_bubble(draw, bubble, outline=CREAM, fill=(26, 56, 109))

    # text block
    title = "썰알람"
    title_bbox = draw.textbbox((title_x, SAFE_Y + 18), title, font=FONT_TITLE)
    draw.text((title_x, SAFE_Y + 18), title, font=FONT_TITLE, fill=CREAM)
    draw.text((title_x + 4, SAFE_Y + 194), sub, font=FONT_SUB, fill=MUTED)

    # underline accent
    line_y = SAFE_Y + 250
    draw.rounded_rectangle((title_x, line_y, title_x + 348, line_y + 8), radius=4, fill=CORAL)
    draw.rounded_rectangle((title_x + 366, line_y, title_x + 510, line_y + 8), radius=4, fill=CYAN)

    tx = tag_x
    for tag in tags:
        bbox = draw.textbbox((0, 0), tag, font=FONT_TAG)
        w = bbox[2] - bbox[0]
        _draw_tag(draw, (tx, tag_y), tag)
        tx += w + 78

    # small footer inside safe zone
    footer = "짧고 강하게, 끝까지 보게 되는 이야기"
    draw.text((title_x, SAFE_Y + 346), footer, font=_font("Paperlogy-5Medium.ttf", 28), fill=(175, 188, 214))

    return base.convert("RGB")


def _save_with_preview(kind: str):
    img = _compose_variant(kind)
    out = OUT_DIR / f"sseolalarm_banner_{kind}.jpg"
    img.save(out, quality=95, optimize=True)

    preview = img.copy()
    draw = ImageDraw.Draw(preview)
    draw.rounded_rectangle((SAFE_X, SAFE_Y, SAFE_X + SAFE_W, SAFE_Y + SAFE_H), radius=28, outline=(255, 255, 255), width=4)
    preview.save(OUT_DIR / f"sseolalarm_banner_{kind}_safe_preview.jpg", quality=90, optimize=True)


def main():
    _save_with_preview("v1")
    _save_with_preview("v2")
    print("created:")
    for path in sorted(OUT_DIR.glob("*.jpg")):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
