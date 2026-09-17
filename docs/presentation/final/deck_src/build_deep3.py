"""보고서 에이전트 Deep Agents 개선 3장 — v3 덱 뒤에 붙일 별도 덱.

v3 pptx 는 열지 않는다. new_deck() 으로 새로 시작하므로 원본을 건드릴 수 없다.
디자인은 base_v3 프레임과 v3 33p(KPI 띠) · 37p(4단계 가로 흐름) 의 관용구를 그대로 쓴다.
내용과 수치는 docs/presentation/eval/SalesLUV_보고서에이전트_Deep_Agents_개선_최종본.pptx
에서 확인되는 것만 쓴다 (check_deep3.py 가 대조).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches

from base_v3 import (
    BLUE, BLUE_LIGHT, BLUE_PALE, CW, GRAY, INK, M, MUTED, SUB, T_NOTE, TINT, TINT2, WHITE,
    _bar, arrow, card, flat, ghost, grid, kpi, keyline, new_deck, para, slide, write,
)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "SalesLuv_보고서에이전트_Deep_Agents_개선_3장.pptx")
CH3 = "03 검증과 확장"
AT = 56                            # v3 마지막 장(56p) 뒤 — 삽입 위치 기준 번호

# ---------- 공통 기하 (본문 2.04 ~ 6.62) ----------
LEAD_Y = 2.04                      # 결론 한 줄
KPI_Y, KPI_H = 2.50, 1.78          # v3 33p 와 같은 KPI 띠 높이


def lead(sl, text):
    """결론 한 줄. v3 33p 와 달리 제목이 결론을 반쯤 맡으므로 여기선 보강 문장."""
    write(sl, M, LEAD_Y, CW, 0.34, [(text, dict(size=20, weight=600, color=INK, line=1.25))])


def kpi_row(sl, y, items, featured, *, h=KPI_H):
    """v3 33p 의 KPI 띠 — flat 틴트 칸 + kpi 타이포."""
    w, xs = grid(len(items), 0.3)
    for i, (val, lab, sub) in enumerate(items):
        hot = i == featured
        flat(sl, xs[i], y, w, h, fill=(TINT2 if hot else TINT), accent=(BLUE if hot else None))
        kpi(sl, xs[i] + 0.34, y + 0.26, w - 0.68, val, lab, sub, color=(BLUE if hot else INK))
    return w, xs


def note_block(sl, x, y, w, h, title, main, sub):
    """GRAY 보조 블록 — 제목 · 본문 한 줄 · 부연 한 줄. 모두 한 줄로 끝난다."""
    flat(sl, x, y, w, h, fill=GRAY)
    write(sl, x + 0.34, y + 0.22, w - 0.66, 0.34,
          [(title, dict(size=19, weight=700, color=INK, line=1.25))])
    write(sl, x + 0.34, y + 0.62, w - 0.66, 0.30,
          [(main, dict(size=16, weight=400, color=SUB, line=1.4))])
    write(sl, x + 0.34, y + 0.94, w - 0.66, 0.28,
          [(sub, dict(size=T_NOTE, weight=400, color=MUTED, line=1.35))])


# ================================================================= 57p
def slide_problem(prs):
    sl, _ = slide(
        prs, AT + 1, chapter=CH3,
        headline="토큰 부담과 기간 보고서 완성도가 문제였다",
        source="출처: 보고서 A/B 평가결과  |  품질: LLM Judge · 100점 만점 · 주간 3건 / 월간 1건")
    lead(sl, "토큰 소모는 줄이고, 보고서 완성도는 높여야 했다")
    kpi_row(sl, KPI_Y,
            [("10,010,770", "기존 A 생성 토큰 합계", "전체 53건 실행"),
             ("72.50", "기존 A 주간 보고서 품질", "100점 만점"),
             ("66.25", "기존 A 월간 보고서 품질", "100점 만점")],
            featured=0)

    ny, nh = 4.40, 1.28                            # 4.40 ~ 5.68
    w2, xs2 = grid(2, 0.4)
    note_block(sl, xs2[0], ny, w2, nh, "토큰 소모량",
               "생성 · 재시도 과정의 토큰 부담", "입력 범위와 반복 호출의 효율화 필요")
    note_block(sl, xs2[1], ny, w2, nh, "보고서 품질",
               "기간보고서의 완성도 보완", "필수 정보 · 보고 목적 · 후속업무 정리 보완")

    # 결론 띠는 5.84 가 한계 — 글상자가 BOT(6.62) 아래로 새지 않는 마지막 y
    keyline(sl, 5.84, "개선 목표는 토큰 효율과 보고서 품질을 함께 올리는 것이었다")
    return sl


# ================================================================= 58p
FLOW_Y, FLOW_H = 2.50, 2.50        # 흐름 도식 — 본문의 약 65%
AG_Y, AG_H = 2.34, 2.82            # 03 칸만 위아래로 0.16 크게 (v3_4 관용구)
GAP = 0.40
W1, W2 = 2.46, 2.24               # 실측 글자 폭에 맞춘 칸 (textwidth.py)
W3 = 3.56
X1 = M
X2 = X1 + W1 + GAP
X3 = X2 + W2 + GAP
X4 = X3 + W3 + GAP
W4 = M + CW - X4
MID = FLOW_Y + FLOW_H / 2


def step(sl, x, y, w, h, num, title, *, fill=TINT, accent=None, num_color=BLUE_LIGHT):
    """v3 37p·v3_4 와 같은 관용구: ghost 번호 + 단계명. (본문 x, 본문 시작 y) 반환."""
    flat(sl, x, y, w, h, fill=fill, accent=accent)
    px = x + (0.38 if accent else 0.30)
    ghost(sl, px, y + 0.20, w - 0.6, num, size=26, color=num_color)
    write(sl, px, y + 0.72, w - (px - x) - 0.30, 0.34,
          [(title, dict(size=19, weight=700, color=INK, line=1.25))])
    return px, y + 1.14


def slide_approach(prs):
    sl, _ = slide(
        prs, AT + 2, chapter=CH3,
        headline="감독 · 작성 · 검토로 역할을 나눴다",
        source="출처: 미팅 · 보고서 에이전트 구조 문서  |  최종 검토 · 확정은 사용자")
    lead(sl, "보고서 에이전트를 Deep Agents 기반으로 개량했다")

    # ---------- 01 입력 확정 ----------
    px, by = step(sl, X1, FLOW_Y, W1, FLOW_H, "01", "입력 확정")
    write(sl, px, by, W1 - 0.60, 0.9,
          [("보고서 종류와", dict(size=16, weight=400, color=SUB, line=1.4)),
           ("입력은 서버가 확정", dict(size=16, weight=400, color=SUB, line=1.4, spacing_before=2))])

    # ---------- 02 Supervisor (강조) ----------
    px, by = step(sl, X2, FLOW_Y, W2, FLOW_H, "02", "Supervisor",
                  fill=TINT2, accent=BLUE, num_color=BLUE)
    write(sl, px, by, W2 - 0.68, 1.2,
          [("작업 위임", dict(size=16, weight=400, color=SUB, line=1.4)),
           ("검토 관리", dict(size=16, weight=400, color=SUB, line=1.4, spacing_before=2)),
           ("결과 선택", dict(size=16, weight=400, color=SUB, line=1.4, spacing_before=2))])

    # ---------- 03 Writer / Reviewer ----------
    px, by = step(sl, X3, AG_Y, W3, AG_H, "03", "Writer · Reviewer", fill=TINT2)
    subs = [("유형별 Writer", "작성 지침과 배정된 근거로 작성"),
            ("공통 Reviewer", "원자료와 초안 대조 · 수정 지적")]
    for i, (t, d) in enumerate(subs):
        cy = by + 0.04 + i * 0.78
        card(sl, px, cy, W3 - (px - X3) - 0.38, 0.68, fill=WHITE, shadow=False, radius=0.09)
        write(sl, px + 0.22, cy + 0.08, W3 - (px - X3) - 0.82, 0.30,
              [(t, dict(size=17, weight=700, color=INK, line=1.2))])
        write(sl, px + 0.22, cy + 0.38, W3 - (px - X3) - 0.82, 0.28,
              [(d, dict(size=T_NOTE, weight=400, color=MUTED, line=1.25))])

    # ---------- 04 결과 ----------
    px, by = step(sl, X4, FLOW_Y, W4, FLOW_H, "04", "결과")
    ch = card(sl, px, by, W4 - (px - X4) - 0.30, 0.56, fill=WHITE, shadow=False, radius=0.09)
    tf = ch.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.16)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, "최대 1회 부분 수정", size=16, weight=600, color=INK, line=1.25, first=True)
    write(sl, px, by + 0.68, W4 - (px - X4) - 0.30, 0.34,
          [("지적된 부분만 고친 초안", dict(size=T_NOTE, weight=400, color=MUTED, line=1.3))])

    # ---------- 화살표 ----------
    for xa, xb in [(X1 + W1, X2), (X2 + W2, X3), (X3 + W3, X4)]:
        arrow(sl, xa + 0.05, MID, xb - 0.05, MID, color=BLUE_LIGHT, width=2)

    # ---------- 바뀐 점 3가지 ----------
    py = 5.44
    w3_, xs3 = grid(3, 0.36)
    pts = [("01", "역할 분리", "감독 · 작성 · 검토"),
           ("02", "지침 · 근거 분리", "유형별 SKILL.md + 배정 근거"),
           ("03", "반복 수정 제한", "검토 후 부분 수정 최대 1회")]
    for i, (n, t, d) in enumerate(pts):
        flat(sl, xs3[i], py, w3_, 1.18, fill=TINT)
        write(sl, xs3[i] + 0.30, py + 0.16, 0.7, 0.3,
              [(n, dict(size=16, weight=700, color=BLUE_LIGHT, line=1.25))])
        write(sl, xs3[i] + 0.94, py + 0.14, w3_ - 1.24, 0.32,
              [(t, dict(size=18, weight=700, color=INK, line=1.25))])
        write(sl, xs3[i] + 0.30, py + 0.62, w3_ - 0.6, 0.34,
              [(d, dict(size=16, weight=400, color=SUB, line=1.3))])
    return sl


# ================================================================= 59p
CARD_Y, CARD_H = 2.50, 2.70        # 2.50 ~ 5.20
KEY_Y = 5.36                       # 결론 띠
NOTE_Y = 6.08                      # 한계 · 범위 주석 (6.62 = BOT 에 맞춘다)
BAR_Y, BAR_PITCH = 4.32, 0.46


def bar_pair(sl, x, y, w, rows):
    """기존 A / 개선 B 가로 막대 두 줄. rows: [(라벨, 값문자열, 비율, 색)]"""
    lab_w, val_w = 0.92, 1.58
    bx = x + lab_w + val_w
    bw = w - lab_w - val_w
    for i, (nm, val, ratio, color) in enumerate(rows):
        yy = y + i * BAR_PITCH
        write(sl, x, yy + 0.02, lab_w, 0.28,
              [(nm, dict(size=T_NOTE, weight=600, color=MUTED, line=1.25))])
        write(sl, x + lab_w, yy, val_w, 0.30,
              [(val, dict(size=17, weight=700, color=INK, line=1.25))])
        _bar(sl, bx, yy + 0.07, max(bw * ratio, 0.05), 0.16, color)


def slide_results(prs):
    sl, _ = slide(
        prs, AT + 3, chapter=CH3,
        headline="토큰은 절반 이하로, 종합 품질은 +1.94점",
        source="출처: 보고서 A/B 평가결과  |  기존 A / 개선 B  |  2026.09.07–09.08")
    lead(sl, "더 적은 토큰으로, 더 높은 종합 품질")

    w2, xs2 = grid(2, 0.4)
    blocks = [("토큰 소모량", "−54.36%", "전체 53건 실행 · 반환된 생성 토큰 합계",
               [("기존 A", "10,010,770", 1.0, BLUE_PALE),
                ("개선 B", "4,568,617", 0.4563, BLUE)]),
              ("보고서 종합 품질", "+1.94점", "동일 43건 · LLM Judge 종합점수 / 100점",
               # 막대는 60~100 구간 길이다. 값 자체의 길이가 아니다.
               [("기존 A", "93.23", (93.23 - 60) / 40, BLUE_PALE),
                ("개선 B", "95.17", (95.17 - 60) / 40, BLUE)])]
    for i, (title, big, cap, rows) in enumerate(blocks):
        hot = i == 1
        flat(sl, xs2[i], CARD_Y, w2, CARD_H,
             fill=(TINT2 if hot else TINT), accent=(BLUE if hot else None))
        write(sl, xs2[i] + 0.40, CARD_Y + 0.24, w2 - 0.8, 0.30,
              [(title, dict(size=17, weight=600, color=MUTED, line=1.25))])
        write(sl, xs2[i] + 0.40, CARD_Y + 0.54, w2 - 0.8, 0.84,
              [(big, dict(size=48, weight=700, color=BLUE, line=1.1))])
        write(sl, xs2[i] + 0.40, CARD_Y + 1.42, w2 - 0.8, 0.28,
              [(cap, dict(size=T_NOTE, weight=400, color=MUTED, line=1.25))])
        bar_pair(sl, xs2[i] + 0.40, BAR_Y, w2 - 0.8, rows)

    keyline(sl, KEY_Y, "필수 내용 · 구성 · 후속업무 점수가 올랐다")

    write(sl, M, NOTE_Y, CW, 0.54,
          [("평가 범위    작성 지침 · 실행 구조를 함께 개선한 A/B 비교 · "
            "프레임워크 교체만의 효과는 아니다",
            dict(size=T_NOTE, weight=400, color=MUTED, line=1.35)),
           ("보완 과제    종합점수는 올랐으나 미팅 평균 · 사실 정확성 항목은 하락했다",
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
