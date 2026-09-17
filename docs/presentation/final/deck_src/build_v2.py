"""SalesLuv 최종 발표 덱 v2 — 큰 타이포 · 주제별 분리 리디자인.

본문 18pt 이상을 지키기 위해 v1의 한 장을 여러 장으로 나눈다.
사실·수치는 deck_prompt.md 확정본만 사용한다.
"""

import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cairosvg
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches, Pt

from base_v2 import (
    BAR, BLUE, BLUE_500, BLUE_600, BLUE_DEEP, BLUE_LIGHT, BLUE_PALE, BOT, BORDER, C, COL, CW,
    DARK, DARK_SUB, EYE_Y, GRAY, HAIRLINE, INK, L, LOGO, LOGO_WHITE, LOGO_H, LOGO_W, M, MUTED,
    R, SH, SUB, SW, T_BODY, T_CARD, T_KPI, T_NOTE, TINT, TINT2, TOP, TOP_NOSUB, WHITE,
    _bar, add_chart, arrow, blank, bullets, card, circle, divider, flat, ghost, grid, keyline,
    kpi, label, line, make_white_logo, new_deck, note, numcard, para, pill, placeholder, slide,
    table, write,
)
from pptx.dml.color import RGBColor

OUT = ("/Volumes/Jexists/skn30/SKN30-FINAL-1Team-dev/docs/presentation/final/"
       "SalesLuv_최종발표_260918_v2.pptx")
HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "icons")

CH1 = "01 문제 정의"
CH2 = "02 설계와 구현"
CH3 = "03 검증과 확장"
APX = "부록 · 검증 자료"
PH = "[입력 예정]"

BRAND = {"react": "149ECA", "typescript": "3178C6", "vite": "646CFF", "fastapi": "009688",
         "python": "3776AB", "sqlalchemy": "D71F00", "supabase": "1FA97A", "postgresql": "4169E1",
         "openai": "412991", "langchain": "1C3C3C", "scikitlearn": "F7931E", "docker": "2496ED",
         "githubactions": "2088FF", "amazonwebservices": "E8871A", "amazons3": "569A31",
         "amazonec2": "E8871A"}
ICON_SRC = "https://cdn.jsdelivr.net/npm/simple-icons@13/icons/{}.svg"


def icon(slug):
    os.makedirs(ICON_DIR, exist_ok=True)
    path = os.path.join(ICON_DIR, slug + ".png")
    if not os.path.exists(path):
        req = urllib.request.Request(ICON_SRC.format(slug), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            svg = r.read().decode()
        svg = svg.replace("<svg ", '<svg fill="#%s" ' % BRAND.get(slug, "45515E"), 1)
        cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=320, output_height=320)
    return path


def put_icon(sl, slug, x, y, size):
    return sl.shapes.add_picture(icon(slug), Inches(x), Inches(y), Inches(size), Inches(size))


def build():
    make_white_logo()
    prs = new_deck()
    pg = [0]

    def p():
        pg[0] += 1
        return pg[0]

    # ========================= 01 표지 =========================
    sl = blank(prs, dark=True)
    sl.shapes.add_picture(LOGO_WHITE, Inches(SW - M - LOGO_W), Inches(EYE_Y - 0.02),
                          Inches(LOGO_W), Inches(LOGO_H))
    write(sl, M, 1.95, 8.0, 0.34,
          [("SKN30 1Team · CassTerra", dict(size=17, weight=600, color=BLUE_LIGHT, line=1.25))])
    write(sl, M, 2.38, 10.0, 1.4, [("SalesLuv", dict(size=78, weight=700, color=WHITE, line=1.1))])
    write(sl, M, 3.85, 10.0, 0.5,
          [("영업의 흐름을 연결하는 멀티에이전트 CRM",
            dict(size=25, weight=500, color=DARK_SUB, line=1.35))])
    _bar(sl, M, 4.62, 2.0, 0.075, BLUE)
    write(sl, M, 4.92, 10.0, 1.1,
          [("CONNECT THE HISTORY.", dict(size=23, weight=700, color=WHITE, line=1.4)),
           ("APPROVE THE NEXT MOVE.", dict(size=23, weight=700, color=BLUE_LIGHT, line=1.4))])
    write(sl, M, 6.28, 10.0, 0.7,
          [("2026.09.18 (FRI) 15:00", dict(size=18, weight=600, color=WHITE, line=1.4)),
           ("천성배 · 정주애 · 박제섭 · 박지유",
            dict(size=18, weight=400, color=DARK_SUB, line=1.4, spacing_before=4))])
    _bar(sl, 0, SH - 0.16, SW, 0.16, BLUE)
    p()

    # ========================= 02 목차 =========================
    sl, top = slide(prs, p(), chapter="목차", headline="문제 → 구현 → 검증, 세 파트로 설명합니다",
                    subtitle="발표 시간 15분")
    w3, xs = grid(3, 0.5)
    toc = [("01", "문제 정의", "왜 이 문제를 골랐는가", "팀 · 주제 · 문제\n시장 · 경쟁 · 해결책 · 기대효과"),
           ("02", "설계와 구현", "무엇을 어떻게 만들었는가", "시나리오 · 시연 · 기술 스택\n아키텍처 · 에이전트 · 흐름"),
           ("03", "검증과 확장", "제대로 동작하는지 어떻게 확인했는가", "에이전트별 평가 · 실패와 개선\n보완점 · 향후 계획 · 결론")]
    for i, (n, t, lead, kw) in enumerate(toc):
        x = xs[i]
        if i:
            line(sl, x - 0.25, top + 0.1, x - 0.25, BOT - 0.55, color=HAIRLINE)
        ghost(sl, x, top, w3, n, size=66, color=BLUE_PALE)
        write(sl, x, top + 1.22, w3, 0.45, [(t, dict(size=27, weight=700, color=INK, line=1.25))])
        write(sl, x, top + 1.82, w3, 0.7, [(lead, dict(size=18, weight=600, color=BLUE_600, line=1.4))])
        line(sl, x, top + 2.62, x + w3 - 0.3, top + 2.62, color=HAIRLINE)
        lines = [(s, dict(size=18, weight=400, color=SUB, line=1.45,
                          spacing_before=(0 if j == 0 else 4))) for j, s in enumerate(kw.split("\n"))]
        write(sl, x, top + 2.8, w3 - 0.2, 1.2, lines)

    # ========================= 03 파트 디바이더 1 =========================
    divider(prs, "01", "문제 정의", "왜 이 프로젝트가 필요한가", p())

    # ========================= 04 팀 구성 =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="네 명이 기획부터 배포까지 나눠 맡았다",
                    subtitle="PM · 풀스택 · 에이전트 · 시연")
    w4, xs = grid(4, 0.32)
    team = [("천성배", ["P.M", "OCR", "자료요약 Agent"]),
            ("정주애", ["Full Stack", "Infra"]),
            ("박제섭", ["기술리더", "미팅분석 Agent", "업무보고 Agent"]),
            ("박지유", ["영업계약 Agent", "일정관리 Agent", "시연영상"])]
    for i, (name, roles) in enumerate(team):
        x = xs[i]
        placeholder(sl, x, top, w4, 1.95, "[PHOTO]", size=16)
        write(sl, x, top + 2.12, w4, 0.42, [(name, dict(size=23, weight=700, color=INK, line=1.25))])
        _bar(sl, x, top + 2.66, 0.5, 0.05, BLUE)
        for j, role in enumerate(roles):
            write(sl, x, top + 2.86 + j * 0.36, w4, 0.34,
                  [(role, dict(size=T_BODY, weight=(600 if j == 0 else 400),
                               color=(BLUE_600 if j == 0 else SUB), line=1.35))])

    # ========================= 05 프로젝트 주제 =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="담당자의 고객 맥락을 팀이 이어받게 한다",
                    subtitle="프로젝트 한 줄 정의와 세 가지 키워드",
                    source="출처: 프로젝트 기획서(2026-08)")
    flat(sl, M, top, CW, 1.05, fill=TINT2)
    write(sl, M + 0.4, top + 0.28, CW - 0.8, 0.6,
          [("영업의 시작부터 끝까지, 한 번에 해결하는 멀티에이전트 CRM",
            dict(size=27, weight=700, color=BLUE_DEEP, line=1.3))], align=C)
    w3, xs = grid(3, 0.36)
    defs = [("국내 B2B 영업", "고객 · 딜 · 일정 · 보고가\n흩어져 있는 조직"),
            ("멀티에이전트", "판단 · 초안 · 제안을\n다섯 에이전트로 분담"),
            ("Human-in-the-loop", "AI는 초안까지,\n확정은 사람의 승인으로")]
    dy = top + 1.45
    for i, (t, d) in enumerate(defs):
        x = xs[i]
        _bar(sl, x, dy, w3, 0.05, BLUE if i == 2 else BLUE_PALE)
        write(sl, x, dy + 0.28, w3, 0.4, [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        lines = [(s, dict(size=T_BODY, weight=400, color=SUB, line=1.45,
                          spacing_before=(0 if j == 0 else 2))) for j, s in enumerate(d.split("\n"))]
        write(sl, x, dy + 0.82, w3, 1.0, lines)
    note(sl, M, BOT - 0.4, CW,
         "CRM — 고객과 나눈 이야기를 기억하는 시스템        딜 — 하나의 거래 기회", size=16)

    # ========================= 06 문제 정의 (흐름) =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="영업 맥락은 다섯 지점에서 끊긴다",
                    subtitle="정보 분산에서 시작해 인수인계에서 무너진다",
                    source="출처: 프로젝트 기획서(2026-08) · 영업사원 출신 PM의 현장 경험")
    probs = [("01", "영업정보 분산", "고객 · 계약 · 매출이 따로 관리된다"),
             ("02", "영업흐름 단절", "리드 → 계약 → 매출이 이어지지 않는다"),
             ("03", "판단 공백", "진행 상황과 예측이 보이지 않는다"),
             ("04", "인수인계 맥락 소실", "관계와 노하우가 담당자와 함께 사라진다"),
             ("05", "범용 CRM 한계", "B2B 영업 현장에는 기능이 부족하다")]
    for i, (n, t, d) in enumerate(probs):
        y = top + i * 0.84
        act = i == 3
        flat(sl, M, y, CW, 0.7, fill=(TINT2 if act else TINT), accent=(BLUE if act else None))
        write(sl, M + 0.36, y + 0.13, 0.9, 0.44,
              [(n, dict(size=26, weight=700, color=(BLUE if act else BLUE_LIGHT), line=1.2))])
        write(sl, M + 1.4, y + 0.19, 3.2, 0.4,
              [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        write(sl, M + 4.9, y + 0.21, CW - 5.25, 0.4,
              [(d, dict(size=T_BODY, weight=400, color=SUB, line=1.3))])

    # ========================= 07 문제 결론 =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="결국 남는 문제는 암묵지다",
                    subtitle="조직에 남지 않는 지식은 담당자와 함께 사라진다",
                    source="출처: 프로젝트 기획서(2026-08) · 영업사원 출신 PM의 현장 경험")
    flat(sl, M, top, CW, 1.6, fill=TINT2, accent=BLUE)
    write(sl, M + 0.45, top + 0.3, CW - 0.9, 1.1,
          [("고객 맥락과 영업 노하우는 담당자 개인의 암묵지로만 쌓인다",
            dict(size=26, weight=700, color=INK, line=1.3)),
           ("조직 자산으로 남지 않아 담당자가 바뀌면 함께 사라진다",
            dict(size=T_CARD, weight=400, color=SUB, line=1.35, spacing_before=8))])
    label(sl, M, top + 1.95, "이 판단의 근거")
    w3, xs = grid(3, 0.36)
    basis = [("프로젝트 기획서", "2026-08 작성\n문제 정의와 범위"),
             ("현장 경험", "영업사원 출신 PM의\n실무 경험에서 출발"),
             ("정량 근거는 없음", "설문 · 인터뷰 데이터 없이\n검증할 가설로 다룬다")]
    by = top + 2.4
    for i, (t, d) in enumerate(basis):
        flat(sl, xs[i], by, w3, 1.7, fill=(GRAY if i == 2 else TINT))
        write(sl, xs[i] + 0.3, by + 0.28, w3 - 0.6, 0.4,
              [(t, dict(size=T_CARD, weight=600, color=(MUTED if i == 2 else INK), line=1.25))])
        lines = [(s, dict(size=T_BODY, weight=400, color=SUB, line=1.4,
                          spacing_before=(0 if j == 0 else 2))) for j, s in enumerate(d.split("\n"))]
        write(sl, xs[i] + 0.3, by + 0.8, w3 - 0.6, 0.9, lines)

    # ========================= 08 시장 규모 =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="국내 CRM 시장은 2033년까지 두 배 이상 커진다",
                    subtitle="영업 CRM 단독 통계는 공개된 것이 없어 상위 시장으로 판단했다",
                    source="출처: Grand View Research(2026) · KISDI 2026(원자료 Gartner 2025) · 환율 2026-09-15 1,347.8원")
    cwid = 7.1
    label(sl, M, top, "국내 CRM 시장 규모 (조원)")
    add_chart(sl, COL, M - 0.2, top + 0.4, cwid, 3.15, ["2025년", "2026년", "2033년"],
              [("국내 CRM 시장", [2.51, 2.75, 5.46])], label_fmt="0.00", gap=110, y_max=6.0,
              axis_size=T_NOTE, label_size=16)
    rx = M + cwid + 0.5
    rw = CW - cwid - 0.5
    kpi(sl, rx, top, rw, "10.3%", "국내 CRM 연평균 성장률", "2026–2033", tint=True, h=1.72)
    kpi(sl, rx, top + 1.85, rw, "17.1%", "국내 SaaS 연평균 성장률",
        "2025–2029 · 2조 1,295억 → 4조 164억", color=BLUE_500, tint=True, h=1.82)
    note(sl, M, BOT - 0.35, CW,
         "CRM과 SaaS는 시장 정의가 달라 합산하지 않는다 · 영업 CRM 단독 시장 통계는 공개된 것이 없다", size=16)

    # ========================= 09 진입 조건 =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="진입 조건은 근거 · 연결 · 승인 세 가지다",
                    subtitle="AI 요약은 이미 존재한다. 남은 자리는 그 다음이다",
                    source="출처: 각 사 공식 제품 페이지(2026-09-15 확인) · 팀 시장 조사")
    w3, xs = grid(3, 0.36)
    conds = [("01", "경쟁 현실", "AI 미팅 요약과 후속조치\n제안은 이미 존재한다"),
             ("02", "초기 ICP", "문서 · 견적 · 계약이\n복잡한 B2B 영업팀"),
             ("03", "차별화 조건", "근거 검색 + 데이터 연결\n+ 담당자 승인")]
    for i, (n, t, d) in enumerate(conds):
        numcard(sl, xs[i], top, w3, 2.9, n, t, d, active=(i == 2), num_size=42, title_lines=1)
    keyline(sl, top + 3.1, "성장하는 시장에서 우리가 고른 자리 — 근거를 대고, 데이터를 잇고, 사람이 승인한다")

    # ========================= 10 경쟁 비교 ① =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="기본 기능은 세 제품 모두 갖추고 있다",
                    subtitle="고객 관리 · 딜 관리 · 실적 분석은 시장의 기본값",
                    source="출처: 각 사 공식 제품 페이지(2026-09-15 확인) · 기능군 판정은 팀 조사 기준")
    rows = [["제품", "고객 · 거래처 관리", "파이프라인 · 딜 관리", "영업 실적 · 매출 분석"],
            ["세일즈맵", "●", "●", "●"],
            ["핑거세일즈", "●", "●", "●"],
            ["세일즈인사이트", "●", "●", "△"],
            ["SalesLuv", "●", "●", "●"]]
    table(sl, M, top, CW, 3.4, rows, col_w=[3.3, 2.931, 2.931, 2.931], highlight_row=4)
    note(sl, M, top + 3.55, CW, "● 제공        △ 일부        – 공개 자료에서 확인되지 않음", size=16)

    # ========================= 11 경쟁 비교 ② =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="차이는 AI 유무가 아니라 승인이 순환하는 구조다",
                    subtitle="승인 결과가 다음 행동으로 이어지는 제품은 아직 없다",
                    source="출처: 각 사 공식 제품 페이지(2026-09-15 확인) · 기능군 판정은 팀 조사 기준")
    rows = [["제품", "AI 기능", "사용자 승인 후 업무 반영", "승인 결과 → 다음 행동 순환"],
            ["세일즈맵", "△", "–", "–"],
            ["핑거세일즈", "●", "●", "–"],
            ["세일즈인사이트", "–", "–", "–"],
            ["SalesLuv", "●", "●", "●"]]
    table(sl, M, top, CW, 3.4, rows, col_w=[3.3, 2.5, 3.146, 3.147], highlight_row=4)
    note(sl, M, top + 3.55, CW,
         "● 제공        △ 일부        – 공개 자료에서 확인되지 않음", size=16)

    # ========================= 12 차별점 =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="SalesLuv가 더하는 것은 세 가지다",
                    subtitle="근거 기반 추천 · Human-in-the-loop · 다음 행동으로 순환",
                    source="출처: SalesLuv 구현 코드(develop, 2026-09-17)")
    w3, xs = grid(3, 0.36)
    diffs = [("근거 기반 추천", "보고서와 자료를 검색해\n출처와 함께 제안한다", BLUE_PALE),
             ("Human-in-the-loop", "AI 제안은 초안일 뿐,\n담당자가 확정한다", BLUE_LIGHT),
             ("다음 행동으로 순환", "승인 결과가 다시\n다음 추천을 부른다", BLUE)]
    for i, (t, d, ac) in enumerate(diffs):
        flat(sl, xs[i], top, w3, 2.7, fill=TINT, accent=ac)
        write(sl, xs[i] + 0.38, top + 0.42, w3 - 0.7, 0.45,
              [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        lines = [(s, dict(size=T_BODY, weight=400, color=SUB, line=1.45,
                          spacing_before=(0 if j == 0 else 2))) for j, s in enumerate(d.split("\n"))]
        write(sl, xs[i] + 0.38, top + 1.1, w3 - 0.7, 1.2, lines)
    keyline(sl, top + 2.95, "경쟁 제품에도 AI는 있다. 다른 것은 승인 결과가 다음 행동으로 순환하는 구조다")

    # ========================= 13 해결책 =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="기록이 초안이 되고, 승인이 다음 일정이 된다",
                    subtitle="네 단계가 딜 하나를 중심으로 순환한다",
                    source="출처: SalesLuv 구현 코드(develop, 2026-09-17)")
    w4, xs = grid(4, 0.3)
    sols = [("01", "미팅 기록 입력", "원문 · 음성 STT\n이미지 OCR"),
            ("02", "AI 초안 + 딜 승산", "딜별 귀속 · 13개 특성\n성사 확률"),
            ("03", "사람이 확정", "근거 대조 · 확정\n팀장 검토"),
            ("04", "다음 미팅 · 브리핑", "날짜 추천\n캘린더 승인")]
    for i, (n, t, d) in enumerate(sols):
        numcard(sl, xs[i], top, w4, 2.75, n, t, d, active=(i == 2), num_size=40, title_lines=1)
        if i < 3:
            arrow(sl, xs[i] + w4 + 0.04, top + 1.38, xs[i] + w4 + 0.26, top + 1.38,
                  color=BLUE_LIGHT, width=2)
    keyline(sl, top + 3.0, "04의 승인 결과가 다시 01로 — 모든 기록은 딜(sales_deal) 하나로 연결된다")

    # ========================= 14 기대효과 ① =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="파일럿에서 네 개 지표로 검증한다",
                    subtitle="아래 수치는 측정 목표가 아니라 측정할 자리다",
                    source="출처: 프로젝트 기획서 9장 · 파일럿 KPI 정의")
    w4, xs = grid(4, 0.3)
    kpis = [("보고서 작성시간", "활성 작업시간 중앙값"),
            ("당일 제출률", "당일 제출 ÷ 보고 대상"),
            ("필수정보 초회 완성률", "첫 제출 필수항목 충족"),
            ("팀장 검토시간", "검토 작업시간 중앙값")]
    for i, (t, d) in enumerate(kpis):
        placeholder(sl, xs[i], top, w4, 1.5, "[수치 입력 예정]", size=T_BODY)
        write(sl, xs[i], top + 1.68, w4, 0.4, [(t, dict(size=19, weight=600, color=INK, line=1.3))])
        write(sl, xs[i], top + 2.12, w4, 0.6, [(d, dict(size=T_BODY, weight=400, color=SUB, line=1.4))])
    keyline(sl, top + 3.1, "정량 수치는 파일럿에서 검증할 가설이며 실측값이 아니다")

    # ========================= 15 기대효과 ② =========================
    sl, top = slide(prs, p(), chapter=CH1, headline="보고서는 아래 단계의 확정본 위에 쌓인다",
                    subtitle="같은 내용을 네 번 쓰지 않는다",
                    source="출처: SalesLuv 구현 코드(develop, 2026-09-17)")
    lw = 6.6
    levels = [("미팅 보고서", BLUE_PALE, INK), ("일일 업무보고", BLUE_LIGHT, WHITE),
              ("주간 업무보고", BLUE_500, WHITE), ("월간 업무보고", BLUE, WHITE)]
    for i, (t, fc, tc) in enumerate(levels):
        y = top + i * 0.92
        ins = i * 0.38
        sh = card(sl, M + ins, y, lw - ins * 2, 0.7, fill=fc, shadow=False, radius=0.1)
        tf = sh.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para(tf, t, size=T_BODY, weight=600, color=tc, line=1.2, align=C, first=True)
        if i < 3:
            arrow(sl, M + lw / 2, y + 0.73, M + lw / 2, y + 0.89, color=BLUE_LIGHT, width=2)
    note(sl, M, top + 3.75, lw, "각 단계는 아래 단계의 확정 제출본을 원천으로 사용한다", size=16)
    rx = M + lw + 0.6
    rw = CW - lw - 0.6
    label(sl, rx, top, "정성 효과", w=rw)
    items = [("자동 집계 · 검증", "흩어진 기록을 모아 숫자를 스스로 맞춘다"),
             ("승인 기반 반영", "확정된 내용만 CRM · 캘린더에 반영한다"),
             ("암묵지의 자산화", "개인의 노하우가 조직의 기록으로 남는다")]
    for i, (t, d) in enumerate(items):
        y = top + 0.5 + i * 1.18
        flat(sl, rx, y, rw, 1.0, fill=TINT)
        write(sl, rx + 0.3, y + 0.16, rw - 0.6, 0.35,
              [(t, dict(size=19, weight=600, color=BLUE_DEEP, line=1.25))])
        write(sl, rx + 0.3, y + 0.56, rw - 0.6, 0.4,
              [(d, dict(size=T_BODY, weight=400, color=SUB, line=1.35))])

    # ========================= 16 파트 디바이더 2 =========================
    divider(prs, "02", "설계와 구현", "그래서 어떻게 해결했는가", p())

    # ========================= 17 시나리오 ① =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="AI는 미팅을 준비하고 기록을 받아 적는다",
                    subtitle="사용자 시나리오 01 – 03",
                    source="출처: SalesLuv 구현 코드(develop, 2026-09-17)")
    w3, xs = grid(3, 0.36)
    sc1 = [("01", "미팅 준비", "영업·계약관리 에이전트가\n다음 미팅을 추천하고\n사람이 캘린더에 승인한다"),
           ("02", "사전 브리핑", "과거 보고서와 자료를\nRAG로 찾아 근거와 함께\n브리핑을 만든다"),
           ("03", "미팅 후 입력", "미팅 원문을 직접 쓰거나\n음성 파일 STT · 이미지 OCR로\n기록을 올린다")]
    for i, (n, t, d) in enumerate(sc1):
        numcard(sl, xs[i], top, w3, 3.3, n, t, d, num_size=42, title_lines=1)
    keyline(sl, top + 3.5, "여기까지는 모두 AI가 준비한 초안 — 아직 확정된 것은 없다")

    # ========================= 18 시나리오 ② =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="확정은 사람이 하고, 그 확정이 다음을 부른다",
                    subtitle="사용자 시나리오 04 – 06",
                    source="출처: SalesLuv 구현 코드(develop, 2026-09-17)")
    w3, xs = grid(3, 0.36)
    sc2 = [("04", "보고서 확정", "사람이 확정해야\n저장된다\nAI 단독 저장은 없다"),
           ("05", "보고서 누적", "확정본이 RAG에 적재되고\n다음 미팅 추천\n트리거가 걸린다"),
           ("06", "기간 보고", "일일 · 주간 · 월간으로\n묶여 팀장 검토로\n올라간다")]
    for i, (n, t, d) in enumerate(sc2):
        numcard(sl, xs[i], top, w3, 3.3, n, t, d, active=(i == 0), num_size=42, title_lines=1)
    keyline(sl, top + 3.5, "확정 결과가 다시 01 미팅 준비로 순환한다")

    # ========================= 19 시연 =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="한 번의 영업 사이클을 실제 화면으로 따라간다",
                    subtitle="[시연 동선 한 줄 입력 예정]")
    vw = 7.2
    placeholder(sl, M, top, vw, vw * 9 / 16, "시연 영상 (16:9)", size=20)
    rx = M + vw + 0.5
    rw = CW - vw - 0.5
    label(sl, rx, top, "시연 체크포인트", w=rw)
    cps = ["자료실 업로드 → 요약", "캘린더 추천 승인", "AI 브리핑 확인",
           "미팅 원문 → 초안 생성", "보고서 확정 → 다음 추천"]
    for i, t in enumerate(cps):
        y = top + 0.52 + i * 0.72
        flat(sl, rx, y, rw, 0.6, fill=TINT)
        write(sl, rx + 0.24, y + 0.15, 0.4, 0.3,
              [(str(i + 1), dict(size=T_BODY, weight=700, color=BLUE, line=1.3))])
        write(sl, rx + 0.62, y + 0.15, rw - 0.85, 0.3,
              [(t, dict(size=T_BODY, weight=500, color=INK, line=1.3))])

    # ========================= 20 기술 스택 ① =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="프론트 · 백엔드 · 데이터는 표준 조합으로 묶었다",
                    subtitle="화면부터 인증 · 저장까지",
                    source="출처: frontend/package.json · backend/uv.lock (2026-09-11 확인)")
    w3, xs = grid(3, 0.36)

    def stack_group(x, y, w, h, title, items, extra=()):
        flat(sl, x, y, w, h, fill=GRAY)
        write(sl, x + 0.3, y + 0.26, w - 0.6, 0.35,
              [(title, dict(size=16, weight=700, color=BLUE_600, line=1.25))])
        line(sl, x + 0.3, y + 0.72, x + w - 0.3, y + 0.72, color=BORDER)
        for i, (slug, name) in enumerate(items):
            iy = y + 0.85 + i * 0.66
            sh = card(sl, x + 0.3, iy, w - 0.6, 0.6, fill=WHITE, shadow=False, radius=0.08)
            put_icon(sl, slug, x + 0.48, iy + 0.13, 0.34)
            write(sl, x + 0.96, iy + 0.14, w - 1.3, 0.34,
                  [(name, dict(size=T_BODY, weight=600, color=INK, line=1.25))])
        ey = y + 0.85 + len(items) * 0.66 + 0.04
        for j, t in enumerate(extra):
            write(sl, x + 0.4, ey + j * 0.36, w - 0.7, 0.34,
                  [("· " + t, dict(size=T_BODY, weight=400, color=SUB, line=1.3))])

    stack_group(xs[0], top, w3, 3.3, "FRONTEND",
                [("react", "React 19"), ("typescript", "TypeScript"), ("vite", "Vite")])
    stack_group(xs[1], top, w3, 3.3, "BACKEND",
                [("fastapi", "FastAPI"), ("python", "Python 3.13"), ("sqlalchemy", "SQLAlchemy")])
    stack_group(xs[2], top, w3, 3.3, "DATA · AUTH",
                [("supabase", "Supabase"), ("postgresql", "PostgreSQL")],
                ["pgvector", "Auth · Storage"])

    # ========================= 21 기술 스택 ② =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="AI 생태계를 중심에 두고 스택을 맞췄다",
                    subtitle="모델은 provider adapter로 교체할 수 있다",
                    source="출처: backend/uv.lock · 운영 설정값(2026-09-11 확인)")
    w2, xs2 = grid(2, 0.5)
    stack_group(xs2[0], top, w2, 3.3, "AI · ML",
                [("openai", "OpenAI API"), ("langchain", "LangChain"), ("scikitlearn", "scikit-learn")],
                ["DeepAgents · CatBoost · RunPod OCR"])
    stack_group(xs2[1], top, w2, 3.3, "DEVOPS",
                [("docker", "Docker"), ("githubactions", "GitHub Actions"),
                 ("amazonwebservices", "AWS")])
    my = top + 3.45
    flat(sl, M, my, CW, 0.75, fill=TINT2, accent=BLUE)
    write(sl, M + 0.36, my + 0.17, CW - 0.7, 0.5,
          [("LLM gpt-5.6-luna        STT gpt-4o-transcribe        OCR PaddleOCR (RunPod GPU)",
            dict(size=T_BODY, weight=600, color=BLUE_DEEP, line=1.3))])

    # ========================= 22 아키텍처 =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="입구는 하나, 오래 걸리는 AI 작업은 따로 뗐다",
                    source="출처: deploy/backend/deploy.sh · backend/app/services/agent_worker.py")
    lane_x, lane_w = 1.9, 5.5
    side_x, side_w = 7.7, 5.01
    rows = [
        (2.02, 0.58, "CLIENT", MUTED, GRAY, "사용자", None, None, None),
        (2.72, 0.80, "EDGE", BLUE_600, TINT, "CloudFront", "단일 HTTPS 진입점", "amazonwebservices",
         ("amazons3", "S3 (Private)", "React SPA 정적 호스팅")),
        (3.64, 0.80, "APP", BLUE_600, TINT, "EC2 · Nginx · FastAPI", "API 서버 · SSE 진행 상황", "amazonec2",
         ("openai", "OCR · STT 동기 호출", "RunPod PaddleOCR · gpt-4o-transcribe")),
        (4.56, 1.16, "DATA", BLUE, TINT2, "Supabase",
         "PostgreSQL · pgvector · Auth · Storage\nagent_run 작업 큐", "supabase", None),
        (5.84, 0.78, "ASYNC", BLUE_500, TINT, "Agent Worker", "큐 폴링 · 별도 Docker 컨테이너", "docker",
         ("openai", "OpenAI gpt-5.6-luna", "보고서 · 미팅분석 생성")),
    ]
    prev = None
    for (y, h, zone, zc, fc, title, sub, ic, side) in rows:
        w_ = lane_w if zone != "CLIENT" else 2.6
        x_ = lane_x if zone != "CLIENT" else lane_x + (lane_w - 2.6) / 2
        flat(sl, x_, y, w_, h, fill=fc)
        write(sl, M, y + (h - 0.24) / 2, 1.2, 0.3,
              [(zone, dict(size=T_NOTE, weight=700, color=zc, line=1.2))])
        tx = x_ + (0.88 if ic else 0.32)
        if ic:
            put_icon(sl, ic, x_ + 0.34, y + (h - 0.36) / 2, 0.36)
        lines = [(title, dict(size=19, weight=700, color=INK, line=1.25))]
        if sub:
            for j, s in enumerate(sub.split("\n")):
                lines.append((s, dict(size=16, weight=400, color=SUB, line=1.3,
                                      spacing_before=(4 if j == 0 else 1))))
        write(sl, tx, y + (0.13 if sub else (h - 0.3) / 2), w_ - (tx - x_) - 0.25, h, lines)
        if prev is not None:
            arrow(sl, lane_x + lane_w / 2, prev, lane_x + lane_w / 2, y - 0.02,
                  color=BLUE_LIGHT, width=2)
        prev = y + h
        if side:
            s_ic, s_t, s_d = side
            flat(sl, side_x, y, side_w, h, fill=GRAY)
            put_icon(sl, s_ic, side_x + 0.3, y + (h - 0.34) / 2, 0.34)
            write(sl, side_x + 0.78, y + 0.13, side_w - 1.05, h,
                  [(s_t, dict(size=17, weight=600, color=INK, line=1.25)),
                   (s_d, dict(size=T_NOTE, weight=400, color=MUTED, line=1.3, spacing_before=4))])
            arrow(sl, lane_x + lane_w + 0.04, y + h / 2, side_x - 0.04, y + h / 2,
                  color=BLUE_PALE, width=1.5, dashed=True)

    # ========================= 23 아키텍처 설명 =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="빠른 요청과 느린 생성을 다른 길로 보냈다",
                    subtitle="같은 서버에 묶으면 사용자가 기다린다",
                    source="출처: deploy/backend/deploy.sh · backend/app/services/agent_worker.py")
    w3, xs = grid(3, 0.36)
    paths = [("동기 경로", "EC2가 직접 호출한다\n\nOCR — RunPod PaddleOCR\nSTT — gpt-4o-transcribe", BLUE_PALE),
             ("비동기 경로", "agent_run 큐에 쌓고\nAgent Worker가 폴링한다\n\nLLM — gpt-5.6-luna 호출", BLUE),
             ("배포", "GitHub Actions → OIDC\n→ SSM 원격 실행\n\n무중단 blue / green", BLUE_LIGHT)]
    for i, (t, d, ac) in enumerate(paths):
        flat(sl, xs[i], top, w3, 3.3, fill=TINT, accent=ac)
        write(sl, xs[i] + 0.38, top + 0.34, w3 - 0.7, 0.4,
              [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        lines = [(s, dict(size=T_BODY, weight=400, color=SUB, line=1.45,
                          spacing_before=(0 if j == 0 else 2))) for j, s in enumerate(d.split("\n"))]
        write(sl, xs[i] + 0.38, top + 1.0, w3 - 0.7, 2.2, lines)
    keyline(sl, top + 3.5, "SSE로 진행 상황을 흘려보내 사용자가 상태를 볼 수 있게 했다")

    # ========================= 24 에이전트 5종 개요 =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="다섯 에이전트가 판단 · 초안 · 제안을 나눠 맡는다",
                    subtitle="확정은 언제나 사람의 몫으로 남긴다",
                    source="출처: backend/app/agents/ (develop, 2026-09-17)")
    agents = [("미팅분석", "판단 생성", "미팅 원문에서 딜별 귀속과 성사 확률을 만든다", BLUE),
              ("영업 · 계약관리", "상태 허브", "위험 신호와 이력을 보고 다음 미팅을 제안한다", BLUE_LIGHT),
              ("보고서 작성", "실행 지원", "원문과 하위 확정 보고서로 초안을 쓴다", BLUE_PALE),
              ("일정관리", "실행 지원", "저장된 추천이 아직 유효한지 다시 판단한다", BLUE_PALE),
              ("자료요약", "실행 지원", "문서를 구조화 요약하고 RAG 청크로 적재한다", BLUE_PALE)]
    for i, (name, tag, role, ac) in enumerate(agents):
        y = top + i * 0.78
        flat(sl, M, y, CW, 0.66, fill=TINT, accent=ac)
        write(sl, M + 0.36, y + 0.16, 2.9, 0.36,
              [(name, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        pill(sl, M + 3.4, y + 0.17, 1.55, 0.34, tag, fill=WHITE, color=BLUE_600, size=T_NOTE)
        write(sl, M + 5.25, y + 0.18, CW - 5.6, 0.36,
              [(role, dict(size=T_BODY, weight=400, color=SUB, line=1.3))])

    # ========================= 25 에이전트 상세 ① =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="판단과 제안을 만드는 두 에이전트",
                    subtitle="미팅분석 · 영업 · 계약관리",
                    source="출처: backend/app/agents/ (develop, 2026-09-17)")
    w2, xs2 = grid(2, 0.5)

    def agent_card(x, y, w, h, name, tag, src, out, human, ac=BLUE):
        flat(sl, x, y, w, h, fill=TINT, accent=ac)
        write(sl, x + 0.38, y + 0.3, w - 0.7, 0.4,
              [(name, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        pill(sl, x + 0.38, y + 0.82, 1.55, 0.34, tag, fill=WHITE, color=BLUE_600, size=T_NOTE)
        rows_ = [("입력", src), ("출력", out), ("사람 확인", human)]
        for j, (k, v) in enumerate(rows_):
            yy = y + 1.35 + j * 0.78
            write(sl, x + 0.38, yy, 1.3, 0.3,
                  [(k, dict(size=T_NOTE, weight=600, color=MUTED, line=1.25))])
            write(sl, x + 0.38, yy + 0.28, w - 0.7, 0.5,
                  [(v, dict(size=T_BODY, weight=(600 if j == 2 else 400),
                            color=(BLUE_DEEP if j == 2 else SUB), line=1.35))])

    agent_card(xs2[0], top, w2, 3.85, "미팅분석", "판단 생성", "미팅 원문",
               "딜별 귀속 · 13개 특성 · 성사 확률", "확정할 때 저장된다", BLUE)
    agent_card(xs2[1], top, w2, 3.85, "영업 · 계약관리", "상태 허브", "위험 신호 7종 · 이력",
               "다음 미팅 제안 · 근거 브리핑", "캘린더 승인", BLUE_LIGHT)

    # ========================= 26 에이전트 상세 ② =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="실행을 돕는 세 에이전트",
                    subtitle="보고서 작성 · 일정관리 · 자료요약",
                    source="출처: backend/app/agents/ (develop, 2026-09-17)")
    w3, xs = grid(3, 0.36)
    agent_card(xs[0], top, w3, 3.85, "보고서 작성", "실행 지원", "원문 · 하위 확정 보고서",
               "작성 → 검토 → 수정 초안", "확정 · 팀장 검토", BLUE)
    agent_card(xs[1], top, w3, 3.85, "일정관리", "실행 지원", "저장된 추천 · 딜 상태",
               "유효 / 재생성 / 무시 판단", "승인 · 거절", BLUE_LIGHT)
    agent_card(xs[2], top, w3, 3.85, "자료요약", "실행 지원", "PDF · DOCX · 이미지",
               "구조화 요약 · RAG 청크", "원문 대조", BLUE_PALE)

    # ========================= 27 Agent Flow =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="트리거와 작업 큐로 잇고, 사람이 닫는다",
                    subtitle="트리거 → agent_run 큐(PostgreSQL) → 에이전트 → 사람 → 다시 트리거",
                    source="출처: backend/app/services/agent_runs.py · agent_worker.py")
    w4, xs = grid(4, 0.28)
    cols = [("업무 트리거", ["자료 업로드", "미팅 보고서 생성", "보고서 확정", "일정 등록", "딜 단계 이동 외 3건"], GRAY, SUB),
            ("작업 큐", ["agent_run 큐", "부모 · 자식 실행", "재시도 최대 2회", "lease 90초"], TINT, SUB),
            ("에이전트", ["미팅 내용분석", "보고서 작성", "딜 특성 + ML 예측", "계약관리 → 일정관리", "브리핑 · 자료요약"], TINT2, INK),
            ("사람", ["보고서 확정", "추천 승인 · 일정 등록", "팀장 검토 · 반려"], TINT, SUB)]
    ch_h = 4.0
    for i, (lb, items, fc, tc) in enumerate(cols):
        x = xs[i]
        flat(sl, x, top, w4, ch_h, fill=fc, accent=(BLUE if i == 2 else None))
        write(sl, x + 0.26, top + 0.24, w4 - 0.5, 0.36,
              [(lb, dict(size=19, weight=700, color=(BLUE_DEEP if i == 2 else INK), line=1.25))])
        line(sl, x + 0.26, top + 0.72, x + w4 - 0.26, top + 0.72, color=BORDER)
        yy = top + 0.9
        for t in items:
            _bar(sl, x + 0.26, yy + 0.11, 0.08, 0.08, BLUE_LIGHT)
            write(sl, x + 0.46, yy, w4 - 0.66, 0.72,
                  [(t, dict(size=T_BODY, weight=(600 if i == 2 else 400), color=tc, line=1.3))])
            yy += 0.62
        if i < 3:
            arrow(sl, x + w4 + 0.04, top + ch_h / 2, x + w4 + 0.24, top + ch_h / 2,
                  color=BLUE_LIGHT, width=2)

    # ========================= 28 Supervisor 없음 =========================
    sl, top = slide(prs, p(), chapter=CH2, headline="전역 LLM Supervisor는 없다",
                    subtitle="에이전트를 지휘하는 또 하나의 LLM을 두지 않았다",
                    source="출처: backend/app/services/agent_runs.py · agent_worker.py")
    w3, xs = grid(3, 0.36)
    mech = [("무엇으로 잇는가", "agent_run 큐\n코드 dispatch\nAPI 트리거"),
            ("큐 규칙", "부모 · 자식 실행 구조\n재시도 최대 2회\nlease 90초"),
            ("DeepAgents 범위", "보고서 작성 내부에서만\n사용한다\n\n전체 조율에는 쓰지 않는다")]
    for i, (t, d) in enumerate(mech):
        flat(sl, xs[i], top, w3, 3.1, fill=(TINT2 if i == 2 else TINT), accent=(BLUE if i == 2 else None))
        write(sl, xs[i] + 0.38, top + 0.34, w3 - 0.7, 0.4,
              [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        lines = [(s, dict(size=T_BODY, weight=400, color=SUB, line=1.5,
                          spacing_before=(0 if j == 0 else 2))) for j, s in enumerate(d.split("\n"))]
        write(sl, xs[i] + 0.38, top + 1.0, w3 - 0.7, 2.0, lines)
    keyline(sl, top + 3.3, "연결은 큐와 코드로 — 판단은 에이전트가, 확정은 사람이 한다")

    # ========================= 29 파트 디바이더 3 =========================
    divider(prs, "03", "검증과 확장", "제대로 동작하는지 어떻게 확인했는가", p())

    # ---------- 공통 헬퍼 ----------
    def kpi_row(sl, y, items, *, featured=None, h=1.78):
        n = len(items)
        w_, xs_ = grid(n, 0.3)
        for i, (v, lb, sb) in enumerate(items):
            flat(sl, xs_[i], y, w_, h, fill=(TINT2 if featured == i else TINT),
                 accent=(BLUE if featured == i else None))
            kpi(sl, xs_[i] + 0.34, y + 0.26, w_ - 0.68, v, lb, sb,
                color=(BLUE if featured == i else INK))
        return w_, xs_

    def limit_cards(sl, y, items, *, h=2.9):
        w_, xs_ = grid(len(items), 0.36)
        for i, (t, d) in enumerate(items):
            flat(sl, xs_[i], y, w_, h, fill=GRAY)
            write(sl, xs_[i] + 0.34, y + 0.3, w_ - 0.66, 0.4,
                  [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
            lines = [(s, dict(size=T_BODY, weight=400, color=SUB, line=1.45,
                              spacing_before=(0 if j == 0 else 2))) for j, s in enumerate(d.split("\n"))]
            write(sl, xs_[i] + 0.34, y + 0.92, w_ - 0.66, h - 1.0, lines)

    # ========================= 30 평가 개요 =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="에이전트마다 다른 방법으로 검증했다",
                    subtitle="정답표 대조 · LLM Judge · 자동 골든셋 · 처리 시간 측정",
                    source="출처: docs/eval · output/evals (develop, 2026-09-17)")
    rows_ = [("미팅분석", "합성 골든셋 정답표 대조 + 딜 승산 ML 30회 반복"),
             ("보고서 작성", "합성 53건 LLM Judge 절대 평가 + 개선 전후 쌍대 비교"),
             ("자료요약 · RAG", "합성 문서 7개 · QRA 자동 골든셋 10건 LLM Judge"),
             ("OCR", "유형별 정답표 대조 + RunPod 웜 스타트 처리 시간"),
             ("영업 · 계약관리 / 일정관리", "[평가 방법 입력 예정]")]
    for i, (t, d) in enumerate(rows_):
        y = top + i * 0.78
        done = i < 4
        flat(sl, M, y, CW, 0.66, fill=(TINT if done else GRAY),
             accent=(BLUE_LIGHT if done else None))
        write(sl, M + 0.36, y + 0.16, 4.4, 0.36,
              [(t, dict(size=T_CARD, weight=700, color=(INK if done else MUTED), line=1.25))])
        write(sl, M + 5.0, y + 0.18, CW - 5.35, 0.36,
              [(d, dict(size=T_BODY, weight=400, color=(SUB if done else MUTED), line=1.3))])

    # ========================= 31 미팅분석 ① =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="딜 귀속 84.7%, 특성 추출 74.8%가 다음 과제",
                    subtitle="합성 골든셋 정답표와 대조한 결과",
                    source="출처: 미팅 내용분석 구조 보고서 (2026-08-31 골든셋 · 과거 코드 기준)")
    kpi_row(sl, top, [("84.7%", "근거 · 딜 일치", "94 / 111 구간"),
                      ("74.8%", "딜 특성 필드 정확도", "350 / 468 필드"),
                      ("82.6%", "필수 사실 보존", "38 / 46"),
                      ("0 / 36", "13개 특성 전부 정답", "가장 큰 과제")], featured=3)
    label(sl, M, top + 2.02, "평가 방법")
    bullets(sl, M, top + 2.46, CW, ["합성 미팅 12회 · 딜 36개로 만든 골든셋 (2026-08-31)",
                                   "AI가 의미를 검수한 결과이며 사람 판정이 아니다"], gap=0.5)
    keyline(sl, top + 3.5, "13개 특성을 한 건도 빠짐없이 맞춘 사례는 36건 중 0건 — 가장 먼저 개선할 지점")

    # ========================= 32 미팅분석 ② =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="딜 승산 모델은 Stacking으로 AUC 0.778까지 올랐다",
                    subtitle="공개 영문 B2B 데이터 448건 · 30회 반복 평균",
                    source="출처: 머신러닝 · 딥러닝 학습결과서 (30회 평균)")
    cwid = 8.0
    label(sl, M, top, "단계별 성능 (30회 평균)")
    add_chart(sl, COL, M - 0.2, top + 0.4, cwid, 3.2,
              ["RF 기준선", "RF 튜닝", "Stacking_LR (최종)"],
              [("Accuracy", [0.6958, 0.7338, 0.7360]), ("ROC-AUC", [0.7409, 0.7756, 0.7783])],
              label_fmt="0.000", gap=80, y_min=0.6, y_max=0.84, colors=(BLUE_PALE, BLUE),
              axis_size=T_NOTE, label_size=T_NOTE)
    rx = M + cwid + 0.5
    rw = CW - cwid - 0.5
    kpi(sl, rx, top, rw, "+0.037", "ROC-AUC 상승폭", "0.7409 → 0.7783", tint=True, h=1.72)
    kpi(sl, rx, top + 1.85, rw, "0.1880", "Brier 점수", "0.2097 → 0.1880 (낮을수록 좋음)",
        color=BLUE_500, tint=True, h=1.82)

    # ========================= 33 미팅분석 ③ =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="이 수치를 읽을 때 유의할 점",
                    subtitle="미팅분석 평가의 한계",
                    source="출처: 미팅 내용분석 구조 보고서 · 머신러닝 · 딥러닝 학습결과서")
    limit_cards(sl, top, [("합성 데이터", "합성 미팅 12회 · 딜 36개\n2026-08-31 골든셋\n과거 코드 기준"),
                          ("사람 판정 아님", "AI가 의미를 검수했다\n사람 평가자가\n채점한 결과가 아니다"),
                          ("영문 공개 데이터", "딜 승산 ML은\n공개 영문 B2B 448건 기준\n한국어 실제 성능은 별도")], h=3.2)
    keyline(sl, top + 3.4, "실제 한국어 영업 데이터에서의 성능은 아직 측정하지 않았다")

    # ========================= 34 보고서 ① =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="구조를 바꾸자 53건 모두 생성, 토큰은 54% 감소",
                    subtitle="합성 53건 · LLM Judge 절대 평가와 쌍대 비교",
                    source="출처: docs/eval/01_보고서작성에이전트 (Judge gpt-5.6-luna, 2026-09-08)")
    kpi_row(sl, top, [("47 → 53", "유효 답안", "53건 중"),
                      ("18 → 0", "외부 재시도", "생성 실패 6 → 0"),
                      ("−54.4%", "생성 토큰", "1,001만 → 457만"),
                      ("29 / 47", "쌍대 우세", "개선 전 우세 1건")], featured=2)
    label(sl, M, top + 2.02, "평가 방법")
    bullets(sl, M, top + 2.46, CW, ["루브릭 5개로 절대 채점하고, 순서를 익명 교차해 쌍대 비교했다",
                                   "인용은 기계로 검증하고, 기간 보고서는 하위 확정본을 참조했다"], gap=0.5)
    keyline(sl, top + 3.5, "실패하던 6건이 사라지고, 같은 결과를 절반 이하의 토큰으로 만든다")

    # ========================= 35 보고서 ② =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="주간 · 월간 보고서 점수가 가장 크게 올랐다",
                    subtitle="LLM Judge 100점 만점 · 공통 43건",
                    source="출처: docs/eval/01_보고서작성에이전트 (Judge gpt-5.6-luna, 2026-09-08)")
    cwid = 8.0
    label(sl, M, top, "보고서 유형별 점수")
    add_chart(sl, COL, M - 0.2, top + 0.4, cwid, 3.2, ["미팅", "일일", "주간", "월간"],
              [("개선 전", [97.74, 86.88, 72.50, 66.25]), ("개선 후", [96.57, 95.16, 87.08, 76.25])],
              label_fmt="0.0", gap=70, y_min=60, y_max=108, colors=(BLUE_PALE, BLUE),
              axis_size=T_NOTE, label_size=T_NOTE)
    rx = M + cwid + 0.5
    rw = CW - cwid - 0.5
    kpi(sl, rx, top, rw, "+14.6", "주간 보고서 상승", "72.50 → 87.08", tint=True, h=1.72)
    kpi(sl, rx, top + 1.85, rw, "−1.2", "미팅 보고서 하락", "97.74 → 96.57",
        color=MUTED, tint=True, h=1.82)

    # ========================= 36 보고서 ③ =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="이 수치를 읽을 때 유의할 점",
                    subtitle="보고서 작성 평가의 한계",
                    source="출처: docs/eval/01_보고서작성에이전트 (2026-09-08)")
    limit_cards(sl, top, [("표본이 작다", "시나리오 1개\n월간 보고서는 1건뿐"),
                          ("같은 모델이 채점", "생성 모델과 Judge 모델이\n동일하다\n(gpt-5.6-luna)"),
                          ("떨어진 지표도 있다", "미팅 보고서 점수 하락\n사실 정확성 3.84 → 3.74")], h=3.2)
    keyline(sl, top + 3.4, "개선은 기간 보고서에 집중되었고, 미팅 보고서의 사실 정확성은 오히려 떨어졌다")

    # ========================= 37 영업 · 계약관리 (레이아웃) =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="[영업 · 계약관리 평가 결론 입력 예정]",
                    subtitle="[평가 방법 한 줄 입력 예정]")
    w4, xs = grid(4, 0.3)
    for i in range(4):
        placeholder(sl, xs[i], top, w4, 1.5, "[지표 입력 예정]")
    placeholder(sl, M, top + 1.75, 8.0, 2.3, "[차트 또는 평가 도식 입력 예정]")
    placeholder(sl, M + 8.3, top + 1.75, CW - 8.3, 2.3, "[평가 데이터 · 방법 · 한계 입력 예정]")

    # ========================= 38 일정관리 (레이아웃) =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="[일정관리 평가 결론 입력 예정]",
                    subtitle="[평가 방법 한 줄 입력 예정]")
    w3, xs = grid(3, 0.36)
    for i in range(3):
        placeholder(sl, xs[i], top, w3, 1.5, "[지표 입력 예정]")
    w2, xs2 = grid(2, 0.5)
    placeholder(sl, xs2[0], top + 1.75, w2, 2.3, "Before — [개선 전 동작 입력 예정]")
    placeholder(sl, xs2[1], top + 1.75, w2, 2.3, "After — [개선 후 동작 입력 예정]")

    # ========================= 39 문서요약 ① =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="문서요약 자동 평가 종합 점수는 0.846이다",
                    subtitle="0–1 · 높을수록 좋음",
                    source="출처: docs/document-summary-evaluation.md · output/evals/document-summary-rageval")
    cwid = 8.6
    label(sl, M, top, "지표별 점수")
    add_chart(sl, BAR, M - 0.15, top + 0.4, cwid, 3.55,
              ["overall", "completeness", "groundedness", "hallucination",
               "retrieval_relevance", "irrelevance"],
              [("점수", [0.846, 0.828, 0.914, 0.942, 0.892, 0.901])],
              label_fmt="0.000", gap=55, y_min=0.0, y_max=1.0,
              axis_size=T_NOTE, label_size=T_NOTE)
    rx = M + cwid + 0.5
    rw = CW - cwid - 0.5
    kpi(sl, rx, top, rw, "0.846", "overall", "자동 골든셋 10건 종합", tint=True, h=1.72)
    kpi(sl, rx, top + 1.85, rw, "0.828", "completeness", "가장 낮은 지표",
        color=BLUE_500, tint=True, h=1.82)

    # ========================= 40 문서요약 ② =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="합성 문서에서 골든셋을 만들어 자동 채점했다",
                    subtitle="사람 검수는 아직 남아 있다",
                    source="출처: docs/document-summary-evaluation.md")
    lw = 6.6
    label(sl, M, top, "평가 흐름", w=lw)
    steps = [("01", "합성 문서 7개"), ("02", "QRA 자동 골든셋 10건"), ("03", "요약 6 · 검색 4 LLM Judge 채점")]
    for i, (n, t) in enumerate(steps):
        y = top + 0.5 + i * 1.0
        flat(sl, M, y, lw, 0.8, fill=TINT, accent=(BLUE if i == 2 else None))
        write(sl, M + 0.34, y + 0.2, 0.7, 0.4, [(n, dict(size=T_CARD, weight=700, color=BLUE, line=1.2))])
        write(sl, M + 1.1, y + 0.22, lw - 1.4, 0.4,
              [(t, dict(size=T_BODY, weight=500, color=INK, line=1.3))])
        if i < 2:
            arrow(sl, M + lw / 2, y + 0.83, M + lw / 2, y + 0.97, color=BLUE_LIGHT, width=2)
    rx = M + lw + 0.6
    rw = CW - lw - 0.6
    label(sl, rx, top, "읽을 때 주의", w=rw, color=MUTED)
    flat(sl, rx, top + 0.5, rw, 2.8, fill=GRAY)
    bullets(sl, rx + 0.34, top + 0.82, rw - 0.68,
            ["요약 6건은 0.91–0.98 구간", "사람 검수는 pending 상태", "모두 합성 문서 기준 결과"],
            gap=0.72, marker=MUTED)

    # ========================= 41 OCR ① =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="명함 · PDF는 필드 100%, 사업자등록증은 80%",
                    subtitle="유형별 정답표와 대조한 결과",
                    source="출처: 자료요약 OCR 평가표 (유형별 1건 소표본)")
    kpi_row(sl, top, [("7 / 7", "명함 필드", "구조화 6 / 6"),
                      ("100%", "취업규칙 PDF 35쪽", "장 제목 12 / 12"),
                      ("12 / 15", "사업자등록증 필드", "80% · 3개 불일치")], featured=2)
    label(sl, M, top + 2.02, "틀린 필드와 대응")
    bullets(sl, M, top + 2.46, CW,
            ["법인등록번호 · 법인명 · 개업연월일이 정답과 어긋났다",
             "이 세 필드는 자동 승인에서 제외하고 사용자가 검토한다"], gap=0.5)
    keyline(sl, top + 3.5, "유형별 1건씩만 확인한 결과이므로 전체 정확도가 아니다")

    # ========================= 42 OCR ② =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="웜 스타트에서는 2초 안에 끝난다",
                    subtitle="RunPod PaddleOCR · 각 5회 측정",
                    source="출처: RunPod OCR 워커 계약 문서")
    cwid = 6.8
    label(sl, M, top, "평균 처리 시간 (초)")
    add_chart(sl, COL, M - 0.2, top + 0.4, cwid, 3.1, ["명함 이미지", "PDF 문서"],
              [("평균 처리 시간(초)", [2.24, 1.23])], label_fmt="0.00", gap=140, y_max=3.0,
              axis_size=T_NOTE, label_size=T_NOTE)
    rx = M + cwid + 0.5
    rw = CW - cwid - 0.5
    label(sl, rx, top, "남은 과제", w=rw, color=MUTED)
    flat(sl, rx, top + 0.5, rw, 3.0, fill=GRAY)
    bullets(sl, rx + 0.34, top + 0.85, rw - 0.68,
            ["손글씨 문자 오류율 45%", "별도 과제로 분리했다", "유형별 1건 소표본"],
            gap=0.8, marker=MUTED)

    # ========================= 43 RAG ① =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="요약은 고르게 높지만 검색 답변은 편차가 크다",
                    subtitle="케이스별 overall 점수 (0–1)",
                    source="출처: output/evals/document-summary-rageval/llm_judge_results.json")
    label(sl, M, top, "요약 6건 · 검색 4건")
    add_chart(sl, COL, M - 0.2, top + 0.35, CW + 0.4, 3.0,
              ["요약1", "요약2", "요약3", "요약4", "요약5", "요약6", "검색1", "검색2", "검색3", "검색4"],
              [("overall", [0.97, 0.91, 0.96, 0.98, 0.93, 0.96, 0.25, 0.78, 0.90, 0.82])],
              label_fmt="0.00", gap=45, y_max=1.05, axis_size=T_NOTE, label_size=T_NOTE)
    keyline(sl, top + 3.5, "검색1 한 건이 0.25 — 최신 자료 대신 옛 계약서를 참조했다")

    # ========================= 44 RAG ② =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="RAG 답변 4건 중 1건은 옛 계약서 날짜를 답했다",
                    subtitle="실패 사례 — 검색1 (overall 0.25)",
                    source="출처: output/evals/document-summary-rageval/llm_judge_results.json")
    lw = 7.0
    flat(sl, M, top, lw, 3.3, fill=TINT2, accent=BLUE)
    write(sl, M + 0.4, top + 0.32, lw - 0.8, 0.4,
          [("검색1 — overall 0.25", dict(size=T_CARD, weight=700, color=BLUE_DEEP, line=1.25))])
    for i, (k, v) in enumerate([("질문", "현재 기준 설치 예정일"),
                                ("기대한 답", "2026-10-08 (추가 자료)"),
                                ("실제 답변", "2026-09-24 (기존 계약서)")]):
        y = top + 0.92 + i * 0.66
        write(sl, M + 0.4, y, 1.7, 0.36, [(k, dict(size=T_NOTE, weight=600, color=MUTED, line=1.25))])
        write(sl, M + 2.2, y - 0.04, lw - 2.6, 0.4,
              [(v, dict(size=T_BODY, weight=500, color=INK, line=1.3))])
    write(sl, M + 0.4, top + 2.8, lw - 0.8, 0.4,
          [("→ 최신 자료 대신 옛 계약서를 참조했다",
            dict(size=T_BODY, weight=600, color=BLUE, line=1.3))])
    rx = M + lw + 0.6
    rw = CW - lw - 0.6
    label(sl, rx, top, "읽을 때 주의", w=rw, color=MUTED)
    flat(sl, rx, top + 0.5, rw, 3.3, fill=GRAY)
    bullets(sl, rx + 0.34, top + 0.82, rw - 0.68,
            ["평가 스크립트의 검색은 단어 겹침 방식이다",
             "운영은 키워드 + pgvector를 RRF로 병합하는 하이브리드 검색이다",
             "보고서 RAG · 브리핑 근거는 별도 품질 평가가 없다"],
            gap=0.98, marker=MUTED)

    # ========================= 45 실패와 개선 ① =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="[실패와 개선 사례 1 결론 입력 예정]",
                    subtitle="[사례 1 한 줄 요약 입력 예정]")
    w4, xs = grid(4, 0.3)
    for i, lb in enumerate(["처음 접근", "무엇이 문제였나", "어떻게 바꿨나", "결과"]):
        write(sl, xs[i], top, w4, 0.36, [(lb, dict(size=19, weight=700, color=BLUE_600, line=1.25))])
        placeholder(sl, xs[i], top + 0.5, w4, 3.4, PH)

    # ========================= 46 실패와 개선 ② =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="[실패와 개선 사례 2 결론 입력 예정]",
                    subtitle="[사례 2 한 줄 요약 입력 예정]")
    for i, lb in enumerate(["처음 접근", "무엇이 문제였나", "어떻게 바꿨나", "결과"]):
        write(sl, xs[i], top, w4, 0.36, [(lb, dict(size=19, weight=700, color=BLUE_600, line=1.25))])
        placeholder(sl, xs[i], top + 0.5, w4, 3.4, PH)

    # ========================= 47 보완점 =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="[보완점 결론 입력 예정]",
                    subtitle="[부제 입력 예정]")
    w3, xs = grid(3, 0.36)
    for i in range(3):
        write(sl, xs[i], top, w3, 0.36,
              [("한계 %d" % (i + 1), dict(size=19, weight=700, color=BLUE_600, line=1.25))])
        placeholder(sl, xs[i], top + 0.5, w3, 2.6, "[영역 · 내용 · 영향 입력 예정]")
    placeholder(sl, M, top + 3.3, CW, 0.75, "[한 줄 정리 입력 예정]")

    # ========================= 48 향후 계획 =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="[향후 계획 결론 입력 예정]",
                    subtitle="[부제 입력 예정]")
    for i, lb in enumerate(["단기", "중기", "장기"]):
        x = xs[i]
        flat(sl, x, top, w3, 0.68, fill=(TINT2 if i == 0 else TINT), accent=(BLUE if i == 0 else None))
        write(sl, x + 0.34, top + 0.17, w3 - 0.6, 0.4,
              [(lb + " 계획", dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        placeholder(sl, x, top + 0.86, w3, 3.05, PH)

    # ========================= 49 결론 ① =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="담당자의 머릿속을 조직의 기록으로 남긴다",
                    subtitle="인수인계 질문 11개 영역 = 데이터 (1 / 2)",
                    source="출처: SalesLuv 데이터 구조(develop, 2026-09-17)")
    areas1 = [("고객 관계 맥락", "회사 · 담당자 · 부서"),
              ("접점 히스토리", "일정 · 활동 · 보고서"),
              ("고객의 실제 발언", "원문 · STT · 첨부"),
              ("발언의 대상 · 범위", "공통 · 딜별 + 근거 ID"),
              ("구매 판단 신호", "권한 · 경쟁사 등 13개 특성"),
              ("딜 진행 맥락", "단계 · 금액 · 계약 · 납기")]
    for i, (t, d) in enumerate(areas1):
        x = xs[i % 3]
        y = top + (i // 3) * 1.85
        flat(sl, x, y, w3, 1.6, fill=TINT)
        write(sl, x + 0.34, y + 0.3, w3 - 0.66, 0.4,
              [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        write(sl, x + 0.34, y + 0.88, w3 - 0.66, 0.6,
              [(d, dict(size=T_BODY, weight=400, color=SUB, line=1.4))])

    # ========================= 50 결론 ② =========================
    sl, top = slide(prs, p(), chapter=CH3, headline="기록이 남으면 사람이 바뀌어도 맥락은 남는다",
                    subtitle="인수인계 질문 11개 영역 = 데이터 (2 / 2)",
                    source="출처: SalesLuv 데이터 구조(develop, 2026-09-17)")
    areas2 = [("과거 맥락", "이전 확정 보고서"),
              ("이슈 · 불만 맥락", "불만 · 긴급도 · 처리"),
              ("위험과 다음 행동", "만료 · 지연 · 추천"),
              ("문서 지식", "원문 추출 · 요약 · RAG"),
              ("판단의 책임 · 이력", "작성자 · revision · 승인")]
    for i, (t, d) in enumerate(areas2):
        x = xs[i % 3]
        y = top + (i // 3) * 1.85
        flat(sl, x, y, w3, 1.6, fill=TINT)
        write(sl, x + 0.34, y + 0.3, w3 - 0.66, 0.4,
              [(t, dict(size=T_CARD, weight=700, color=INK, line=1.25))])
        write(sl, x + 0.34, y + 0.88, w3 - 0.66, 0.6,
              [(d, dict(size=T_BODY, weight=400, color=SUB, line=1.4))])
    gy = top + 1.85
    flat(sl, xs[2], gy, w3, 1.6, fill=DARK)
    write(sl, xs[2] + 0.34, gy + 0.34, w3 - 0.66, 1.0,
          [("AI는 구조화 · 요약 · 제안까지", dict(size=T_BODY, weight=700, color=WHITE, line=1.4)),
           ("확정은 사람의 승인으로", dict(size=T_BODY, weight=700, color=BLUE_LIGHT, line=1.4,
                                  spacing_before=6))])

    # ========================= 51 Q&A =========================
    sl = blank(prs, dark=True)
    sl.shapes.add_picture(LOGO_WHITE, Inches(SW - M - LOGO_W), Inches(EYE_Y - 0.02),
                          Inches(LOGO_W), Inches(LOGO_H))
    write(sl, M, 2.9, CW, 1.3, [("Q & A", dict(size=64, weight=700, color=WHITE, line=1.15))], align=C)
    _bar(sl, SW / 2 - 1.0, 4.45, 2.0, 0.075, BLUE)
    write(sl, M, 4.8, CW, 0.6,
          [("감사합니다 · Thank You", dict(size=21, weight=500, color=DARK_SUB, line=1.4))], align=C)
    write(sl, SW - M - 1.0, 6.83, 1.0, 0.3,
          [("%02d" % p(), dict(size=16, weight=600, color=SUB, line=1.25))], align=R)

    # ========================= 52 부록 ERD =========================
    sl, top = slide(prs, p(), chapter=APX, headline="모든 데이터는 딜을 중심으로 연결된다",
                    source="출처: backend/app/models/ (develop, 2026-09-17)")
    gw = 3.75
    gxs = [M, M + 4.17, M + 8.34]
    top_y, bot_y = top, top + 3.0
    gh = 1.6
    hub_w, hub_h = 3.4, 0.95
    hub_x, hub_y = SW / 2 - hub_w / 2, top + 1.78
    groups = [("조직 · 권한", "team · member", gxs[0], top_y),
              ("고객", "customer_company\ncustomer_contact", gxs[1], top_y),
              ("영업 실행", "sales_pipeline(+stage)\nproduct · sales_deal_item\npurchase_order(+item)",
               gxs[2], top_y),
              ("활동 · 보고", "activity · report\nreport_deal · report_submission", gxs[0], bot_y),
              ("AI 실행", "agent_run\ncontract_next_meeting_suggestion", gxs[1], bot_y),
              ("문서 · C/S", "document · file\ndocument_chunk · support_request", gxs[2], bot_y)]
    bus = hub_y + hub_h / 2
    line(sl, gxs[0] + gw / 2, top_y + gh, gxs[0] + gw / 2, bot_y, color=BLUE_PALE, width=1.5)
    line(sl, gxs[2] + gw / 2, top_y + gh, gxs[2] + gw / 2, bot_y, color=BLUE_PALE, width=1.5)
    line(sl, gxs[0] + gw / 2, bus, hub_x, bus, color=BLUE_PALE, width=1.5)
    line(sl, hub_x + hub_w, bus, gxs[2] + gw / 2, bus, color=BLUE_PALE, width=1.5)
    line(sl, gxs[1] + gw / 2, top_y + gh, gxs[1] + gw / 2, hub_y, color=BLUE_PALE, width=1.5)
    line(sl, gxs[1] + gw / 2, hub_y + hub_h, gxs[1] + gw / 2, bot_y, color=BLUE_PALE, width=1.5)
    hub = card(sl, hub_x, hub_y, hub_w, hub_h, fill=BLUE, shadow=False, radius=0.12)
    tf = hub.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, "sales_deal", size=T_CARD, weight=700, color=WHITE, line=1.2, align=C, first=True)
    para(tf, "영업 딜", size=T_NOTE, weight=400, color=BLUE_PALE, line=1.3, align=C)
    for lb, items, x, y in groups:
        flat(sl, x, y, gw, gh, fill=TINT)
        write(sl, x + 0.28, y + 0.2, gw - 0.55, 0.34,
              [(lb, dict(size=17, weight=700, color=BLUE_600, line=1.25))])
        lines = [(t, dict(size=T_NOTE, weight=400, color=SUB, line=1.4,
                          spacing_before=(0 if j == 0 else 2))) for j, t in enumerate(items.split("\n"))]
        write(sl, x + 0.28, y + 0.66, gw - 0.55, 0.7, lines)

    # ========================= 53 부록 WBS =========================
    sl, top = slide(prs, p(), chapter=APX, headline="7주 동안 기획에서 배포 검증까지 진행했다",
                    subtitle="주차별 주요 작업", source="출처: 프로젝트 WBS")
    weeks = [("1주", "요구사항 분석\n기획"), ("2주", "DB 기반 구축\n화면 설계"),
             ("3주", "FE · BE 개발\n중간 발표"), ("4주", "데이터 전처리\nAI 모델링"),
             ("5주", "모델 평가\n기능 통합"), ("6주", "통합 테스트\n배포 검증"),
             ("7주", "산출물 검수\n최종 발표")]
    n = len(weeks)
    w_, xs7 = grid(n, 0.2)
    ry = top + 1.7
    line(sl, M + w_ / 2, ry, M + CW - w_ / 2, ry, color=BORDER, width=2)
    for i, (wk, t) in enumerate(weeks):
        x = xs7[i]
        write(sl, x, ry - 0.75, w_, 0.4, [(wk, dict(size=T_CARD, weight=700, color=INK, line=1.2))],
              align=C)
        circle(sl, x + w_ / 2 - 0.11, ry - 0.11, 0.22, "",
               fill=(BLUE if i >= n - 2 else BLUE_PALE))
        lines = [(s, dict(size=T_BODY, weight=400, color=SUB, line=1.4,
                          spacing_before=(0 if j == 0 else 2))) for j, s in enumerate(t.split("\n"))]
        write(sl, x, ry + 0.35, w_, 1.2, lines, align=C)

    # ========================= 54 부록 ML 상세 =========================
    sl, top = slide(prs, p(), chapter=APX, headline="딜 승산 모델 단계별 성능 상세",
                    subtitle="공개 영문 B2B 448건 · 30회 반복 평균",
                    source="출처: 머신러닝 · 딥러닝 학습결과서")
    rows = [["단계", "Accuracy", "ROC-AUC", "Brier"],
            ["RF 기준선", "0.6958", "0.7409", "0.2097"],
            ["RF 튜닝", "0.7338", "0.7756", "–"],
            ["Stacking_LR (최종)", "0.7360", "0.7783", "0.1880"]]
    table(sl, M, top, CW, 2.8, rows, col_w=[4.2, 2.631, 2.631, 2.631], highlight_row=3)
    note(sl, M, top + 2.95, CW,
         "Brier는 낮을수록 좋다 · RF 튜닝 단계의 Brier 값은 보고서에 기록되지 않았다", size=16)

    # ========================= 55 부록 보고서 Judge 상세 =========================
    sl, top = slide(prs, p(), chapter=APX, headline="보고서 유형별 LLM Judge 점수 상세",
                    subtitle="100점 만점 · 공통 43건 · Judge gpt-5.6-luna",
                    source="출처: docs/eval/01_보고서작성에이전트 (2026-09-08)")
    rows = [["보고서 유형", "개선 전", "개선 후"],
            ["미팅 보고서", "97.74", "96.57"],
            ["일일 업무보고", "86.88", "95.16"],
            ["주간 업무보고", "72.50", "87.08"],
            ["월간 업무보고", "66.25", "76.25"]]
    table(sl, M, top, CW, 3.4, rows, col_w=[5.0, 3.546, 3.547], highlight_col=2)
    note(sl, M, top + 3.55, CW,
         "생성 모델과 Judge 모델이 동일하며 시나리오는 1개, 월간 보고서는 1건이다", size=16)

    # ========================= 56 부록 출처 일람 =========================
    sl, top = slide(prs, p(), chapter=APX, headline="본문에 쓰인 근거 자료",
                    subtitle="모든 수치의 출처")
    w2, xs2 = grid(2, 0.6)
    srcs = [["프로젝트 기획서 (2026-08)",
             "Grand View Research (2026)",
             "KISDI 2026 · 원자료 Gartner 2025",
             "환율 2026-09-15 기준 1,347.8원",
             "각 사 공식 제품 페이지 (2026-09-15 확인)",
             "SalesLuv 구현 코드 (develop, 2026-09-17)"],
            ["미팅 내용분석 구조 보고서 (2026-08-31 골든셋)",
             "머신러닝 · 딥러닝 학습결과서 (30회 평균)",
             "docs/eval/01_보고서작성에이전트 (2026-09-08)",
             "docs/document-summary-evaluation.md",
             "output/evals/document-summary-rageval",
             "자료요약 OCR 평가표 · RunPod OCR 워커 계약 문서"]]
    for ci, col in enumerate(srcs):
        bullets(sl, xs2[ci], top + 0.05, w2, col, gap=0.6, size=17)
    note(sl, M, BOT - 0.4, CW,
         "평가용 데이터는 모두 합성 데이터이며 실제 고객 · 영업 데이터를 사용하지 않았다", size=16)

    prs.save(OUT)
    print("saved", OUT, len(prs.slides._sldIdLst), "slides")


if __name__ == "__main__":
    build()
