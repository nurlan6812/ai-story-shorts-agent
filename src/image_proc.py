"""Pillow 이미지 가공 - 3-layout 시스템 (fullbleed / split / three_zone)"""

import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from config.settings import VIDEO_WIDTH, VIDEO_HEIGHT, FONTS_DIR


def _strip_emoji(text: str) -> str:
    """이모지 제거 (Pillow에서 렌더링 불가) - 한글/영문/숫자/기본구두점 보존"""
    # 허용할 문자만 명시적으로 보존
    # 한글(AC00-D7AF), 한글 자모(3130-318F), 영문, 숫자, 기본 구두점, 공백
    cleaned = re.sub(
        r'[^\uAC00-\uD7AF\u3130-\u318F\u0020-\u007E\u00A0-\u00FF]',
        '',
        text,
    )
    return cleaned.strip()


def get_style_font(size: int, bold: bool = True, style: dict | None = None, section_font: str | None = None) -> ImageFont.FreeTypeFont:
    """스타일별 폰트 로드 — section_font > style JSON font_family > 기본 폰트"""
    if style:
        # 1순위: 섹션별 font_family (title.font_family, narration.font_family 등)
        font_family = section_font or style.get("font_family")
        if font_family:
            font_path = FONTS_DIR / font_family
            if font_path.exists():
                try:
                    # .ttc 파일은 index 지정 (0=Regular, 1=Bold, 2=ExtraBold)
                    if font_path.suffix == ".ttc":
                        idx = 2 if bold else 0  # ExtraBold for bold, Regular for normal
                        return ImageFont.truetype(str(font_path), size, index=idx)
                    return ImageFont.truetype(str(font_path), size)
                except Exception:
                    pass
    return get_font(size, bold)


def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """한국어 폰트 로드 - Paperlogy Black/Bold 우선, Pretendard 폴백"""
    # 1순위: Paperlogy (Black for bold, Bold for regular)
    if bold:
        paperlogy = FONTS_DIR / "Paperlogy-8ExtraBold.ttf"
    else:
        paperlogy = FONTS_DIR / "Paperlogy-7Bold.ttf"
    if paperlogy.exists():
        try:
            return ImageFont.truetype(str(paperlogy), size)
        except Exception:
            pass

    # 2순위: Pretendard Variable (Black=900, Regular=400)
    pretendard = FONTS_DIR / "PretendardVariable.ttf"
    if pretendard.exists():
        try:
            font = ImageFont.truetype(str(pretendard), size)
            weight = 900 if bold else 400
            font.set_variation_by_axes([weight])
            return font
        except Exception:
            pass

    # 3순위: 정적 폰트
    static_fonts = [
        FONTS_DIR / "Pretendard-Black.otf",
        FONTS_DIR / "Pretendard-ExtraBold.otf",
        FONTS_DIR / "NanumGothicBold.ttf",
        FONTS_DIR / "NanumGothic.ttf",
    ]
    for font_path in static_fonts:
        if font_path.exists():
            try:
                return ImageFont.truetype(str(font_path), size)
            except Exception:
                continue

    # 3순위: 시스템 폰트 (AppleSDGothicNeo)
    system_font = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
    if system_font.exists():
        try:
            idx = 16 if bold else 6  # Heavy for bold, Bold for normal
            return ImageFont.truetype(str(system_font), size, index=idx)
        except Exception:
            try:
                return ImageFont.truetype(str(system_font), size, index=0)
            except Exception:
                pass

    return ImageFont.load_default(size)


def fit_to_shorts_file(
    image_path: Path,
    output_path: Path,
    style: dict | None = None,
) -> Path:
    """이미지를 9:16로 크롭/리사이즈 (줌용 배경)

    fullbleed: 풀스크린 이미지 (storytelling)
    split: 상단 헤더 + 이미지 (darkcomedy)
    three_zone: 상단 헤더 + 중앙 이미지 + 하단 나레이션 존 (casual/wholesome/absurdist)
    """
    img = Image.open(image_path).convert("RGB")

    layout = style.get("layout", {}) if style else {}
    layout_type = layout.get("type", "overlay")

    if layout_type == "split":
        h_ratio = layout.get("header_height", 0.12)
        h_height = int(VIDEO_HEIGHT * h_ratio)
        content_height = VIDEO_HEIGHT - h_height

        # 이미지를 content 영역(헤더 아래)에 맞게 리사이즈
        target_ratio = VIDEO_WIDTH / content_height
        img_ratio = img.width / img.height
        if img_ratio > target_ratio:
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))
        img = img.resize((VIDEO_WIDTH, content_height), Image.LANCZOS)

        # 풀 캔버스에 헤더 배경색 + 이미지 배치
        bg_color = tuple(layout.get("header_bg_color", [245, 235, 210]))
        canvas = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), bg_color)
        canvas.paste(img, (0, h_height))

        # 하단 블러 처리 (이미지 하단부를 블러+어두운 오버레이)
        bottom_blur = layout.get("bottom_blur", 0)
        if bottom_blur > 0:
            blur_height_ratio = layout.get("bottom_blur_height", 0.28)
            blur_h = int(VIDEO_HEIGHT * blur_height_ratio)
            blur_top = VIDEO_HEIGHT - blur_h
            # 하단 영역 크롭 → 블러
            bottom_region = canvas.crop((0, blur_top, VIDEO_WIDTH, VIDEO_HEIGHT))
            bottom_blurred = bottom_region.filter(ImageFilter.GaussianBlur(radius=bottom_blur))
            # 어두운 오버레이
            overlay_alpha = layout.get("bottom_blur_alpha", 160)
            dark_overlay = Image.new("RGBA", (VIDEO_WIDTH, blur_h), (0, 0, 0, overlay_alpha))
            bottom_blurred = bottom_blurred.convert("RGBA")
            bottom_blurred = Image.alpha_composite(bottom_blurred, dark_overlay)
            canvas.paste(bottom_blurred.convert("RGB"), (0, blur_top))

        img = canvas

    elif layout_type == "three_zone":
        h_height = int(VIDEO_HEIGHT * layout.get("header_height", 0.18))
        b_height = int(VIDEO_HEIGHT * layout.get("bottom_height", 0.25))
        img_top_gap = layout.get("image_top_gap", 0)
        img_height = VIDEO_HEIGHT - h_height - b_height - img_top_gap

        # 이미지를 중앙 영역 크기에 맞게 crop+resize
        target_ratio = VIDEO_WIDTH / img_height
        img_ratio = img.width / img.height
        if img_ratio > target_ratio:
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        # absurdist 프레임: 패딩 적용 시 이미지 축소
        pad_x = layout.get("image_padding_x", 0)
        border_w = layout.get("image_border_width", 0)
        if pad_x > 0 and border_w > 0:
            img = img.resize((VIDEO_WIDTH - 2 * pad_x, img_height), Image.LANCZOS)
        else:
            img = img.resize((VIDEO_WIDTH, img_height), Image.LANCZOS)

        # 캔버스 구성
        header_bg = tuple(layout.get("header_bg_color", [255, 225, 170]))
        bottom_bg = tuple(layout.get("bottom_bg_color", header_bg))
        mid_bg = tuple(layout.get("mid_bg_color", [255, 255, 255]))
        canvas = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), mid_bg)
        # 헤더 영역만 헤더 색으로 채우기
        draw_canvas = ImageDraw.Draw(canvas)
        draw_canvas.rectangle([(0, 0), (VIDEO_WIDTH, h_height)], fill=header_bg)

        # 상단 악센트 바 (라벨 위 컬러 스트립)
        top_bar_color = layout.get("header_top_bar_color")
        top_bar_h = layout.get("header_top_bar_height", 0)
        if top_bar_color and top_bar_h > 0:
            draw_tmp = ImageDraw.Draw(canvas)
            draw_tmp.rectangle([(0, 0), (VIDEO_WIDTH, top_bar_h)], fill=tuple(top_bar_color))

        # 하단 영역: 블러 배경 또는 단색
        bottom_blur = layout.get("bottom_blur", 0)
        if bottom_blur > 0:
            # 이미지 하단부를 확대+블러해서 하단 존 배경으로 사용
            # 원본 이미지의 하단 ~40%를 크롭해서 하단 존 크기로 resize
            src_h = img.height
            crop_top = int(src_h * 0.6)
            bottom_src = img.crop((0, crop_top, img.width, src_h))
            bottom_resized = bottom_src.resize((VIDEO_WIDTH, b_height), Image.LANCZOS)
            # GaussianBlur 적용
            bottom_blurred = bottom_resized.filter(ImageFilter.GaussianBlur(radius=bottom_blur))
            # 반투명 컬러 오버레이 (bottom_bg_color 사용)
            overlay_color = tuple(bottom_bg[:3]) if len(bottom_bg) >= 3 else (200, 200, 200)
            overlay_alpha = layout.get("bottom_blur_alpha", 140)
            color_overlay = Image.new("RGBA", (VIDEO_WIDTH, b_height), overlay_color + (overlay_alpha,))
            bottom_blurred = bottom_blurred.convert("RGBA")
            bottom_blurred = Image.alpha_composite(bottom_blurred, color_overlay)
            canvas.paste(bottom_blurred.convert("RGB"), (0, VIDEO_HEIGHT - b_height))
        else:
            # 기존: 단색 하단 배경
            if bottom_bg != header_bg:
                draw = ImageDraw.Draw(canvas)
                draw.rectangle(
                    [(0, VIDEO_HEIGHT - b_height), (VIDEO_WIDTH, VIDEO_HEIGHT)],
                    fill=bottom_bg,
                )

        # 이미지 배치 (image_top_gap: 헤더와 이미지 사이 간격)
        img_top_gap = layout.get("image_top_gap", 0)
        img_y = h_height + img_top_gap
        if pad_x > 0 and border_w > 0:
            canvas.paste(img, (pad_x, img_y))
        else:
            canvas.paste(img, (0, img_y))

        # absurdist 프레임 테두리 그리기
        if border_w > 0:
            draw = ImageDraw.Draw(canvas)
            border_color = tuple(layout.get("image_border_color", [180, 160, 140]))
            border_radius = layout.get("image_border_radius", 8)
            img_x = pad_x if pad_x > 0 else 0
            img_w = VIDEO_WIDTH - 2 * pad_x if pad_x > 0 else VIDEO_WIDTH
            draw.rounded_rectangle(
                [(img_x, img_y), (img_x + img_w, img_y + img_height)],
                radius=border_radius,
                outline=border_color,
                width=border_w,
            )

        img = canvas

    else:  # fullbleed (= 기존 overlay)
        h_ratio = layout.get("header_height", 0)
        if h_ratio > 0:
            h_height = int(VIDEO_HEIGHT * h_ratio)
            content_height = VIDEO_HEIGHT - h_height

            target_ratio = VIDEO_WIDTH / content_height
            img_ratio = img.width / img.height
            if img_ratio > target_ratio:
                new_width = int(img.height * target_ratio)
                left = (img.width - new_width) // 2
                img = img.crop((left, 0, left + new_width, img.height))
            else:
                new_height = int(img.width / target_ratio)
                top = (img.height - new_height) // 2
                img = img.crop((0, top, img.width, top + new_height))
            img = img.resize((VIDEO_WIDTH, content_height), Image.LANCZOS)

            bg_color = tuple(layout.get("header_bg_color", [20, 20, 30]))
            canvas = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), bg_color)
            canvas.paste(img, (0, h_height))
            img = canvas
        else:
            img = _fit_to_shorts(img)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", quality=95)
    return output_path


def create_subtitle_overlay(
    output_path: Path,
    style: dict,
    title: str = "",
    subtitle_text: str = "",
    narration: str = "",
    date_str: str = "",
) -> Path:
    """자막 오버레이 (투명 배경 PNG) - 3-layout 시스템

    fullbleed 레이아웃: 풀스크린 이미지 위에 텍스트 오버레이
    split 레이아웃: 상단 헤더 영역 + 하단 나레이션
    three_zone 레이아웃: 상단 헤더 + 중앙 이미지 + 하단 나레이션 존
    """
    overlay = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    layout_type = style.get("layout", {}).get("type", "overlay")

    # 하단 그라데이션 (나레이션 가독성)
    narration_cfg = style.get("narration", {})
    if narration_cfg.get("show", True) and narration:
        if layout_type == "three_zone":
            pass  # 하단이 컬러 배경이므로 그라데이션 불필요
        elif layout_type == "split":
            _draw_bottom_gradient(overlay, alpha_max=100, height_ratio=0.28)
        else:  # fullbleed (overlay)
            _draw_bottom_gradient(overlay)

    # 1. 제목 + 부제 렌더링 (split: 헤더 배경도 여기서 그림)
    _render_title_overlay(overlay, title, subtitle_text, date_str, style)

    # 2. 라벨 렌더링 (배지/강조 텍스트) - 헤더 배경 위에 그려야 함
    _render_label(overlay, style)

    # 2-1. 상단 바 텍스트 (채널명 등)
    _render_top_bar_text(overlay, style)

    # 3. 나레이션 렌더링
    if narration:
        _render_narration(overlay, narration, style)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, "PNG")
    return output_path


def create_teaser_overlay(
    output_path: Path,
    style: dict,
    teaser_text: str,
) -> Path:
    """시리즈 비최종편용 짧은 엔드카드 오버레이."""
    overlay = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    layout_type = style.get("layout", {}).get("type", "overlay")

    if teaser_text:
        if layout_type == "three_zone":
            pass
        elif layout_type == "split":
            _draw_bottom_gradient(overlay, alpha_max=100, height_ratio=0.28)
        else:
            _draw_bottom_gradient(overlay)
        _render_narration(overlay, teaser_text, style)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, "PNG")
    return output_path


# ============================================================
# 내부 헬퍼: 제목/부제/나레이션 렌더링
# ============================================================

def _draw_bottom_gradient(
    overlay: Image.Image,
    alpha_max: int = 120,
    height_ratio: float = 0.35,
) -> None:
    """하단 영역에 검은색 그라데이션 (나레이션 가독성 향상)"""
    gradient_height = int(VIDEO_HEIGHT * height_ratio)
    gradient = Image.new("RGBA", (VIDEO_WIDTH, gradient_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    for i in range(gradient_height):
        alpha = int(alpha_max * (i / gradient_height))  # 0 → alpha_max (위→아래)
        draw.line([(0, i), (VIDEO_WIDTH, i)], fill=(0, 0, 0, alpha))
    overlay.paste(gradient, (0, VIDEO_HEIGHT - gradient_height), gradient)

def _add_letter_spacing(text: str, spacing: int = 1) -> str:
    """글자 사이에 공백을 추가하여 letter-spacing(트래킹) 효과 생성"""
    if spacing <= 0:
        return text
    spacer = " " * spacing
    return spacer.join(text)


def _render_top_bar_text(overlay: Image.Image, style: dict) -> None:
    """상단 바 영역에 채널명 등 텍스트 렌더링"""
    layout = style.get("layout", {})
    text = layout.get("header_top_bar_text")
    bar_h = layout.get("header_top_bar_height", 0)
    if not text or bar_h <= 0:
        return

    draw = ImageDraw.Draw(overlay)
    font_size = layout.get("header_top_bar_text_size", 26)
    color = tuple(layout.get("header_top_bar_text_color", [80, 80, 80]))
    font = get_font(font_size, bold=False)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    align = layout.get("header_top_bar_text_align", "center")
    if align == "left":
        x = 40
    elif align == "right":
        x = VIDEO_WIDTH - text_w - 40
    else:
        x = (VIDEO_WIDTH - text_w) // 2
    y = (bar_h - text_h) // 2
    draw.text((x, y), text, font=font, fill=color + (255,))


def _render_label(
    overlay: Image.Image,
    style: dict,
) -> None:
    """라벨/배지 렌더링 (예: BREAKING ANALYSIS, HOT ISSUE 등)

    split 레이아웃: 헤더 영역 상단 좌측 (x=50)
    overlay 레이아웃: 상단 좌측 (y=20)
    bg_color가 있으면 pill 배경, 없으면 텍스트만 렌더링
    """
    label_cfg = style.get("label", {})
    if not label_cfg.get("show", False):
        return
    if label_cfg.get("inline", False):
        return

    text = label_cfg.get("text", "")
    if not text:
        return

    draw = ImageDraw.Draw(overlay)
    layout_type = style.get("layout", {}).get("type", "overlay")
    font_size = label_cfg.get("font_size", 22)
    font = get_font(font_size, bold=False)  # 라벨은 얇은 고딕
    color = tuple(label_cfg.get("color", [255, 255, 255]))
    bg_color = label_cfg.get("bg_color")
    position = label_cfg.get("position", "tab_left")

    spacing = label_cfg.get("letter_spacing", 1)
    spaced_text = _add_letter_spacing(text, spacing=spacing)

    # 위치 결정 (label_x, label_y로 오버라이드 가능)
    if layout_type == "split":
        layout = style.get("layout", {})
        h_height = int(VIDEO_HEIGHT * layout.get("header_height", 0.16))
        title_cfg_ref = style.get("title", {})
        subtitle_cfg_ref = style.get("subtitle", {})
        lbl_fs = label_cfg.get("font_size", 22)
        lbl_off = lbl_fs + max(8, lbl_fs // 4) * 2 + 16
        t_fs = title_cfg_ref.get("font_size", 72)
        s_fs = subtitle_cfg_ref.get("font_size", 44)
        total_h = lbl_off + t_fs + 8
        if subtitle_cfg_ref.get("show", True):
            total_h += subtitle_cfg_ref.get("gap_before", 0) + s_fs + 8
        top_pad = layout.get("header_top_padding", 0)
        x = label_cfg.get("label_x", 50)
        y = label_cfg.get("label_y", max(16, (h_height - total_h) // 2 + top_pad))
    elif layout_type == "three_zone":
        layout = style.get("layout", {})
        h_height = int(VIDEO_HEIGHT * layout.get("header_height", 0.18))
        title_cfg_ref = style.get("title", {})
        subtitle_cfg_ref = style.get("subtitle", {})
        lbl_fs = label_cfg.get("font_size", 22)
        lbl_off = lbl_fs + max(8, lbl_fs // 4) * 2 + 16
        t_fs = title_cfg_ref.get("font_size", 72)
        s_fs = subtitle_cfg_ref.get("font_size", 44)
        total_h = lbl_off + t_fs + 8
        if subtitle_cfg_ref.get("show", True):
            total_h += s_fs + 8
        top_pad = layout.get("header_top_padding", 0)
        x = label_cfg.get("label_x", 30)
        y = label_cfg.get("label_y", max(16, (h_height - total_h) // 2 + top_pad))
        y += label_cfg.get("y_offset", 0)
    else:  # fullbleed
        x = label_cfg.get("label_x", 50)
        y = label_cfg.get("label_y", 80)

    bbox = draw.textbbox((x, y), spaced_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    if bg_color is not None:
        pad_h = label_cfg.get("pill_pad_h") or max(16, font_size // 2)
        pad_v = label_cfg.get("pill_pad_v") or max(10, font_size // 3)
        radius = text_h // 2 + pad_v
        fill_color = tuple(bg_color) + (255,) if len(bg_color) == 3 else tuple(bg_color)

        corner_r = label_cfg.get("border_radius", radius)

        if position == "pill":
            text_x = x + pad_h
            bbox = draw.textbbox((text_x, y), spaced_text, font=font)
            pill_rect = [
                x,
                bbox[1] - pad_v,
                bbox[2] + pad_h,
                bbox[3] + pad_v,
            ]
            draw.rounded_rectangle(pill_rect, radius=corner_r, fill=fill_color)
            lbl_shadow = label_cfg.get("shadow_offset", 0)
            lbl_shadow_c = tuple(label_cfg.get("shadow_color", [0, 0, 0, 180]))
            if lbl_shadow > 0:
                sf = lbl_shadow_c if len(lbl_shadow_c) >= 4 else lbl_shadow_c[:3] + (180,)
                draw.text((text_x + lbl_shadow, y + lbl_shadow), spaced_text, font=font, fill=sf)
            draw.text((text_x, y), spaced_text, font=font, fill=color + (255,))
            return
        elif position == "pill_center":
            cx = (VIDEO_WIDTH - text_w) // 2
            bbox_c = draw.textbbox((cx, y), spaced_text, font=font)
            pill_rect = [
                bbox_c[0] - pad_h,
                bbox_c[1] - pad_v,
                bbox_c[2] + pad_h,
                bbox_c[3] + pad_v,
            ]
            draw.rounded_rectangle(pill_rect, radius=corner_r, fill=fill_color)
            x = cx
        else:  # tab_left (기본)
            tab_rect = [
                -radius,
                bbox[1] - pad_v,
                bbox[2] + pad_h,
                bbox[3] + pad_v,
            ]
            draw.rounded_rectangle(tab_rect, radius=radius, fill=fill_color)

    lbl_shadow = label_cfg.get("shadow_offset", 0)
    lbl_shadow_c = tuple(label_cfg.get("shadow_color", [0, 0, 0, 180]))
    if lbl_shadow > 0:
        sf = lbl_shadow_c if len(lbl_shadow_c) >= 4 else lbl_shadow_c[:3] + (180,)
        draw.text((x + lbl_shadow, y + lbl_shadow), spaced_text, font=font, fill=sf)
    draw.text(
        (x, y), spaced_text, font=font,
        fill=color + (255,),
    )


def _render_title_overlay(
    overlay: Image.Image,
    title: str,
    subtitle_text: str,
    date_str: str,
    style: dict,
) -> None:
    """레이아웃 타입에 따라 제목 + 부제 + 날짜 렌더링 분기"""
    draw = ImageDraw.Draw(overlay)
    layout_type = style.get("layout", {}).get("type", "overlay")

    if layout_type == "split":
        _render_title_split(draw, title, subtitle_text, date_str, style)
    elif layout_type == "three_zone":
        _render_title_three_zone(draw, title, subtitle_text, style)
    else:  # fullbleed (overlay)
        _render_title_overlay_mode(draw, title, subtitle_text, style)


def _render_title_split(
    draw: ImageDraw.Draw,
    title: str,
    subtitle_text: str,
    date_str: str,
    style: dict,
) -> None:
    """split 레이아웃: 헤더 영역에 제목/부제/날짜 렌더링"""
    max_title_lines = 1
    layout = style.get("layout", {})
    h_ratio = layout.get("header_height", 0.16)
    h_height = int(VIDEO_HEIGHT * h_ratio)
    bg_color = tuple(layout.get("header_bg_color", [245, 235, 210]))

    # 헤더 배경 (반투명)
    draw.rectangle(
        [(0, 0), (VIDEO_WIDTH, h_height)],
        fill=bg_color + (240,),
    )

    title_cfg = style.get("title", {})
    subtitle_cfg = style.get("subtitle", {})
    label_cfg = style.get("label", {})
    align = title_cfg.get("align", "center")  # "left" or "center"
    margin_left = 50

    # 라벨이 있으면 상단에 공간 확보
    label_offset = 0
    if label_cfg.get("show", False) and label_cfg.get("text"):
        label_fs = label_cfg.get("font_size", 28)
        label_offset = label_fs + max(8, label_fs // 4) * 2 + 16  # pill height + gap

    title_font_size = title_cfg.get("font_size", 72)
    sub_font_size = subtitle_cfg.get("font_size", 44)
    clean_title = _strip_emoji(title) if title else ""
    title_font = get_font(title_font_size, bold=True)
    max_w = VIDEO_WIDTH - 100 if align == "center" else VIDEO_WIDTH - margin_left - 50
    preview_title_lines = []
    if clean_title and title_cfg.get("show", True):
        one_line = _truncate_to_width(clean_title, title_font, max_w, draw)
        if one_line:
            preview_title_lines = [one_line][:max_title_lines]

    if "title_y" in title_cfg:
        y = title_cfg["title_y"]
    else:
        title_h = len(preview_title_lines) * (title_font_size + 8)
        total_text_h = label_offset + title_h
        if subtitle_text and subtitle_cfg.get("show", True):
            total_text_h += subtitle_cfg.get("gap_before", 0) + sub_font_size + 8
        top_pad = layout.get("header_top_padding", 0)
        y = max(16, (h_height - total_text_h) // 2 + top_pad)
        y += label_offset

    # 제목
    if title and title_cfg.get("show", True):
        font_color = tuple(title_cfg.get("color", [30, 30, 30]))
        title_lines = preview_title_lines

        stroke_w = title_cfg.get("stroke_width", 0)
        stroke_c = tuple(title_cfg.get("stroke_color", [0, 0, 0]))
        shadow_offset = title_cfg.get("shadow_offset", 0)
        shadow_color = tuple(title_cfg.get("shadow_color", [0, 0, 0, 180]))

        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_width = bbox[2] - bbox[0]
            if align == "left":
                x = margin_left
            else:
                x = (VIDEO_WIDTH - text_width) // 2
            # 그림자 (먼저 그리기)
            if shadow_offset > 0:
                shadow_fill = shadow_color if len(shadow_color) >= 4 else shadow_color[:3] + (180,)
                draw.text((x + shadow_offset, y + shadow_offset), line, font=title_font, fill=shadow_fill)
            kwargs = {"fill": font_color + (255,)}
            if stroke_w > 0:
                kwargs["stroke_width"] = stroke_w
                kwargs["stroke_fill"] = stroke_c + (255,)
            draw.text((x, y), line, font=title_font, **kwargs)
            y += title_font_size + 8

    # 부제 (split 헤더)
    if subtitle_text and subtitle_cfg.get("show", True):
        y += subtitle_cfg.get("gap_before", 0)
        clean_sub = _strip_emoji(subtitle_text)
        sub_color = tuple(subtitle_cfg.get("color", [80, 80, 80]))
        sub_font = get_font(sub_font_size, bold=False)
        max_w = VIDEO_WIDTH - 100 if align == "center" else VIDEO_WIDTH - margin_left - 50
        sub_lines = _wrap_text(clean_sub, sub_font, max_w, draw)

        stroke_w = subtitle_cfg.get("stroke_width", 0)
        stroke_c = tuple(subtitle_cfg.get("stroke_color", [0, 0, 0]))
        sub_shadow_offset = subtitle_cfg.get("shadow_offset", 0)
        sub_shadow_color = tuple(subtitle_cfg.get("shadow_color", [0, 0, 0, 180]))

        for line in sub_lines[:1]:
            bbox = draw.textbbox((0, 0), line, font=sub_font)
            text_width = bbox[2] - bbox[0]
            if align == "left":
                x = margin_left
            else:
                x = (VIDEO_WIDTH - text_width) // 2
            if sub_shadow_offset > 0:
                shadow_fill = sub_shadow_color if len(sub_shadow_color) >= 4 else sub_shadow_color[:3] + (180,)
                draw.text((x + sub_shadow_offset, y + sub_shadow_offset), line, font=sub_font, fill=shadow_fill)
            kwargs = {"fill": sub_color + (255,)}
            if stroke_w > 0:
                kwargs["stroke_width"] = stroke_w
                kwargs["stroke_fill"] = stroke_c + (255,)
            draw.text((x, y), line, font=sub_font, **kwargs)
            y += sub_font_size + 8

    # 날짜 (우측 상단) - date_color 지원
    if date_str:
        date_font = get_font(24, bold=False)
        clean_date = _strip_emoji(date_str)
        bbox = draw.textbbox((0, 0), clean_date, font=date_font)
        date_w = bbox[2] - bbox[0]
        date_color_cfg = style.get("date_color")
        if date_color_cfg:
            date_fill = tuple(date_color_cfg) + (180,)
        else:
            date_fill = (150, 150, 150, 180)
        draw.text(
            (VIDEO_WIDTH - date_w - 30, 12),
            clean_date,
            font=date_font,
            fill=date_fill,
        )


def _render_title_three_zone(
    draw: ImageDraw.Draw,
    title: str,
    subtitle_text: str,
    style: dict,
) -> None:
    """three_zone 레이아웃: 헤더 영역에 제목/부제 렌더링 (배경은 base에 이미 있음)"""
    max_title_lines = 1
    layout = style.get("layout", {})
    h_ratio = layout.get("header_height", 0.18)
    h_height = int(VIDEO_HEIGHT * h_ratio)

    title_cfg = style.get("title", {})
    subtitle_cfg = style.get("subtitle", {})
    label_cfg = style.get("label", {})
    align = title_cfg.get("align", "center")  # "left" or "center"
    margin_left = 50  # 왼쪽 마진 (left 정렬 시)

    # 라벨이 있으면 상단에 공간 확보
    label_offset = 0
    if label_cfg.get("show", False) and label_cfg.get("text"):
        label_fs = label_cfg.get("font_size", 28)
        label_offset = label_fs + max(8, label_fs // 4) * 2 + 16  # pill height + gap

    # 헤더 내 수직 배치 (gap_before는 centering 제외 → 타이틀 고정, 서브타이틀만 내려감)
    title_font_size = title_cfg.get("font_size", 72)
    sub_font_size = subtitle_cfg.get("font_size", 44)
    clean_title = _strip_emoji(title) if title else ""
    title_font = get_style_font(title_font_size, bold=True, style=style, section_font=title_cfg.get("font_family"))
    max_w = VIDEO_WIDTH - 100 if align == "center" else VIDEO_WIDTH - margin_left - 50
    preview_title_lines = []
    if clean_title and title_cfg.get("show", True):
        one_line = _truncate_to_width(clean_title, title_font, max_w, draw)
        if one_line:
            preview_title_lines = [one_line][:max_title_lines]
    total_text_h = label_offset + len(preview_title_lines) * (title_font_size + 8)
    if subtitle_text and subtitle_cfg.get("show", True):
        total_text_h += sub_font_size + 8
    top_pad = layout.get("header_top_padding", 0)
    y = max(16, (h_height - total_text_h) // 2 + top_pad)

    # 라벨이 있으면 그 아래부터 제목 시작
    y += label_offset
    title_top_gap = title_cfg.get("top_gap", 0)

    # 제목 (top_gap은 타이틀 그릴 때만 적용, y 누적에는 미반영)
    if title and title_cfg.get("show", True):
        font_color = tuple(title_cfg.get("color", [30, 30, 30]))
        title_lines = preview_title_lines

        stroke_w = title_cfg.get("stroke_width", 0)
        stroke_c = tuple(title_cfg.get("stroke_color", [0, 0, 0]))

        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_width = bbox[2] - bbox[0]
            if align == "left":
                x = margin_left
            else:
                x = (VIDEO_WIDTH - text_width) // 2
            kwargs = {"fill": font_color + (255,)}
            if stroke_w > 0:
                kwargs["stroke_width"] = stroke_w
                kwargs["stroke_fill"] = stroke_c + (255,)
            draw.text((x, y + title_top_gap), line, font=title_font, **kwargs)
            y += title_font_size + 8

    # 부제 (three_zone 헤더)
    if subtitle_text and subtitle_cfg.get("show", True):
        y += subtitle_cfg.get("gap_before", 0)
        clean_sub = _strip_emoji(subtitle_text)
        sub_color = tuple(subtitle_cfg.get("color", [80, 80, 80]))
        sub_font = get_font(sub_font_size, bold=False)
        max_w = VIDEO_WIDTH - 100 if align == "center" else VIDEO_WIDTH - margin_left - 50
        sub_lines = _wrap_text(clean_sub, sub_font, max_w, draw)

        stroke_w = subtitle_cfg.get("stroke_width", 0)
        stroke_c = tuple(subtitle_cfg.get("stroke_color", [0, 0, 0]))

        for line in sub_lines[:1]:
            bbox = draw.textbbox((0, 0), line, font=sub_font)
            text_width = bbox[2] - bbox[0]
            if align == "left":
                x = margin_left
            else:
                x = (VIDEO_WIDTH - text_width) // 2
            kwargs = {"fill": sub_color + (255,)}
            if stroke_w > 0:
                kwargs["stroke_width"] = stroke_w
                kwargs["stroke_fill"] = stroke_c + (255,)
            draw.text((x, y), line, font=sub_font, **kwargs)
            y += sub_font_size + 8


def _render_title_overlay_mode(
    draw: ImageDraw.Draw,
    title: str,
    subtitle_text: str,
    style: dict,
) -> None:
    """overlay 레이아웃: 이미지 위에 제목/부제 오버레이"""
    title_cfg = style.get("title", {})
    subtitle_cfg = style.get("subtitle", {})
    label_cfg = style.get("label", {})

    bg = title_cfg.get("bg", "none")
    show_title = title and title_cfg.get("show", True)
    show_sub = subtitle_text and subtitle_cfg.get("show", True)
    narration_cfg = style.get("narration", {})
    has_narration = narration_cfg.get("show", True)
    inline_label = label_cfg.get("inline", False) and label_cfg.get("show", False)

    # --- 인라인 라벨+타이틀 모드 ---
    if inline_label and show_title:
        _render_inline_label_title(draw, title, subtitle_text, style)
        return

    # 라벨이 있으면 y_start를 아래로 밀기
    if label_cfg.get("show", False) and label_cfg.get("text"):
        y_start = 120 + 36
    else:
        y_start = 120

    # --- 폰트/텍스트 사전 준비 ---
    title_font_size = title_cfg.get("font_size", 80)
    title_font_color = tuple(title_cfg.get("color", [255, 255, 255]))
    title_font = get_font(title_font_size, bold=True)
    title_line_h = title_font_size + 14
    title_stroke_w = title_cfg.get("stroke_width", 4)
    title_stroke_c = tuple(title_cfg.get("stroke_color", [0, 0, 0]))
    title_lines = []
    if show_title:
        one_line = _truncate_to_width(_strip_emoji(title), title_font, VIDEO_WIDTH - 120, draw)
        if one_line:
            title_lines = [one_line]

    sub_font_size = subtitle_cfg.get("font_size", 48)
    sub_color = tuple(subtitle_cfg.get("color", [255, 255, 200]))
    sub_font = get_font(sub_font_size, bold=False)
    sub_line_h = sub_font_size + 10
    sub_stroke_w = subtitle_cfg.get("stroke_width", 3)
    sub_stroke_c = tuple(subtitle_cfg.get("stroke_color", [0, 0, 0]))
    sub_lines = []
    if show_sub:
        sub_lines = _wrap_text(_strip_emoji(subtitle_text), sub_font, VIDEO_WIDTH - 120, draw)[:2]

    # --- 제목+부제 총 높이 계산 ---
    gap = 10
    total_h = len(title_lines) * title_line_h
    if title_lines and sub_lines:
        total_h += gap
    total_h += len(sub_lines) * sub_line_h

    if not has_narration and total_h > 0:
        y_start = max(120, (VIDEO_HEIGHT // 4) - (total_h // 2))

    if bg == "dark_bar" and total_h > 0:
        padding = 28
        draw.rectangle(
            [(0, y_start - padding), (VIDEO_WIDTH, y_start + total_h + padding)],
            fill=(0, 0, 0, 180),
        )

    # --- 제목 렌더 ---
    y = y_start
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        text_w = bbox[2] - bbox[0]
        x = (VIDEO_WIDTH - text_w) // 2
        kwargs = {"fill": title_font_color + (255,)}
        if bg == "outline" or title_stroke_w > 0:
            kwargs["stroke_width"] = title_stroke_w
            kwargs["stroke_fill"] = title_stroke_c + (255,)
        draw.text((x, y), line, font=title_font, **kwargs)
        y += title_line_h

    # --- 부제 렌더 ---
    if sub_lines:
        y += gap
        for line in sub_lines:
            bbox = draw.textbbox((0, 0), line, font=sub_font)
            text_w = bbox[2] - bbox[0]
            x = (VIDEO_WIDTH - text_w) // 2
            kwargs = {"fill": sub_color + (255,)}
            if sub_stroke_w > 0:
                kwargs["stroke_width"] = sub_stroke_w
                kwargs["stroke_fill"] = sub_stroke_c + (255,)
            draw.text((x, y), line, font=sub_font, **kwargs)
            y += sub_line_h


def _render_inline_label_title(
    draw: ImageDraw.Draw,
    title: str,
    subtitle_text: str,
    style: dict,
) -> None:
    """fullbleed 인라인 모드: 라벨 pill + 타이틀을 같은 줄에 배치"""
    label_cfg = style.get("label", {})
    title_cfg = style.get("title", {})

    margin_left = 50
    y_start = label_cfg.get("label_y", 130)

    # --- 라벨 pill 그리기 ---
    lbl_text = label_cfg.get("text", "")
    lbl_fs = label_cfg.get("font_size", 40)
    lbl_font = get_font(lbl_fs, bold=True)
    lbl_color = tuple(label_cfg.get("color", [255, 255, 255]))
    lbl_bg = label_cfg.get("bg_color", [110, 60, 175])
    lbl_spacing = label_cfg.get("letter_spacing", 0)
    lbl_spaced = _add_letter_spacing(lbl_text, spacing=lbl_spacing)

    pad_h = max(16, lbl_fs // 2)
    pad_v = max(10, lbl_fs // 3)
    lbl_bbox = draw.textbbox((margin_left + pad_h, y_start), lbl_spaced, font=lbl_font)
    lbl_th = lbl_bbox[3] - lbl_bbox[1]
    corner_r = label_cfg.get("border_radius", lbl_th // 2 + pad_v)
    fill_c = tuple(lbl_bg) + (255,) if len(lbl_bg) == 3 else tuple(lbl_bg)

    pill_rect = [
        margin_left,
        lbl_bbox[1] - pad_v,
        lbl_bbox[2] + pad_h,
        lbl_bbox[3] + pad_v,
    ]
    draw.rounded_rectangle(pill_rect, radius=corner_r, fill=fill_c)
    draw.text((margin_left + pad_h, y_start), lbl_spaced, font=lbl_font, fill=lbl_color + (255,))

    # --- 타이틀 (라벨 오른쪽에서 시작) ---
    title_fs = title_cfg.get("font_size", 80)
    title_font = get_font(title_fs, bold=True)
    title_color = tuple(title_cfg.get("color", [255, 255, 255]))
    title_stroke_w = title_cfg.get("stroke_width", 3)
    title_stroke_c = tuple(title_cfg.get("stroke_color", [0, 0, 0]))
    clean_title = _strip_emoji(title)

    title_x_start = pill_rect[2] + 16
    first_line_max_w = VIDEO_WIDTH - title_x_start - 60

    pill_center_y = (pill_rect[1] + pill_rect[3]) // 2
    title_y = pill_center_y - title_fs // 2

    # 제목은 1줄 고정 (초과 시 말줄임)
    first_line_chars = _truncate_to_width(clean_title, title_font, first_line_max_w, draw)

    kwargs = {"fill": title_color + (255,)}
    if title_stroke_w > 0:
        kwargs["stroke_width"] = title_stroke_w
        kwargs["stroke_fill"] = title_stroke_c + (255,)

    if first_line_chars:
        draw.text((title_x_start, title_y), first_line_chars, font=title_font, **kwargs)


def _render_narration(
    overlay: Image.Image,
    narration: str,
    style: dict,
) -> None:
    """하단에 나레이션 텍스트 렌더링"""
    narration_cfg = style.get("narration", {})
    if not narration_cfg.get("show", True):
        return

    clean_narration = _strip_emoji(narration)
    if not clean_narration:
        return

    draw = ImageDraw.Draw(overlay)
    font_size = narration_cfg.get("font_size", 54)
    font = get_style_font(font_size, bold=True, style=style, section_font=narration_cfg.get("font_family"))
    text_color = tuple(narration_cfg.get("color", [255, 255, 255]))
    bg = narration_cfg.get("bg", "outline")

    layout = style.get("layout", {})
    layout_type = layout.get("type", "overlay")

    margin_x = 60
    lines = _wrap_text(clean_narration, font, VIDEO_WIDTH - margin_x * 2, draw)
    line_height = font_size + 18
    total_height = len(lines) * line_height

    # 하단 배치 - 레이아웃별 y 위치 결정
    if layout_type == "three_zone":
        bottom_height = layout.get("bottom_height", 0.25)
        bottom_zone_top = int(VIDEO_HEIGHT * (1 - bottom_height))
        # 이미지 아래 배치 (적당한 여백)
        y_start = bottom_zone_top + 60
    elif layout_type == "split":
        # split: 블러 영역 내 상단에 배치
        blur_h_ratio = layout.get("bottom_blur_height", 0.25)
        blur_top = int(VIDEO_HEIGHT * (1 - blur_h_ratio))
        y_start = blur_top + 60
    else:
        # fullbleed: 하단 배치 (유튜브 UI 피함)
        y_start = VIDEO_HEIGHT - total_height - 280

    if bg in ("clean_box", "dark_box"):
        # 반투명 둥근 사각형 배경 + 텍스트
        bg_color = tuple(narration_cfg.get("bg_color", [255, 255, 255, 210]))
        padding_v = 30
        padding_h = 50

        # 텍스트 최대 너비 계산 → 박스를 텍스트에 맞게 유동 크기
        max_text_w = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            max_text_w = max(max_text_w, bbox[2] - bbox[0])

        box_w = max_text_w + padding_h * 2
        box_x = (VIDEO_WIDTH - box_w) // 2
        box_rect = [
            box_x,
            y_start - padding_v,
            box_x + box_w,
            y_start + total_height + padding_v,
        ]

        # 그림자 효과 (shadow 설정 시)
        shadow_offset = narration_cfg.get("shadow_offset", 0)
        if shadow_offset > 0:
            shadow_color = tuple(narration_cfg.get("shadow_color", [0, 0, 0, 60]))
            shadow_rect = [
                box_rect[0] + shadow_offset,
                box_rect[1] + shadow_offset,
                box_rect[2] + shadow_offset,
                box_rect[3] + shadow_offset,
            ]
            draw.rounded_rectangle(shadow_rect, radius=28, fill=shadow_color)

        draw.rounded_rectangle(
            box_rect,
            radius=28,
            fill=tuple(bg_color),
        )

        # 테두리 (border_color 설정 시)
        border_color = narration_cfg.get("border_color")
        border_width = narration_cfg.get("border_width", 0)
        if border_color and border_width > 0:
            outline_c = tuple(border_color) + (255,) if len(border_color) == 3 else tuple(border_color)
            draw.rounded_rectangle(
                box_rect,
                radius=28,
                outline=outline_c,
                width=border_width,
            )

        # 텍스트 stroke 지원
        stroke_w = narration_cfg.get("stroke_width", 0)
        stroke_c = tuple(narration_cfg.get("stroke_color", [0, 0, 0]))

        for i, line in enumerate(lines):
            y = y_start + i * line_height
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (VIDEO_WIDTH - text_width) // 2
            kwargs = {"fill": text_color + (255,)}
            if stroke_w > 0:
                kwargs["stroke_width"] = stroke_w
                kwargs["stroke_fill"] = stroke_c + (255,)
            draw.text(
                (x, y), line, font=font,
                **kwargs,
            )

    elif bg == "dark_bar":
        bg_color = tuple(narration_cfg.get("bg_color", [0, 0, 0, 220]))
        padding_v = narration_cfg.get("bar_padding_v", 32)
        padding_h = narration_cfg.get("bar_padding_h", 40)

        text_positions = []
        actual_top = float('inf')
        actual_bottom = 0
        for i, line in enumerate(lines):
            cy = y_start + i * line_height
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (VIDEO_WIDTH - tw) // 2
            actual_top = min(actual_top, cy + bbox[1])
            actual_bottom = max(actual_bottom, cy + bbox[3])
            text_positions.append((tx, cy, line))

        bar_rect = [
            0,
            actual_top - padding_v,
            VIDEO_WIDTH,
            actual_bottom + padding_v,
        ]
        draw.rectangle(bar_rect, fill=tuple(bg_color))

        stroke_w = narration_cfg.get("stroke_width", 0)
        stroke_c = tuple(narration_cfg.get("stroke_color", [0, 0, 0]))

        for tx, ty, line in text_positions:
            kwargs = {"fill": text_color + (255,)}
            if stroke_w > 0:
                kwargs["stroke_width"] = stroke_w
                kwargs["stroke_fill"] = stroke_c + (255,)
            draw.text((tx, ty), line, font=font, **kwargs)

    elif bg == "bordered_box":
        # 반투명 배경 + 테두리 + 둥근 모서리
        bg_color = tuple(narration_cfg.get("bg_color", [15, 20, 40, 160]))
        border_color = tuple(narration_cfg.get("border_color", [80, 100, 160, 180]))
        padding_v = 24
        padding_h = 40
        border_width = 2
        radius = 16

        box_rect = [
            padding_h,
            y_start - padding_v,
            VIDEO_WIDTH - padding_h,
            y_start + total_height + padding_v,
        ]

        # 배경 채우기
        draw.rounded_rectangle(
            box_rect,
            radius=radius,
            fill=tuple(bg_color),
        )
        # 테두리 그리기
        draw.rounded_rectangle(
            box_rect,
            radius=radius,
            outline=tuple(border_color),
            width=border_width,
        )

        for i, line in enumerate(lines):
            y = y_start + i * line_height
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (VIDEO_WIDTH - text_width) // 2
            draw.text(
                (x, y), line, font=font,
                fill=text_color + (255,),
            )

    elif bg == "outline":
        # 외곽선 텍스트, 배경 없음
        stroke_w = narration_cfg.get("stroke_width", 4)
        stroke_c = tuple(narration_cfg.get("stroke_color", [0, 0, 0]))
        for i, line in enumerate(lines):
            y = y_start + i * line_height
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (VIDEO_WIDTH - text_width) // 2
            draw.text(
                (x, y), line, font=font,
                fill=text_color + (255,),
                stroke_width=stroke_w,
                stroke_fill=stroke_c + (255,),
            )

    else:  # "none" - 나레이션 텍스트 표시 안 함
        pass


# ============================================================
# 공용 유틸리티
# ============================================================

def _fit_to_shorts(img: Image.Image) -> Image.Image:
    """이미지를 9:16 비율로 크롭 후 리사이즈"""
    target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT  # 9:16
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        new_width = int(img.height * target_ratio)
        left = (img.width - new_width) // 2
        img = img.crop((left, 0, left + new_width, img.height))
    else:
        new_height = int(img.width / target_ratio)
        top = (img.height - new_height) // 2
        img = img.crop((0, top, img.width, top + new_height))

    return img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)


def _truncate_to_width(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.Draw,
    suffix: str = "...",
) -> str:
    """단일 라인 폭 제한에 맞게 텍스트 자르기 (필요 시 말줄임)."""
    if not text:
        return ""

    bbox = draw.textbbox((0, 0), text, font=font)
    if bbox[2] - bbox[0] <= max_width:
        return text

    suffix_bbox = draw.textbbox((0, 0), suffix, font=font)
    suffix_width = suffix_bbox[2] - suffix_bbox[0]
    if suffix_width > max_width:
        suffix = ""

    trimmed = text
    while trimmed:
        trial = trimmed + suffix
        trial_bbox = draw.textbbox((0, 0), trial, font=font)
        if trial_bbox[2] - trial_bbox[0] <= max_width:
            return trial
        trimmed = trimmed[:-1]

    return suffix


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.Draw,
) -> list[str]:
    """텍스트를 최대 너비에 맞게 줄바꿈.

    기본은 공백(어절) 기준으로 묶고, 공백이 없는 긴 토큰만 예외적으로 문자 단위 분할한다.
    """

    def text_width(value: str) -> int:
        bbox = draw.textbbox((0, 0), value, font=font)
        return bbox[2] - bbox[0]

    def hard_wrap_token(token: str) -> list[str]:
        if not token:
            return []

        wrapped: list[str] = []
        current = ""
        for char in token:
            candidate = current + char
            if current and text_width(candidate) > max_width:
                wrapped.append(current)
                current = char
            else:
                current = candidate
        if current:
            wrapped.append(current)
        return wrapped

    lines: list[str] = []

    for raw_paragraph in str(text or "").splitlines() or [str(text or "")]:
        paragraph = re.sub(r"\s+", " ", raw_paragraph).strip()
        if not paragraph:
            continue

        current_line = ""
        for token in paragraph.split(" "):
            candidate = token if not current_line else f"{current_line} {token}"
            if text_width(candidate) <= max_width:
                current_line = candidate
                continue

            if current_line:
                lines.append(current_line)
                current_line = ""

            if text_width(token) <= max_width:
                current_line = token
                continue

            token_lines = hard_wrap_token(token)
            lines.extend(token_lines[:-1])
            current_line = token_lines[-1] if token_lines else ""

        if current_line:
            lines.append(current_line)

    # orphan 방지: 마지막 줄이 너무 짧으면 공백 위치 기준으로만 재분배
    if len(lines) >= 2 and len(lines[-1].replace(" ", "")) <= 4:
        merged = f"{lines[-2].rstrip()} {lines[-1].lstrip()}".strip()
        split_candidates = []
        midpoint = len(merged) // 2

        for match in re.finditer(r"\s+", merged):
            left = merged[:match.start()].rstrip()
            right = merged[match.end():].lstrip()
            if not left or not right:
                continue
            if text_width(left) > max_width or text_width(right) > max_width:
                continue

            right_len = len(right.replace(" ", ""))
            split_candidates.append((
                0 if right_len > 4 else 1,
                abs(match.start() - midpoint),
                abs(text_width(left) - text_width(right)),
                left,
                right,
            ))

        if split_candidates:
            _, _, _, left, right = min(split_candidates)
            lines[-2] = left
            lines[-1] = right

    return lines
