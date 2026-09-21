#!/usr/bin/env python3.12
"""pptx 도형을 PIL 로 직접 그려 잘림·겹침을 잡는다.

    /usr/local/bin/python3.12 check_layout.py

이 환경엔 LibreOffice 가 없어 pptx 를 실제로 렌더할 수 없다. 그래서 도형의
좌표·색·문단 글꼴을 읽어 960×540 을 2배로 그린다. PowerPoint 와 픽셀이 같지는
않지만, 상자 밖으로 넘치는 글과 겹치는 도형은 그대로 드러난다.

줄바꿈은 Pretendard 실측 폭(PIL)으로 접는다 — 눈대중이 아니라 글꼴 메트릭이다.
"""

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.util import Emu

HERE = Path(__file__).parent
SCALE = 2
FONTS = {
    (False,): "Pretendard-Regular.otf",
    (True,): "Pretendard-Bold.otf",
}
FONT_DIR = Path.home() / "Library" / "Fonts"
_cache: dict[tuple[float, bool], ImageFont.FreeTypeFont] = {}


def font(size_pt: float, bold: bool):
    key = (round(size_pt, 1), bold)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(FONT_DIR / FONTS[(bold,)]), size_pt * SCALE)
    return _cache[key]


def pt(v) -> float:
    return Emu(v).pt * SCALE


def wrap(text: str, fnt, max_w: float) -> list[str]:
    """PowerPoint 와 같은 규칙: 띄어쓰기 우선, 한 낱말이 넘치면 글자 단위로 자른다."""
    lines, line = [], ""
    for word in text.split(" "):
        trial = f"{line} {word}".strip()
        if line and fnt.getlength(trial) > max_w:
            lines.append(line)
            line = word
        else:
            line = trial
        while fnt.getlength(line) > max_w and len(line) > 1:
            cut = len(line) - 1
            while cut > 1 and fnt.getlength(line[:cut]) > max_w:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    if line:
        lines.append(line)
    return lines or [""]


def rgb(color, default=(0, 0, 0)):
    try:
        return tuple(color.rgb)
    except (AttributeError, TypeError, ValueError):
        return default


def main() -> int:
    src = HERE / "out" / "SalesLuv_서비스소개서.pptx"
    if not src.exists():
        sys.exit("pptx 가 없습니다 — 먼저 `python3.12 build_pptx.py`")

    prs = Presentation(src)
    outdir = HERE / "out" / "check"
    outdir.mkdir(parents=True, exist_ok=True)
    problems = []

    for n, slide in enumerate(prs.slides, 1):
        img = Image.new("RGB", (960 * SCALE, 540 * SCALE), "white")
        draw = ImageDraw.Draw(img)
        boxes = []

        for shape in slide.shapes:
            x, y = pt(shape.left), pt(shape.top)
            w, h = pt(shape.width), pt(shape.height)

            if shape.shape_type == 13:  # PICTURE
                pic = Image.open(io.BytesIO(shape.image.blob)).convert("RGBA")
                pic = pic.resize((max(1, round(w)), max(1, round(h))), Image.LANCZOS)
                img.paste(pic, (round(x), round(y)), pic)
                boxes.append(("picture", x, y, w, h))
                continue

            if shape.has_text_frame and not shape.text_frame.text and hasattr(shape, "fill"):
                draw.rectangle(
                    [x, y, x + w, y + h],
                    fill=rgb(shape.fill.fore_color, (255, 255, 255)),
                    outline=rgb(shape.line.color, (229, 231, 235)),
                )
                boxes.append(("card", x, y, w, h))
                continue

            if not shape.has_text_frame:
                continue

            # 번호 원처럼 채움이 있는 도형은 배경부터 그린다.
            try:
                if shape.fill.type is not None and shape.fill.type == 1:
                    draw.ellipse([x, y, x + w, y + h], fill=rgb(shape.fill.fore_color))
            except (AttributeError, ValueError):
                pass

            cy = y
            for para in shape.text_frame.paragraphs:
                runs = para.runs
                if not runs:
                    continue
                run = runs[0]
                size = (run.font.size or Emu(0)).pt or 9
                fnt = font(size, bool(run.font.bold))
                lead = (para.line_spacing.pt if para.line_spacing else size * 1.45) * SCALE
                color = rgb(run.font.color, (17, 24, 39))
                for line in wrap("".join(r.text for r in runs), fnt, w):
                    tx = x + (w - fnt.getlength(line)) / 2 if str(para.alignment) == "CENTER (2)" else x
                    draw.text((tx, cy + (lead - size * SCALE) / 2), line, font=fnt, fill=color)
                    cy += lead
            if cy > y + h + 1:
                problems.append(
                    f"슬라이드 {n}: 글이 상자를 {(cy - y - h) / SCALE:.0f}pt 넘침 "
                    f"— {shape.text_frame.text[:22]!r}"
                )

        # 카드끼리 겹치면 좌표가 틀어진 것이다.
        cards = [b for b in boxes if b[0] == "card"]
        for i, (_, ax, ay, aw, ah) in enumerate(cards):
            for _, bx, by, bw, bh in cards[i + 1 :]:
                if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                    problems.append(f"슬라이드 {n}: 카드가 겹침")

        img.save(outdir / f"{n:02d}.png")

    for line in problems:
        print("  !", line)
    print(f"  → out/check/ ({n}장), 문제 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
