"""OCR 고도화 3장 — v3 덱 뒤에 붙일 별도 덱.

v3 pptx 는 열지 않는다. new_deck() 으로 새로 시작하므로 원본을 건드릴 수 없다.
디자인은 base_v3 프레임과 v3 40p(KPI 띠) · 41p(3단계 흐름) 의 관용구를 그대로 쓴다.
내용과 수치는 docs/presentation/eval/OCR 고도화 평가 최종보고서.pdf 에서만 가져온다
(check_ocr3.py 가 PDF 본문과 대조한다).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches

from base_v3 import (
    BLUE, BLUE_LIGHT, CW, INK, M, MUTED, SUB, TINT, TINT2, T_BODY, T_CARD, T_KPI, T_NOTE,
    WHITE,
    R, arrow, card, flat, grid, keyline, kpi, label, new_deck, para, slide, write,
)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "SalesLuv_OCR_고도화_3장.pptx")
CH3 = "03 검증과 확장"
AT = 59                            # v3(56p) + Deep Agents 3장(57–59) 뒤 — 60 · 61 · 62
SRC_FULL = "출처: OCR 고도화 전후 최종 결과보고서 (2026-09-17 RunPod 재시험)"


def kpi_row(sl, y, items, *, featured=None, h=1.78):
    """v3 40p 의 KPI 띠 — flat 틴트 칸 + kpi 타이포. build_v3 와 같은 관용구."""
    w, xs = grid(len(items), 0.3)
    for i, (val, lab, sub) in enumerate(items):
        hot = featured == i
        flat(sl, xs[i], y, w, h, fill=(TINT2 if hot else TINT), accent=(BLUE if hot else None))
        kpi(sl, xs[i] + 0.34, y + 0.26, w - 0.68, val, lab, sub, color=(BLUE if hot else INK))
    return w, xs


# ================================================================= 60p 문제
PROB_Y, PROB_H = 4.02, 1.66


def slide_problem(prs):
    sl, top = slide(prs, AT + 1, chapter=CH3,
                    headline="원본 PDF OCR만으로는 핵심 필드가 누락됐다",
                    source=SRC_FULL)
    kpi_row(sl, top,
            [("65.4%", "핵심 구조화 문서", "1차 테스트 · 752 / 1,150"),
             ("25.0%", "계약서", "1차 테스트 · 50 / 200"),
             ("66.9%", "발주서", "1차 테스트 · 502 / 750"),
             ("84.0%", "상품설명서", "1차 테스트 · 42 / 50")],
            featured=0)

    w3, xs3 = grid(3, 0.36)
    probs = [("한글 필수값 누락", ["상호 · 대표이사 · 상대 상호가", "PDF 경로에서 누락됐다"]),
             ("표 영역 손실", ["공급자 · 지급조건 · 표 영역이", "PDF 경로에서 손실됐다"]),
             ("PDF 작업 실패", ["상품설명서 일부는 PDF OCR", "작업 자체가 실패했다"])]
    for i, (t, lines) in enumerate(probs):
        flat(sl, xs3[i], PROB_Y, w3, PROB_H, fill=TINT)
        write(sl, xs3[i] + 0.34, PROB_Y + 0.30, w3 - 0.66, 0.36,
              [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        write(sl, xs3[i] + 0.34, PROB_Y + 0.82, w3 - 0.66, 0.68,
              [(s, dict(size=16, weight=400, color=SUB, line=1.45,
                        spacing_before=(0 if j == 0 else 1))) for j, s in enumerate(lines)])

    keyline(sl, 5.84, "스캔 PDF의 텍스트 · 표 영역을 복구할 경로가 필요했다")
    return sl


# ================================================================= 61p 개선
FLOW_Y, FLOW_H = 2.46, 2.56        # 본문(2.04–6.62)의 약 60%
WAY_LBL_Y = 5.14
WAY_Y, WAY_H = 5.40, 1.08


def slide_approach(prs):
    sl, top = slide(prs, AT + 2, chapter=CH3,
                    headline="누락된 문서만 PNG로 다시 읽고, 취약 필드는 남겼다",
                    source="출처: OCR 고도화 전후 최종 결과보고서 (2026-09-17) · "
                           "재시도 시 모든 페이지를 최대 긴 변 2,200px으로 렌더링")
    label(sl, M, top, "고도화 흐름")

    w3, xs3 = grid(3, 0.36)
    steps = [("1차", ["원본 PDF를 RunPod", "PDF OCR로 처리한다"],
              "기준 성능과 누락 필드 확인"),
             ("조건부 재시도", ["한글 필수값 누락 또는 PDF OCR", "작업 실패일 때만 모든 페이지를",
                          "PNG로 변환해 다시 읽는다"],
              "스캔 PDF의 텍스트 · 표 영역 복구"),
             ("결과 선택", ["발주서 공급자 주소는 PDF 결과,", "나머지 선정 필드는",
                        "PNG 결과를 쓴다"],
              "PNG 경로의 주소 하락 방지")]
    for i, (t, lines, aim) in enumerate(steps):
        act = i == 1
        flat(sl, xs3[i], FLOW_Y, w3, FLOW_H,
             fill=(TINT2 if act else TINT), accent=(BLUE if act else None))
        px = xs3[i] + (0.42 if act else 0.34)
        iw = w3 - (px - xs3[i]) - 0.34
        write(sl, px, FLOW_Y + 0.28, iw, 0.36,
              [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        write(sl, px, FLOW_Y + 0.80, iw, 1.02,
              [(s, dict(size=16, weight=400, color=SUB, line=1.45,
                        spacing_before=(0 if j == 0 else 1))) for j, s in enumerate(lines)])
        ch = card(sl, px, FLOW_Y + 1.90, iw, 0.54, fill=WHITE, shadow=False, radius=0.09)
        tf = ch.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.14)
        tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para(tf, aim, size=T_NOTE, weight=600, color=MUTED, line=1.25, first=True)
        if i < 2:
            arrow(sl, xs3[i] + w3 + 0.05, FLOW_Y + FLOW_H / 2,
                  xs3[i] + w3 + 0.31, FLOW_Y + FLOW_H / 2, color=BLUE_LIGHT, width=2)

    label(sl, M, WAY_LBL_Y, "문서별 최종 경로")
    w4, xs4 = grid(4, 0.3)
    ways = [("견적서", ["원본 PDF OCR 유지"]),
            ("계약서", ["한글 누락 시", "모든 페이지 PNG OCR"]),
            ("발주서", ["PNG OCR + 공급자", "주소만 PDF 결과 보존"]),
            ("상품설명서", ["PDF 작업 실패 문서만", "PNG OCR 재시도"])]
    for i, (t, lines) in enumerate(ways):
        flat(sl, xs4[i], WAY_Y, w4, WAY_H, fill=TINT)
        write(sl, xs4[i] + 0.28, WAY_Y + 0.14, w4 - 0.56, 0.30,
              [(t, dict(size=17, weight=700, color=INK, line=1.25))])
        write(sl, xs4[i] + 0.28, WAY_Y + 0.46, w4 - 0.56, 0.56,
              [(s, dict(size=T_NOTE, weight=400, color=MUTED, line=1.3,
                        spacing_before=(0 if j == 0 else 1))) for j, s in enumerate(lines)])
    return sl


# ================================================================= 62p 결과
HERO_Y, HERO_H = 2.04, 1.82
DOC_Y, DOC_H = 4.02, 1.12
KEY_Y = 5.30
NOTE_Y = 6.08


def slide_results(prs):
    sl, top = slide(prs, AT + 3, chapter=CH3,
                    headline="핵심 구조화 문서 일치율 65.4% → 98.8%",
                    source=SRC_FULL)

    flat(sl, M, HERO_Y, CW, HERO_H, fill=TINT2, accent=BLUE)
    kpi(sl, M + 0.42, HERO_Y + 0.26, 5.60, "65.4% → 98.8%",
        "핵심 구조화 문서 선정 필드 일치율",
        "1,136 / 1,150 · 견적서 · 계약서 · 발주서 150건", color=BLUE)
    rx = M + CW - 0.42 - 3.20
    write(sl, rx, HERO_Y + 0.26, 3.20, 0.80,
          [("+33.4%p", dict(size=T_KPI, weight=700, color=BLUE, line=1.1))], align=R)
    write(sl, rx, HERO_Y + 1.10, 3.20, 0.32,
          [("1차 대비 개선 폭", dict(size=17, weight=600, color=INK, line=1.3))], align=R)

    w4, xs4 = grid(4, 0.3)
    docs = [("견적서", "100.0% → 100.0%", "0.0%p · 200 / 200", False),
            ("계약서", "25.0% → 98.5%", "+73.5%p · 197 / 200", True),
            ("발주서", "66.9% → 98.5%", "+31.6%p · 739 / 750", True),
            ("상품설명서", "84.0% → 86.0%", "+2.0%p · 43 / 50", False)]
    for i, (t, ba, gain, hot) in enumerate(docs):
        flat(sl, xs4[i], DOC_Y, w4, DOC_H,
             fill=(TINT2 if hot else TINT), accent=(BLUE if hot else None))
        px = xs4[i] + (0.36 if hot else 0.28)
        iw = w4 - (px - xs4[i]) - 0.28
        write(sl, px, DOC_Y + 0.14, iw, 0.30,
              [(t, dict(size=17, weight=700, color=INK, line=1.25))])
        write(sl, px, DOC_Y + 0.46, iw, 0.36,
              [(ba, dict(size=T_BODY, weight=700, color=(BLUE if hot else INK), line=1.25))])
        write(sl, px, DOC_Y + 0.84, iw, 0.26,
              [(gain, dict(size=T_NOTE, weight=400, color=MUTED, line=1.25))])

    keyline(sl, KEY_Y, "스캔 · 한글 누락 PDF만 PNG로 다시 읽고, 취약 필드는 PDF 결과를 보존했다")

    write(sl, M, NOTE_Y, CW, 0.54,
          [("평가 범위    선정 필드 일치율 기준 · 문자 단위 전사 정확도 · CER / WER 미포함",
            dict(size=T_NOTE, weight=400, color=MUTED, line=1.35)),
           ("남은 과제    상품설명서는 +2.0%p · 사양 값 자동 등록 정확도는 사람 검수 필요",
            dict(size=T_NOTE, weight=400, color=MUTED, line=1.35, spacing_before=2))])
    return sl


def build():
    prs = new_deck()
    slide_problem(prs)
    slide_approach(prs)
    slide_results(prs)
    prs.save(OUT)
    print("saved", os.path.normpath(OUT), len(prs.slides._sldIdLst), "slides")


if __name__ == "__main__":
    build()
