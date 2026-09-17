"""SalesLuv 최종 발표 v4 = v3 그대로 + 평가 슬라이드 3장.

v3 pptx 를 열어 29p(평가 개요) 뒤에 세 장을 끼우고 v4 로 따로 저장한다.
기존 슬라이드는 페이지 번호 텍스트 외에는 건드리지 않는다.
  30p 미팅 브리핑 에이전트  ← SalesLuv_미팅브리핑_평가.pptx
  31p 보고서 작성 에이전트  ← SalesLuv_보고서작성에이전트_평가_4p.pptx
  32p 딜 승산 예측 모델     ← SalesLuv_딜승산예측모델_평가.pptx

세 장 모두 같은 골격이다.
  상단  핵심 수치 KPI 3개 (30p·33p 의 kpi_row 관용구)
  하단  좌 = 평가 방법 4단계 세로 흐름 / 우 = 평가 데이터 (39p 의 2단 관용구)
결론 한 줄은 헤드라인이 맡는다 — 31p·34p·39p·43p 와 같이 keyline 을 쓰지 않는다.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx import Presentation
from pptx.util import Inches

from textwidth import width

from base_v3 import (
    BLUE, BLUE_600, BLUE_LIGHT, CW, FOOT_Y, GRAY, INK, M, MUTED, SUB, SW, T_NOTE, TINT,
    TINT2, flat, grid, kpi, label, slide, write,
)

FINAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(FINAL, "SalesLuv_최종발표_260918_v3.pptx")
OUT = os.path.join(FINAL, "SalesLuv_최종발표_260918_v4.pptx")

CH3 = "03 검증과 확장"
AT = 29                            # 0-based — 29p(평가 개요) 바로 뒤

# ---------- 공통 기하 (본문 2.04 ~ 6.62) ----------
KPI_Y, KPI_H = 2.04, 1.78          # 30p·33p 와 같은 높이
LAB_Y = 4.02
ROW_Y, ROW_H = 4.42, 2.20          # 4.42 + 2.20 = 6.62 (BOT)
FLOW_W = 7.20                      # 좌: 평가 방법
DATA_X = M + FLOW_W + 0.55         # 우: 평가 데이터
DATA_W = CW - FLOW_W - 0.55
STEP_H, STEP_GAP = 0.49, 0.08      # 4 × 0.49 + 3 × 0.08 = 2.20
DATA_Y0, DATA_PITCH = 0.28, 0.42   # 4행 + 한계 한 줄이 6.62 안에 들어가는 간격
DESC_X, DESC_W = 3.45, FLOW_W - 3.75   # 단계 설명 칸 — 한 줄로 끝나야 한다


def kpi_row(sl, items, featured):
    """30p·33p 와 같은 KPI 띠. 본문 폭 전체를 세 장이 나눠 쓴다."""
    w, xs = grid(len(items), 0.3)
    for i, (val, lab, sub) in enumerate(items):
        hot = i == featured
        flat(sl, xs[i], KPI_Y, w, KPI_H, fill=(TINT2 if hot else TINT),
             accent=(BLUE if hot else None))
        kpi(sl, xs[i] + 0.34, KPI_Y + 0.26, w - 0.68, val, lab, sub,
            color=(BLUE if hot else INK))


def method_flow(sl, steps):
    """39p 와 같은 세로 흐름. 번호 · 단계명 · 설명을 한 줄에 둔다."""
    label(sl, M, LAB_Y, "평가 방법", w=FLOW_W)
    for i, (title, desc) in enumerate(steps):
        y = ROW_Y + i * (STEP_H + STEP_GAP)
        last = i == len(steps) - 1
        flat(sl, M, y, FLOW_W, STEP_H, fill=(TINT2 if last else TINT),
             accent=(BLUE if last else None), radius=0.09)
        write(sl, M + 0.32, y + 0.10, 0.6, 0.30,
              [("%02d" % (i + 1), dict(size=17, weight=700,
                                       color=(BLUE if last else BLUE_LIGHT), line=1.25))])
        write(sl, M + 0.92, y + 0.10, 2.45, 0.30,
              [(title, dict(size=17, weight=700, color=INK, line=1.25))])
        write(sl, M + DESC_X, y + 0.125, DESC_W, 0.28,
              [(desc, dict(size=15, weight=400, color=SUB, line=1.25))])


def data_block(sl, rows):
    """39p 우측 GRAY 블록과 같은 자리. 건수는 값 + 라벨 한 줄로만 보인다."""
    label(sl, DATA_X, LAB_Y, "평가 데이터", w=DATA_W - 0.2, color=MUTED)
    flat(sl, DATA_X, ROW_Y, DATA_W, ROW_H, fill=GRAY)
    vw = max(width(v, 20, 700) for v, _ in rows) + 0.16      # 값 칸은 가장 긴 값에 맞춘다
    for i, (val, lab) in enumerate(rows):
        y = ROW_Y + DATA_Y0 + i * DATA_PITCH
        write(sl, DATA_X + 0.32, y, vw, 0.34,
              [(val, dict(size=20, weight=700, color=BLUE_600, line=1.25))])
        write(sl, DATA_X + 0.32 + vw, y + 0.055, DATA_W - 0.64 - vw, 0.28,
              [(lab, dict(size=15, weight=400, color=SUB, line=1.25))])


def eval_slide(prs, page, *, headline, source, kpis, featured, steps, data, caveat=None):
    sl, _ = slide(prs, page, chapter=CH3, headline=headline, source=source)
    kpi_row(sl, kpis, featured)
    method_flow(sl, steps)
    data_block(sl, data)
    if caveat:                     # 한계 한 줄 — 데이터 마지막 행 아래, BOT 안쪽
        y = ROW_Y + DATA_Y0 + len(data) * DATA_PITCH - 0.06
        write(sl, DATA_X + 0.32, y, DATA_W - 0.64, 0.28,
              [(caveat, dict(size=T_NOTE, weight=400, color=MUTED, line=1.35))])
    return sl


# ---------- 페이지 번호 ----------
NUM_X, NUM_Y = SW - M - 1.0, FOOT_Y - 0.03


def _page_box(sl):
    """base_v3.slide() 가 찍는 우하단 페이지 번호 텍스트박스."""
    for sh in sl.shapes:
        if not sh.has_text_frame or sh.top is None:
            continue
        if not re.fullmatch(r"\d{2}", sh.text_frame.text.strip()):
            continue
        if abs(sh.left - Inches(NUM_X)) < Inches(0.05) and \
           abs(sh.top - Inches(NUM_Y)) < Inches(0.05):
            return sh
    return None


def renumber(prs):
    """삽입으로 밀린 슬라이드의 번호 텍스트만 다시 쓴다. 서식은 런에 남는다."""
    fixed = 0
    for i, sl in enumerate(prs.slides, 1):
        sh = _page_box(sl)
        if sh is None:             # 표지는 번호가 없다
            continue
        want = "%02d" % i
        runs = sh.text_frame.paragraphs[0].runs
        if runs[0].text != want:
            runs[0].text = want
            fixed += 1
    return fixed


def build():
    prs = Presentation(SRC)
    base = len(prs.slides._sldIdLst)

    # ========================= 30 미팅 브리핑 에이전트 =========================
    eval_slide(
        prs, AT + 1,
        headline="30건 평균 89.8%, 근거 오류는 0건이었다",
        source="출처: SalesLuv 미팅 브리핑 평가 "
               "(salesluv-briefing-eval-v1 · 합성 이력 · 실제 고객 데이터 미사용)",
        kpis=[("89.8%", "전체 30건 평균", "미팅 누적 깊이별 5개 시점"),
              ("96.3%", "미팅 1~5회 시점 평균", "쌓일수록 점수는 내려간다"),
              ("0건", "없는 근거 인용 · 발언 왜곡", "근거 없어 버려진 하이라이트도 0건")],
        featured=0,
        steps=[("합성 이력 구축", "고객사 6곳 · 1~30회 5개 시점"),
               ("시점별 정답 계산", "주제 타임라인에서 그 시점의 정답만"),
               ("도구 실제 실행", "DB 없이 실행 · RAG 호출까지 측정"),
               ("LLM 판정 + 코드 채점", "판정만 LLM · 점수 산술은 코드")],
        data=[("30", "평가 케이스"),
              ("180", "확정 보고서"),
              ("6", "고객사 이력"),
              ("1.7만 자", "30회차 누적 입력")])

    # ========================= 31 보고서 작성 에이전트 =========================
    eval_slide(
        prs, AT + 2,
        headline="품질과 토큰 두 기준으로 B 구조를 골랐다",
        source="출처: SalesLuv 보고서작성 에이전트 평가 "
               "(salesluv-report-eval-v1 · 4주 가상 영업 시나리오 · 실제 고객 데이터 미사용)",
        kpis=[("95.4점", "B 구조 종합 점수", "A 93.1 · C 94.0"),
              ("46%", "A 대비 토큰 사용량", "10.01M → 4.57M"),
              ("76.3점", "B 월간 — 가장 낮은 유형", "미팅 96.8 · 일일 95.6 · 주간 87.8")],
        featured=1,
        steps=[("정답지 먼저 확정", "LLM 생성 → 사람 검수 · 보정 후 고정"),
               ("정답과 입력 분리", "input.json ↔ golden.json"),
               ("사실 단위 판정", "충족 · 누락 · 왜곡 + 오류 출처 · 중대 오류"),
               ("코드로 재검사", "구조명 숨겨 위치 교차 · 인용 재검증")],
        data=[("53", "평가 케이스"),
              ("36", "미팅 보고서"),
              ("17", "일일 12 · 주간 4 · 월간 1"),
              ("27", "가상 딜")],
        caveat="C 구조는 입력 한도 초과로 월간 실패")

    # ========================= 32 딜 승산 예측 모델 =========================
    eval_slide(
        prs, AT + 3,
        headline="정확도가 아니라 Brier와 FP로 Stacking_LR을 골랐다",
        source="출처: SalesLuv 딜 승산 예측 모델 평가 "
               "(Salvirt B2B Sales Dataset · 공개 영문 데이터 · 30회 반복 분할)",
        kpis=[("0.1880", "Stacking_LR Brier", "7개 후보 중 1위 · 낮을수록 좋음"),
              ("16.15", "FP — 7개 후보 중 2위", "최저는 LogisticRegression 16.09"),
              ("+4.01%p", "Accuracy 기준선 대비", "69.58% → 73.60%")],
        featured=0,
        steps=[("항목 13개 선별", "보고서에서 일관되게 뽑히는 항목"),
               ("누수 차단", "198개 입력 묶음 → Train 158 / Test 40"),
               ("결측 마스킹", "행마다 Unknown 4개 · 448건 × 10세트"),
               ("Brier · FP로 선택", "Train 안에서만 설정 · Test 제외")],
        data=[("448", "원본 딜 · Won 227 · Lost 221"),
              ("13", "입력 항목 (22개 중 선별)"),
              ("4,480", "마스킹 후 학습 행"),
              ("30회", "반복 분할 평가")])

    # 뒤에 붙은 세 장을 29p 다음 자리로 옮긴다
    ids = prs.slides._sldIdLst
    for i, el in enumerate(list(ids)[base:]):
        ids.remove(el)
        ids.insert(AT + i, el)

    fixed = renumber(prs)
    prs.save(OUT)
    print("saved", OUT, len(ids), "slides · 번호 수정", fixed, "장")


if __name__ == "__main__":
    build()
