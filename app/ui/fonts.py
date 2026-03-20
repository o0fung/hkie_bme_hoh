import os

import pygame

_LATIN_FONT_CANDIDATES = [
    "Arial",
    "Liberation Sans",
    "DejaVu Sans",
    "Noto Sans",
]

_CJK_FONT_CANDIDATES = [
    "PingFang TC",
    "PingFang SC",
    "PingFang HK",
    "Hiragino Sans GB",
    "Hiragino Sans CNS",
    "Heiti TC",
    "Heiti SC",
    "STHeiti",
    "Songti SC",
    "Noto Sans CJK TC",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Noto Sans TC",
    "Noto Sans SC",
    "Source Han Sans TC",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "Microsoft JhengHei",
    "PingFang TC",
    "SimHei",
    "SimSun",
    "Arial Unicode MS",
    "Droid Sans Fallback",
]

_CJK_FONT_PATH_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Hiragino Sans CNS.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
]

_CJK_GLYPH_PROBE_TEXT = "繁體中文简体中文設定设置鏡像"


def font_supports_text(font: pygame.font.Font, text: str) -> bool:
    """Return True only when every glyph in text exists in the font."""
    try:
        metrics = font.metrics(text)
    except Exception:
        return False
    if not metrics:
        return False
    return all(metric is not None for metric in metrics)


def pick_font(size: int, prefer_cjk: bool = False) -> pygame.font.Font:
    """
    Resolve a font that supports requested glyphs.

    The CJK probe check avoids square-box glyphs in multilingual UI labels.
    """
    candidates = (
        _CJK_FONT_CANDIDATES + _LATIN_FONT_CANDIDATES
        if prefer_cjk
        else _LATIN_FONT_CANDIDATES + _CJK_FONT_CANDIDATES
    )
    seen_paths = set()
    for name in candidates:
        path = pygame.font.match_font(name)
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            font = pygame.font.Font(path, size)
        except Exception:
            continue
        if not prefer_cjk or font_supports_text(font, _CJK_GLYPH_PROBE_TEXT):
            return font

    if prefer_cjk:
        for path in _CJK_FONT_PATH_CANDIDATES:
            if not os.path.exists(path):
                continue
            try:
                font = pygame.font.Font(path, size)
            except Exception:
                continue
            if font_supports_text(font, _CJK_GLYPH_PROBE_TEXT):
                return font
    return pygame.font.Font(None, size)
