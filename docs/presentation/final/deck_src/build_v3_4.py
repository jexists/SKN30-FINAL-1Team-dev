"""자료요약 에이전트 슬라이드 1장 — v3 덱 '02 설계와 구현' 섹션에 끼워 넣을 낱장.

기존 v3 파일은 건드리지 않고, base_v3 디자인 시스템만 그대로 재사용해 1장짜리 pptx를 만든다.
문구는 docs/document-summary-evaluation.md 와 문서요약 에이전트·RAG 1차 평가 결과보고서
(2026-09-15) 에서 확인되는 내용만 쓴다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches

from base_v3 import (
    BLUE, BLUE_600, BLUE_LIGHT, C, CW, INK, M, MUTED, SUB, T_BODY, T_CARD, T_NOTE, TINT,
    TINT2, WHITE, arrow, card, flat, ghost, keyline, label, new_deck, para, pill, slide,
    write,
)

OUT = ("/Volumes/Jexists/skn30/SKN30-FINAL-1Team-dev/docs/presentation/final/"
       "SalesLuv_최종발표_260918_v3_4.pptx")

PAGE = 25
CH2 = "02 설계와 구현"

# ---------- 흐름 기하 (좌우 끝이 M .. M+CW 에 정확히 맞도록) ----------
GAP = 0.40
BAND_Y, BAND_H = 2.56, 2.72          # 일반 단계 카드
AG_Y, AG_H = 2.40, 3.04              # Agent 카드만 위아래로 0.16 크게
W1 = W2 = 2.56
W3 = 3.10
X1 = M                               # 0.620
X2 = X1 + W1 + GAP                   # 3.580
X3 = X2 + W2 + GAP                   # 6.540
X4 = X3 + W3 + GAP                   # 10.040
W4 = M + CW - X4                     # 2.673
MID = BAND_Y + BAND_H / 2            # 3.92 — 수평 화살표 높이


def step(sl, x, y, w, h, num, title, *, fill=TINT, accent=None, num_color=BLUE_LIGHT):
    """37번 슬라이드와 같은 관용구: ghost 번호 + 단계명. 본문 시작 y 를 돌려준다."""
    flat(sl, x, y, w, h, fill=fill, accent=accent)
    px = x + (0.38 if accent else 0.30)
    ghost(sl, px, y + 0.22, w - 0.6, num, size=26, color=num_color)
    write(sl, px, y + 0.74, w - (px - x) - 0.30, 0.36,
          [(title, dict(size=19, weight=700, color=INK, line=1.25))])
    return px, y + 1.18


def build():
    prs = new_deck()
    sl, top = slide(
        prs, PAGE, chapter=CH2, headline="자료요약 에이전트",
        source="출처: docs/document-summary-evaluation.md · "
               "문서요약 에이전트·RAG 1차 평가 결과보고서(2026-09-15)")

    label(sl, M, top, "문서 한 건이 처리되는 흐름")

    # ---------- 01 입력 자료 ----------
    px, by = step(sl, X1, BAND_Y, W1, BAND_H, "01", "입력 자료")
    write(sl, px, by, W1 - 0.60, 1.0,
          [("견적서 · 계약서", dict(size=16, weight=400, color=SUB, line=1.4)),
           ("발주서 · 상품설명서", dict(size=16, weight=400, color=SUB, line=1.4,
                                 spacing_before=2))])
    write(sl, px, by + 0.94, W1 - 0.60, 0.3,
          [("PDF 문서", dict(size=T_NOTE, weight=400, color=MUTED, line=1.3))])

    # ---------- 02 텍스트 추출 (OCR 은 보조 배지로만) ----------
    px, by = step(sl, X2, BAND_Y, W2, BAND_H, "02", "텍스트 추출")
    write(sl, px, by, W2 - 0.56, 0.4,
          [("PDF 본문을 읽는다", dict(size=16, weight=400, color=SUB, line=1.4))])
    pill(sl, px, by + 0.41, 1.75, 0.32, "OCR fallback",
         fill=WHITE, color=BLUE_600, size=T_NOTE)
    write(sl, px, by + 0.83, W2 - 0.56, 0.6,
          [("추출 실패 시", dict(size=T_NOTE, weight=400, color=MUTED, line=1.35)),
           ("OCR로 다시 읽는다", dict(size=T_NOTE, weight=400, color=MUTED, line=1.35))])

    # ---------- 03 자료요약 Agent (강조) ----------
    px, by = step(sl, X3, AG_Y, W3, AG_H, "03", "자료요약 Agent",
                  fill=TINT2, accent=BLUE, num_color=BLUE)
    for i, kw in enumerate(["문서 요약 생성", "핵심 필드 보존", "검색 문맥 기반 응답"]):
        ch = card(sl, px, by + 0.06 + i * 0.60, W3 - (px - X3) - 0.38, 0.50,
                  fill=WHITE, shadow=False, radius=0.09)
        tf = ch.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.16)
        tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para(tf, kw, size=17, weight=600, color=INK, line=1.25, first=True)

    # ---------- 04 결과 (요약 · RAG 두 갈래) ----------
    flat(sl, X4, BAND_Y, W4, BAND_H, fill=TINT)
    ghost(sl, X4 + 0.30, BAND_Y + 0.22, W4 - 0.6, "04", size=26, color=BLUE_LIGHT)
    write(sl, X4 + 0.30, BAND_Y + 0.74, W4 - 0.60, 0.36,
          [("결과", dict(size=19, weight=700, color=INK, line=1.25))])
    outs = [("문서 요약", "문서별 핵심 필드 정리"),
            ("RAG 질의응답", "검색 문맥 기반 답변")]
    for i, (t, d) in enumerate(outs):
        oy = BAND_Y + 1.20 + i * 0.76
        card(sl, X4 + 0.24, oy, W4 - 0.48, 0.66, fill=WHITE, shadow=False, radius=0.09)
        write(sl, X4 + 0.44, oy + 0.09, W4 - 0.88, 0.28,
              [(t, dict(size=T_NOTE + 2, weight=700, color=INK, line=1.2))])
        write(sl, X4 + 0.44, oy + 0.36, W4 - 0.88, 0.26,
              [(d, dict(size=T_NOTE, weight=400, color=MUTED, line=1.2))])

    # ---------- 화살표: 수평 직선 3개만 ----------
    for xa, xb in [(X1 + W1, X2), (X2 + W2, X3), (X3 + W3, X4)]:
        arrow(sl, xa + 0.05, MID, xb - 0.05, MID, color=BLUE_LIGHT, width=2)

    keyline(sl, 5.70,
            "요약과 검색 답변은 LLM-as-a-Judge 자동 평가와 사람검수 화면으로 원문과 대조한다")

    prs.save(OUT)
    print("saved", OUT, len(prs.slides._sldIdLst), "slides")


if __name__ == "__main__":
    build()
