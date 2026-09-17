"""Create a concise current-state PDF and a 16:9 PPT-ready RAG overview visual.

Sources are limited to the current implementation and the 2026-09-15 evaluation
report.  The report deliberately keeps unapproved LLM-judge outcomes separate
from production acceptance criteria.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf")
NAVY = colors.HexColor("#132238")
BLUE = colors.HexColor("#246BFD")
TEAL = colors.HexColor("#0F9F8B")
INK = colors.HexColor("#344054")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#D7DEE8")
PALE_BLUE = colors.HexColor("#EFF5FF")
PALE_TEAL = colors.HexColor("#ECFDF8")
PALE_AMBER = colors.HexColor("#FFF7E5")


def configure_font() -> str:
    if not FONT_PATH.exists():
        raise RuntimeError(f"Korean font missing: {FONT_PATH}")
    pdfmetrics.registerFont(TTFont("AppleGothic", str(FONT_PATH)))
    return "AppleGothic"


def e(value: object) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName=font, fontSize=22, leading=29, textColor=NAVY, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontName=font, fontSize=9.3, leading=13, textColor=MUTED, spaceAfter=9),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=font, fontSize=14, leading=19, textColor=NAVY, spaceBefore=10, spaceAfter=5),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=font, fontSize=10.5, leading=14, textColor=BLUE, spaceBefore=7, spaceAfter=3),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=font, fontSize=8.8, leading=13.1, textColor=INK, spaceAfter=4, wordWrap="CJK"),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName=font, fontSize=7.1, leading=10, textColor=MUTED, wordWrap="CJK"),
        "card": ParagraphStyle("card", parent=base["BodyText"], fontName=font, fontSize=8.1, leading=11.7, textColor=INK, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontName=font, fontSize=7.45, leading=10.4, textColor=INK, wordWrap="CJK"),
        "head": ParagraphStyle("head", parent=base["BodyText"], fontName=font, fontSize=7.3, leading=10.2, textColor=colors.white, alignment=TA_CENTER, wordWrap="CJK"),
        "metric": ParagraphStyle("metric", parent=base["BodyText"], fontName=font, fontSize=15, leading=18, textColor=NAVY, alignment=TA_CENTER),
        "metric_label": ParagraphStyle("metric_label", parent=base["BodyText"], fontName=font, fontSize=7.5, leading=10, textColor=MUTED, alignment=TA_CENTER, wordWrap="CJK"),
    }


def p(value: object, sty: ParagraphStyle) -> Paragraph:
    return Paragraph(e(value), sty)


class BriefDoc(BaseDocTemplate):
    def __init__(self, path: Path, font: str):
        super().__init__(str(path), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title="문서요약 에이전트·RAG 구축 현황", author="SalesLuv")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="main")
        self.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=self._footer)])
        self.font = font

    def _footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(17 * mm, 10.4 * mm, A4[0] - 17 * mm, 10.4 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont(self.font, 7.2)
        canvas.drawString(17 * mm, 6.5 * mm, "SalesLuv | 문서요약 에이전트·RAG 구축 현황 | 2026-09-17")
        canvas.drawRightString(A4[0] - 17 * mm, 6.5 * mm, str(doc.page))
        canvas.restoreState()


def boxed(items: list[object], *, width: float, bg: colors.Color = colors.white, edge: colors.Color = LINE) -> Table:
    # Put the supplied flowables in one table cell so they stack vertically.
    # A bare ``[items]`` treats them as adjacent columns and clips long copy.
    t = Table([[[*items]]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.55, edge),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def data_table(rows: list[list[object]], widths: list[float], sty: dict[str, ParagraphStyle]) -> Table:
    converted = []
    for row_i, row in enumerate(rows):
        converted.append([item if isinstance(item, Paragraph) else p(item, sty["head"] if row_i == 0 else sty["cell"]) for item in row])
    t = Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5.5), ("RIGHTPADDING", (0, 0), (-1, -1), 5.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    return t


def metric(label: str, value: str, sty: dict[str, ParagraphStyle]) -> Table:
    t = Table([[p(value, sty["metric"])], [p(label, sty["metric_label"])]], colWidths=[41 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white), ("BOX", (0, 0), (-1, -1), 0.55, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def build_pdf(output: Path) -> None:
    font = configure_font()
    sty = styles(font)
    width = 176 * mm
    story: list[object] = [
        p("문서요약 에이전트·RAG 구축 현황", sty["title"]),
        p("현재 구현 기준 쉬운 설명 및 구축 보고서 | 기준일 2026-09-17", sty["subtitle"]),
        HRFlowable(width="100%", thickness=1.4, color=BLUE, spaceAfter=8),
        boxed([p("결론", sty["h2"]), p("[검증] 현재 구조는 문서에서 텍스트를 추출·OCR 보완한 뒤, 구조화 요약과 출처가 남는 검색 청크를 함께 저장합니다. [검증] 검색은 권한·팀·최신 파일·문서 연결 범위를 먼저 제한하고, 키워드와 벡터 결과를 결합합니다. [추론] 다음 우선순위는 문서 유형별 필수 필드와 상품설명서 사양 검색을 보강하는 일입니다.", sty["body"])], width=width, bg=PALE_BLUE, edge=colors.HexColor("#B8D1FF")),
        p("1. 문서요약 에이전트: 문서를 읽어 '정리된 메모'로 만드는 역할", sty["h1"]),
        p("[검증] 에이전트는 원문을 명령으로 실행하지 않고 분석 대상으로만 취급합니다. LLM 출력은 요약, 핵심 포인트, 영업 관련성, 리스크, 구조화 추출 필드, 출처 참조의 6개 묶음입니다. 원문에 없는 정보는 비워 두도록 설계되어 있습니다.", sty["body"]),
        Table([[boxed([p("입력", sty["h2"]), p("원본 파일 → 텍스트 추출\n스캔·이미지형 문서는 OCR 보완", sty["card"])], width=53 * mm, bg=colors.white), boxed([p("정리", sty["h2"]), p("Markdown 원문을 바탕으로\n구조화 JSON 요약 생성", sty["card"])], width=53 * mm, bg=colors.white), boxed([p("저장", sty["h2"]), p("요약·추출값·감사 이력과\nRAG 청크를 함께 보존", sty["card"])], width=53 * mm, bg=colors.white)]], colWidths=[58 * mm, 58 * mm, 58 * mm], hAlign="LEFT", style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3)])),
        p("2. RAG: 답변 전에 관련 원문 근거를 찾아 붙이는 역할", sty["h1"]),
        p("[검증] RAG는 요약 자체가 아니라 Markdown 원문 청크를 검색합니다. 즉, '먼저 문서를 찾아 근거를 붙이고, 그 범위 안에서 답변하게 하는' 구조입니다. 검색 결과에는 파일명, 페이지, 섹션, 청크 번호와 내용이 남아 답변 근거를 추적할 수 있습니다.", sty["body"]),
        data_table([
            ["단계", "현재 구현", "의미"],
            ["1. 청킹", "1,600자 단위 / 200자 중첩. 페이지·섹션 정보를 보존", "긴 문서를 검색 가능한 작은 근거 단위로 전환"],
            ["2. 검색", "키워드 후보 + 설정 시 벡터 유사도 후보를 RRF로 결합", "표현이 달라도 찾을 여지를 늘리고, 점수 스케일 차이를 완화"],
            ["3. 범위 제한", "팀·열람권한·최신 완료 파일·삭제 문서 제외·딜/고객사/제품 연결", "다른 팀·비공개·오래된 자료가 근거에 섞이지 않게 제한"],
            ["4. 답변 문맥", "요약 + 검색 근거를 document_context로 변환", "최종 Agent가 어느 문서에서 왔는지 함께 보도록 전달"],
        ], [27 * mm, 76 * mm, 73 * mm], sty),
        Spacer(1, 5),
        p("[검증] 임베딩 설정 또는 호출이 불가하면 원문·요약 저장을 멈추지 않고 키워드 검색으로 운영을 이어갑니다. 다만 이때 의미 유사 검색은 제공되지 않습니다.", sty["small"]),
        PageBreak(),
        p("구축 보고서: 현재 평가와 실행 우선순위", sty["title"]),
        p("평가 원천: docs/document-summary-evaluation-report.md (2026-09-15) | 평가 기준과 운영 검색은 동일하지 않음", sty["subtitle"]),
        boxed([p("평가 결론", sty["h2"]), p("[검증] 4개 문서 유형 각 3개, 총 12문서에서 요약 12건과 RAG 질의 12건을 평가했습니다. 재실행 LLM Judge Overall은 0.7600이며, RAG 검색 문맥이 비어 있는 케이스는 5건에서 0건으로 줄었습니다. [검증] 사람검수 상태는 pending이고 사전 합격 기준도 없으므로, 이 점수는 운영 합격률이 아닙니다.", sty["body"])], width=width, bg=PALE_AMBER, edge=colors.HexColor("#F4D28D")),
        Spacer(1, 7),
        Table([[metric("LLM Judge Overall", "0.7600", sty), metric("Completeness", "0.7421", sty), metric("Groundedness", "0.8325", sty), metric("Retrieval relevance", "0.8671", sty)]], colWidths=[44 * mm, 44 * mm, 44 * mm, 44 * mm], style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("VALIGN", (0, 0), (-1, -1), "TOP")])),
        Spacer(1, 6),
        p("[검증] 위 수치는 2026-09-15 평가 보고서의 LLM-as-a-Judge 결과입니다. Judge 점수의 해석은 사람검수 및 서비스 조건과 분리해야 합니다.", sty["small"]),
        p("유형별 관측 결과", sty["h1"]),
        data_table([
            ["문서 유형", "요약 Overall", "RAG Overall", "관측된 판단"],
            ["견적서", "0.9233", "1.0000", "[검증] 해당 3개 샘플에서는 상대적으로 안정적"],
            ["계약서", "0.3400", "1.0000", "[검증] 요약에서 당사자·일자·금액 누락/의미 혼동이 관측됨"],
            ["발주서", "0.6400", "0.8500", "[검증] 발주자·공급자·납품·지급 조건의 보존 점검 필요"],
            ["상품설명서", "0.8767", "0.4500", "[검증] 사양·Intended Use·수치 조건 검색/답변 누락 관측"],
        ], [31 * mm, 31 * mm, 29 * mm, 85 * mm], sty),
        p("실행안", sty["h1"]),
        data_table([
            ["우선", "담당 단위", "실행", "측정 / 실패 판정"],
            ["1", "요약 Agent", "[추론] 계약서의 당사자·대표·작성/공급일·총액·계약금·잔금을 유형별 필수 스키마로 분리", "필수 필드 보존 여부 / [미확인] 허용 누락 기준 필요"],
            ["2", "요약 Agent", "[추론] 발주자·공급자·납품장소·지급조건을 역할 기반 필드로 강제", "역할 뒤바뀜·누락 건수 / [미확인] 허용 기준 필요"],
            ["3", "Retriever", "[추론] 상품설명서 사양표·용도·수치 조건을 우선 검색하도록 청킹/질의 설계 보완", "Completeness·Groundedness / [미확인] 목표 기준 필요"],
            ["4", "평가 운영", "[추론] 사람검수 골든셋 확정 후 Judge와 사람 판정 불일치 기록", "불일치율 / [미확인] 허용 기준 필요"],
        ], [12 * mm, 29 * mm, 81 * mm, 54 * mm], sty),
        p("리스크와 폐기 조건", sty["h1"]),
        boxed([p("[검증] 표본은 유형별 3개라 전체 문서군으로 일반화할 수 없습니다. [검증] 상품설명서 전용 정답지는 없어 기준값의 사람검수가 필요합니다. [검증] 평가기의 검색은 로컬 키워드 검색으로, 운영의 벡터·하이브리드 설정과 같지 않을 수 있습니다. [추론] 따라서 사람검수에서 핵심 필드 오류가 반복되거나 운영 환경에서 근거 누락이 재현되면, 현 개선안을 보류하고 골든셋·청킹·스키마를 먼저 재설계해야 합니다.", sty["body"])], width=width, bg=PALE_TEAL, edge=colors.HexColor("#9BE5D7")),
        Spacer(1, 5),
        p("근거 코드: backend/app/agents/document_summary.py, backend/app/services/document_processing.py, backend/app/services/sales_context.py. 평가 근거: docs/document-summary-evaluation-report.md (2026-09-15).", sty["small"]),
    ]
    BriefDoc(output, font).build(story)


def make_svg() -> str:
    """Create a polished, editable 16:9 architecture slide on a white canvas."""
    boxes = [
        (85, "01", "원본 입력", ["PDF · DOCX · 이미지", "텍스트 추출 / 필요 시 OCR"], "light"),
        (441, "02", "문서요약 Agent", ["구조화 요약 + 추출 필드", "원문 지시문은 실행하지 않음"], "blue"),
        (797, "03", "RAG 청크", ["Markdown 기반 1,600자", "페이지 · 섹션 출처 보존"], "navy"),
        (1153, "04", "검색", ["권한/범위 필터 후", "키워드 + 벡터를 RRF 결합"], "blue"),
        (1509, "05", "답변 문맥", ["요약 + 근거를 전달", "파일명 · 페이지 추적 가능"], "light"),
    ]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">',
        '<defs><linearGradient id="blue" x1="0" x2="1"><stop stop-color="#2563EB"/><stop offset="1" stop-color="#5B8CFF"/></linearGradient><linearGradient id="navy" x1="0" x2="1"><stop stop-color="#142B52"/><stop offset="1" stop-color="#204A88"/></linearGradient><linearGradient id="mint" x1="0" x2="1"><stop stop-color="#F0FDFA"/><stop offset="1" stop-color="#E0F7F1"/></linearGradient><filter id="shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#1D3A6E" flood-opacity=".10"/></filter></defs>',
        '<rect width="1920" height="1080" fill="#FFFFFF"/>',
        '<circle cx="1765" cy="98" r="164" fill="#EFF5FF"/><circle cx="1765" cy="98" r="106" fill="#DCEAFF" opacity=".8"/><circle cx="108" cy="985" r="122" fill="#F2F7FF"/>',
        '<style>.kr{font-family:AppleGothic,\'Noto Sans CJK KR\',sans-serif}.title{font-size:48px;font-weight:700;fill:#132238;letter-spacing:-1px}.sub{font-size:20px;fill:#667085}.step{font-size:15px;font-weight:700;letter-spacing:1.2px}.boxTitle{font-size:25px;font-weight:700;letter-spacing:-.4px}.body{font-size:18px}.guardTitle{font-size:25px;font-weight:700;fill:#132238}.guardBody{font-size:18px;fill:#475467}.tag{font-size:16px;font-weight:700;letter-spacing:.8px}</style>',
        '<text x="85" y="125" class="kr title">문서요약 Agent와 RAG, 이렇게 연결됩니다</text>',
        '<text x="85" y="171" class="kr sub">문서를 정리하고 · 관련 근거를 찾고 · 출처와 함께 답변 문맥으로 전달하는 구조</text>',
        '<path d="M 228 428 H 1689" stroke="#DCE7FA" stroke-width="4" stroke-linecap="round"/>',
    ]
    for index, (x, step, title, lines, mode) in enumerate(boxes):
        y, width, height = 308, 290, 240
        # Keep every process card on one neutral-blue system for a cohesive deck.
        fill, stroke, title_color, body_color, step_fill, step_color = "#F8FAFF", "#D5E1F4", "#132238", "#475467", "#EAF1FF", "#2563EB"
        svg.extend([
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="2" filter="url(#shadow)"/>',
            f'<rect x="{x + 26}" y="{y + 25}" width="80" height="29" rx="14.5" fill="{step_fill}"/>',
            f'<text x="{x + 66}" y="{y + 46}" class="kr step" text-anchor="middle" fill="{step_color}">STEP {step}</text>',
            f'<text x="{x + 26}" y="{y + 105}" class="kr boxTitle" fill="{title_color}">{escape(title)}</text>',
            f'<path d="M {x + 26} {y + 128} H {x + 258}" stroke="{stroke}" stroke-width="1.5" opacity=".75"/>',
            f'<text x="{x + 26}" y="{y + 169}" class="kr body" fill="{body_color}">{escape(lines[0])}</text>',
            f'<text x="{x + 26}" y="{y + 205}" class="kr body" fill="{body_color}">{escape(lines[1])}</text>',
        ])
        if index < len(boxes) - 1:
            arrow_x = x + width + 15
            svg.append(f'<circle cx="{arrow_x + 18}" cy="428" r="18" fill="#FFFFFF" stroke="#D4E1F7" stroke-width="2"/><path d="M {arrow_x + 9} 428 H {arrow_x + 27}" stroke="#4C7FEA" stroke-width="3" stroke-linecap="round"/><path d="M {arrow_x + 21} 421 L {arrow_x + 28} 428 L {arrow_x + 21} 435" stroke="#4C7FEA" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    svg.extend([
        '<text x="85" y="665" class="kr tag" fill="#2563EB">운영 안전장치</text>',
        '<rect x="85" y="698" width="850" height="190" rx="22" fill="#FFFFFF" stroke="#DCE4F0" stroke-width="2" filter="url(#shadow)"/>',
        '<rect x="85" y="698" width="12" height="190" rx="6" fill="url(#blue)"/>',
        '<rect x="126" y="732" width="92" height="28" rx="14" fill="#EAF1FF"/><text x="172" y="752" class="kr tag" text-anchor="middle" fill="#2563EB">SCOPE</text>',
        '<text x="126" y="803" class="kr guardTitle">근거 범위 통제</text>',
        '<text x="126" y="846" class="kr guardBody">팀 · 열람권한 · 최신 완료 파일 · 삭제 문서 제외</text>',
        '<text x="126" y="878" class="kr guardBody">딜 / 고객사 / 제품 연결 범위 안에서만 검색</text>',
        '<rect x="985" y="698" width="850" height="190" rx="22" fill="#F8FAFF" stroke="#D5E1F4" stroke-width="2" filter="url(#shadow)"/>',
        '<rect x="985" y="698" width="12" height="190" rx="6" fill="url(#blue)"/>',
        '<rect x="1026" y="732" width="102" height="28" rx="14" fill="#EAF1FF"/><text x="1077" y="752" class="kr tag" text-anchor="middle" fill="#2563EB">FALLBACK</text>',
        '<text x="1026" y="803" class="kr guardTitle">장애 시 운영 연속성</text>',
        '<text x="1026" y="846" class="kr guardBody">임베딩이 불가해도 원문·요약은 저장하고 키워드 검색으로 계속 운영</text>',
        '<text x="1026" y="878" class="kr guardBody">단, 의미 유사 검색은 제공되지 않음</text>',
        '</svg>',
    ])
    return "\n".join(svg)


def build_slide_assets(svg_output: Path) -> None:
    svg_output.write_text(make_svg(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=ROOT / "output/pdf/document-summary-agent-rag-current-brief.pdf")
    parser.add_argument("--svg", type=Path, default=ROOT / "output/images/document-summary-agent-rag-current-overview.svg")
    parser.add_argument("--assets-only", action="store_true", help="Regenerate only the PPT-ready SVG asset.")
    args = parser.parse_args()
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    build_slide_assets(args.svg)
    if not args.assets_only:
        args.pdf.parent.mkdir(parents=True, exist_ok=True)
        build_pdf(args.pdf)
        print(args.pdf)
    print(args.svg)


if __name__ == "__main__":
    main()
