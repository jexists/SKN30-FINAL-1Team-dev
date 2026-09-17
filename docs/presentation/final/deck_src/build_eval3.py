"""03 검증과 확장 — 평가 슬라이드 3장만 담은 별도 덱.

v3 pptx 는 열지 않는다. new_deck() 으로 새로 시작하므로 원본을 건드릴 수 없다.
디자인은 base_v3 프레임과 v3 30p·33p 의 관용구(KPI 띠 · 세로 흐름 · GRAY 데이터 블록)를 그대로 쓴다.
제목은 고정 제목만 쓰고, 결론 한 줄은 제목 아래 첫 줄이 맡는다.
수치는 docs/presentation/eval 의 평가 덱 3개에만 근거한다 (check_eval3.py 가 대조).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from textwidth import width

from base_v3 import (
    BLUE, BLUE_600, BLUE_LIGHT, CW, GRAY, INK, M, MUTED, SUB, TINT, TINT2,
    flat, grid, kpi, label, new_deck, slide, write,
)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "SalesLuv_03_검증과확장.pptx")
CH3 = "03 검증과 확장"
AT = 29                            # v3 29p(평가 개요) 뒤 — 삽입 위치 기준 번호

# ---------- 공통 기하 (본문 2.04 ~ 6.62) ----------
LEAD_Y = 2.04                      # 결론 한 줄
KPI_Y, KPI_H = 2.50, 1.78          # v3 30p·33p 와 같은 KPI 띠 높이
LAB_Y = 4.44
ROW_Y, ROW_H = 4.80, 1.82          # 4.80 + 1.82 = 6.62 (BOT)
FLOW_W = 7.20                      # 좌: 평가 방법
DATA_X = M + FLOW_W + 0.55         # 우: 평가 데이터
DATA_W = CW - FLOW_W - 0.55
STEP_H, STEP_GAP = 0.425, 0.04     # 4 × 0.425 + 3 × 0.04 = 1.82
DATA_Y0, DATA_PITCH = 0.18, 0.37   # 4행이 ROW_H 안에 들어가는 간격
DESC_X, DESC_W = 3.35, FLOW_W - 3.65   # 단계 설명 칸 — 한 줄로 끝나야 한다


def lead(sl, text):
    """결론 한 줄. 제목이 고정 제목이라 결론은 본문 첫 줄이 맡는다."""
    write(sl, M, LEAD_Y, CW, 0.34, [(text, dict(size=20, weight=600, color=INK, line=1.25))])


def kpi_row(sl, items, featured):
    w, xs = grid(len(items), 0.3)
    for i, (val, lab, sub) in enumerate(items):
        hot = i == featured
        flat(sl, xs[i], KPI_Y, w, KPI_H, fill=(TINT2 if hot else TINT),
             accent=(BLUE if hot else None))
        kpi(sl, xs[i] + 0.34, KPI_Y + 0.26, w - 0.68, val, lab, sub,
            color=(BLUE if hot else INK))


def method_flow(sl, steps):
    """번호 · 단계명 · 설명을 한 줄에 둔 세로 흐름."""
    label(sl, M, LAB_Y, "평가 방법", w=FLOW_W)
    for i, (title, desc) in enumerate(steps):
        y = ROW_Y + i * (STEP_H + STEP_GAP)
        last = i == len(steps) - 1
        flat(sl, M, y, FLOW_W, STEP_H, fill=(TINT2 if last else TINT),
             accent=(BLUE if last else None), radius=0.09)
        write(sl, M + 0.32, y + 0.085, 0.6, 0.28,
              [("%02d" % (i + 1), dict(size=16, weight=700,
                                       color=(BLUE if last else BLUE_LIGHT), line=1.25))])
        write(sl, M + 0.88, y + 0.085, 2.4, 0.28,
              [(title, dict(size=16, weight=700, color=INK, line=1.25))])
        write(sl, M + DESC_X, y + 0.105, DESC_W, 0.26,
              [(desc, dict(size=14, weight=400, color=SUB, line=1.25))])


def data_block(sl, rows):
    """우측 GRAY 블록 — 건수는 값 + 라벨 한 줄로만."""
    label(sl, DATA_X, LAB_Y, "평가 데이터", w=DATA_W - 0.2, color=MUTED)
    flat(sl, DATA_X, ROW_Y, DATA_W, ROW_H, fill=GRAY)
    vw = max(width(v, 19, 700) for v, _ in rows) + 0.16      # 값 칸은 가장 긴 값에 맞춘다
    for i, (val, lab) in enumerate(rows):
        y = ROW_Y + DATA_Y0 + i * DATA_PITCH
        write(sl, DATA_X + 0.32, y, vw, 0.32,
              [(val, dict(size=19, weight=700, color=BLUE_600, line=1.25))])
        write(sl, DATA_X + 0.32 + vw, y + 0.05, DATA_W - 0.64 - vw, 0.26,
              [(lab, dict(size=14, weight=400, color=SUB, line=1.25))])


def eval_slide(prs, page, *, headline, conclusion, source, kpis, featured, steps, data):
    sl, _ = slide(prs, page, chapter=CH3, headline=headline, source=source)
    lead(sl, conclusion)
    kpi_row(sl, kpis, featured)
    method_flow(sl, steps)
    data_block(sl, data)
    return sl


def build():
    prs = new_deck()

    # ========================= 30 미팅 브리핑 에이전트 =========================
    eval_slide(
        prs, AT + 1,
        headline="미팅 브리핑 에이전트",
        conclusion="30건 평균 89.8%, 근거 오류는 0건이었다",
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
        headline="보고서 작성 에이전트",
        conclusion="품질과 토큰 두 기준으로 B 구조를 골랐다 — C는 월간을 만들지 못했다",
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
              ("27", "가상 딜")])

    # ========================= 32 딜 승산 예측 모델 =========================
    eval_slide(
        prs, AT + 3,
        headline="딜 승산 예측 모델",
        conclusion="정확도가 아니라 Brier와 FP로 Stacking_LR을 골랐다",
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

    prs.save(OUT)
    print("saved", OUT, len(prs.slides._sldIdLst), "slides")


if __name__ == "__main__":
    build()
