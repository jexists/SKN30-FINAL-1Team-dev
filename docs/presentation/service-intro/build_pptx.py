#!/usr/bin/env python3.12
"""pages.json + shots/*.png → 편집 가능한 서비스 소개서 pptx.

    /usr/local/bin/python3.12 build_pptx.py

웹 화면 캡처만 그림이고 나머지 글은 전부 PowerPoint 텍스트 상자다.
python-pptx 는 python3.12 에만 있다.

좌표계는 960×540 pt = PowerPoint Wide(13.333×7.5in). 1pt = 1px 로 설계했다.
아래 상수가 MASTER TEMPLATE 이다. 장마다 참조만 하므로 페이지별 디자인이 갈릴 수 없다.
"""

import json
import os
import sys
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Pt

HERE = Path(__file__).parent

# Keynote 의 슬라이드 이미지 내보내기는 1pt = 1px 이라 960×540 PNG 밖에 안 나온다.
# 1920×1080 이 필요할 때만 DECK_SCALE=2 로 좌표와 글자를 통째로 2배 키워 한 벌 더 굽는다.
# 비율이 전부 같으므로 보이는 모습은 똑같고 픽셀만 커진다.
SCALE = float(os.environ.get("DECK_SCALE", 1))


def P(value):
    """pt 값에 배율을 먹여 EMU 로."""
    return Pt(value * SCALE)

# ── 색 (LOCKED) ────────────────────────────────────────────────────────────
BLUE = RGBColor(0x25, 0x63, 0xEB)
NAVY = RGBColor(0x1E, 0x3A, 0x5F)
TEXT = RGBColor(0x11, 0x18, 0x27)
TEXT2 = RGBColor(0x4B, 0x55, 0x63)
LINE = RGBColor(0xE5, 0xE7, 0xEB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TIP_BG = RGBColor(0xEF, 0xF6, 0xFF)

FONT = "Pretendard"
RADIUS = 12  # pt

# ── 좌표 (LOCKED) ──────────────────────────────────────────────────────────
W, H = 960, 540
M = 40  # 좌우 여백
CONTENT_W = W - 2 * M  # 880

DOC_Y, DOC_H = 22, 16  # 상단 라벨 줄
TITLE_Y, TITLE_H = 46, 26  # 화면 제목
ONELINER_Y, ONELINER_H = 74, 16  # 한 줄 설명

MAIN_Y, MAIN_H = 96, 284  # 웹 화면 + 화면 설명
DESC_W = 256
SHOT_W = CONTENT_W - DESC_W - 16  # 608
DESC_X = M + SHOT_W + 16  # 664

BOT_Y, BOT_H = 390, 108  # 주요 기능 / 사용 흐름
BOT_W = (CONTENT_W - 16) // 2  # 432
FLOW_X = M + BOT_W + 16  # 488

TIP_Y, TIP_H = 506, 20

CARD_PAD = 12
SHOT_PAD = 8
SECTION_H = 15  # 섹션 제목 한 줄
DESC_GAP_HEAD = 22  # 섹션 제목 → 첫 항목
DESC_GAP_ITEM = 16  # 항목 → 항목
NUM = 18  # 번호 원
NUM_GAP = 10  # 번호 → 글
ICON = 24


def _ea(run):
    """python-pptx 는 라틴 글꼴만 넣는다. 한글은 동아시아 글꼴 자리를 따로 채워야 한다."""
    rpr = run._r.get_or_add_rPr()
    ea = rpr.find(qn("a:ea"))
    if ea is None:
        ea = rpr.makeelement(qn("a:ea"), {})
        rpr.append(ea)
    ea.set("typeface", FONT)


def textbox(slide, x, y, w, h, *, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(P(x), P(y), P(w), P(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    return tf


def write(tf, text, size, *, bold=False, color=TEXT, line=None, align=None, first=False):
    """첫 문단은 tf.paragraphs[0] 을 쓰고, 이후는 새 문단을 붙인다."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.line_spacing = P(line or size * 1.45)
    if align is not None:
        p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = P(size)
    run.font.bold = bold
    run.font.name = FONT
    run.font.color.rgb = color
    _ea(run)
    return p


def card(slide, x, y, w, h):
    """흰 카드. radius 12pt, 테두리 #E5E7EB 1pt.

    ponytail: 그림자(0 2px 8px rgba(0,0,0,.04))는 생략했다. python-pptx 에 API 가 없고
    눈에 거의 안 띄는 값이다. 필요해지면 spPr 에 a:effectLst 를 직접 넣으면 된다.
    """
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, P(x), P(y), P(w), P(h))
    shape.adjustments[0] = RADIUS / min(w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = WHITE
    shape.line.color.rgb = LINE
    shape.line.width = P(1)
    shape.shadow.inherit = False
    shape.text_frame.text = ""
    return shape


def icon(slide, key, x, y):
    png = HERE / "icons" / f"{key}.png"
    if not png.exists():
        sys.exit(f"아이콘이 없습니다: {key} — `node bake_icons.mjs` 를 먼저 돌리세요.")
    slide.shapes.add_picture(str(png), P(x), P(y), P(ICON), P(ICON))


def shot(slide, path: Path):
    """캡처를 카드 안쪽에 비율 유지로 contain 하고 가운데 정렬. 남는 곳은 흰색."""
    box_w, box_h = SHOT_W - 2 * SHOT_PAD, MAIN_H - 2 * SHOT_PAD
    with Image.open(path) as im:
        ratio = im.width / im.height
    w = min(box_w, box_h * ratio)
    h = w / ratio
    x = M + SHOT_PAD + (box_w - w) / 2
    y = MAIN_Y + SHOT_PAD + (box_h - h) / 2
    slide.shapes.add_picture(str(path), P(x), P(y), P(w), P(h))


def row(slide, items, x0, width, y):
    """주요 기능 / 사용 흐름의 한 줄. 아이콘 위, 기능명·설명 아래."""
    gap = 10
    w = (width - gap * (len(items) - 1)) / len(items)
    for i, it in enumerate(items):
        x = x0 + i * (w + gap)
        icon(slide, it["icon"], x, y)
        tf = textbox(slide, x, y + ICON + 4, w, 28)
        write(tf, it["t"], 9, bold=True, line=13, first=True)
        write(tf, it["d"], 8, color=TEXT2, line=12)


def flow_row(slide, steps, x0, width, y):
    """사용 흐름. 단계 사이에 파란 화살표가 선다."""
    gap, arrow = 8, 12
    w = (width - gap * 2 * (len(steps) - 1) - arrow * (len(steps) - 1)) / len(steps)
    x = x0
    for i, step in enumerate(steps):
        if i:
            tf = textbox(slide, x, y + 2, arrow, ICON, anchor=MSO_ANCHOR.MIDDLE)
            write(tf, "→", 9, bold=True, color=BLUE, align=PP_ALIGN.CENTER, first=True)
            x += arrow + gap
        icon(slide, step["icon"], x, y)
        tf = textbox(slide, x, y + ICON + 4, w, 28)
        write(tf, step["t"], 9, bold=True, line=13, first=True)
        write(tf, step["d"], 8, color=TEXT2, line=12)
        x += w + gap


def build_slide(prs, page):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # 상단 라벨 + 문서 제목
    chip = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, P(M), P(DOC_Y), P(4), P(DOC_H))
    chip.adjustments[0] = 0.5
    chip.fill.solid()
    chip.fill.fore_color.rgb = BLUE
    chip.line.fill.background()
    chip.shadow.inherit = False
    tf = textbox(slide, M + 10, DOC_Y, 400, DOC_H, anchor=MSO_ANCHOR.MIDDLE)
    write(tf, "SalesLuv 서비스 소개서", 11, bold=True, color=NAVY, line=15, first=True)

    # 화면 제목 / 한 줄 설명
    tf = textbox(slide, M, TITLE_Y, CONTENT_W, TITLE_H)
    write(tf, page["title"], 15, bold=True, line=26, first=True)
    tf = textbox(slide, M, ONELINER_Y, CONTENT_W, ONELINER_H)
    write(tf, page["oneLiner"], 9, color=TEXT2, line=16, first=True)

    # 웹 화면
    card(slide, M, MAIN_Y, SHOT_W, MAIN_H)
    png = HERE / "shots" / f"{page['slug']}.png"
    if png.exists():
        shot(slide, png)
    else:
        print(f"  ! 캡처 없음: {png.name}")

    # 화면 설명 — 위에서부터 촘촘히. 마지막 항목 아래는 그대로 비워 둔다.
    card(slide, DESC_X, MAIN_Y, DESC_W, MAIN_H)
    tf = textbox(slide, DESC_X + CARD_PAD, MAIN_Y + CARD_PAD, DESC_W - 2 * CARD_PAD, SECTION_H)
    write(tf, "화면 설명", 11, bold=True, line=SECTION_H, first=True)

    y = MAIN_Y + CARD_PAD + SECTION_H + DESC_GAP_HEAD
    for i, item in enumerate(page["desc"], 1):
        circle = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, P(DESC_X + CARD_PAD), P(y), P(NUM), P(NUM)
        )
        circle.fill.solid()
        circle.fill.fore_color.rgb = BLUE
        circle.line.fill.background()
        circle.shadow.inherit = False
        ctf = circle.text_frame
        ctf.margin_left = ctf.margin_right = ctf.margin_top = ctf.margin_bottom = 0
        ctf.vertical_anchor = MSO_ANCHOR.MIDDLE
        write(ctf, str(i), 8, bold=True, color=WHITE, line=11, align=PP_ALIGN.CENTER, first=True)

        tx = DESC_X + CARD_PAD + NUM + NUM_GAP
        tf = textbox(slide, tx, y - 1, DESC_X + DESC_W - CARD_PAD - tx, 28)
        write(tf, item["t"], 9, bold=True, line=13, first=True)
        write(tf, item["d"], 8, color=TEXT2, line=12)
        y += 28 + DESC_GAP_ITEM

    # 주요 기능 / 사용 흐름 — 두 카드의 Y 와 높이는 모든 장에서 같다.
    for x, title in ((M, "주요 기능"), (FLOW_X, "사용 흐름")):
        card(slide, x, BOT_Y, BOT_W, BOT_H)
        tf = textbox(slide, x + CARD_PAD, BOT_Y + CARD_PAD, BOT_W - 2 * CARD_PAD, SECTION_H)
        write(tf, title, 11, bold=True, line=SECTION_H, first=True)

    items_y = BOT_Y + CARD_PAD + SECTION_H + 8
    row(slide, page["features"], M + CARD_PAD, BOT_W - 2 * CARD_PAD, items_y)
    flow_row(slide, page["flow"], FLOW_X + CARD_PAD, BOT_W - 2 * CARD_PAD, items_y)

    # TIP
    bar = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, P(M), P(TIP_Y), P(CONTENT_W), P(TIP_H)
    )
    bar.adjustments[0] = 6 / TIP_H
    bar.fill.solid()
    bar.fill.fore_color.rgb = TIP_BG
    bar.line.fill.background()
    bar.shadow.inherit = False
    tf = textbox(slide, M + 10, TIP_Y, 40, TIP_H, anchor=MSO_ANCHOR.MIDDLE)
    write(tf, "TIP", 8, bold=True, color=BLUE, line=12, first=True)
    tf = textbox(slide, M + 42, TIP_Y, CONTENT_W - 52, TIP_H, anchor=MSO_ANCHOR.MIDDLE)
    write(tf, page["tip"], 8, color=TEXT2, line=12, first=True)


def main():
    pages = json.loads((HERE / "pages.json").read_text(encoding="utf-8"))

    prs = Presentation()
    prs.slide_width, prs.slide_height = P(W), P(H)
    for page in pages:
        build_slide(prs, page)

    out = HERE / "out"
    out.mkdir(exist_ok=True)
    suffix = "" if SCALE == 1 else f"@{SCALE:g}x"
    dest = out / f"SalesLuv_서비스소개서{suffix}.pptx"
    prs.save(dest)
    print(f"  → {dest.relative_to(HERE)} ({len(pages)}장)")


if __name__ == "__main__":
    main()
