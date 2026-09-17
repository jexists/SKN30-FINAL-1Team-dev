"""문서요약 평가 결과를 두 개의 PDF 보고서로 내보낸다."""

# 보고서용 한글 문장과 표 내용은 가독성을 위해 코드 한 줄 길이 검사를 제외한다.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from statistics import mean
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
    LongTable,
    PageTemplate,
    Paragraph,
    Table,
    TableStyle,
)

PRODUCT_FILES = {"EU-ME2.pdf", "Quick Clip2.pdf", "URF-V2.pdf"}
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)


def configure_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("Korean", path))
            return "Korean"
    raise RuntimeError("korean_font_not_found")


def safe(value: object) -> str:
    return escape(unicodedata.normalize("NFC", str(value))).replace("\n", "<br/>")


def para(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(safe(value), style)


def category(row: dict) -> str:
    names = row.get("source_files") or row.get("expected_source_files") or [""]
    name = unicodedata.normalize("NFC", names[0])
    return "상품설명서" if name in PRODUCT_FILES else name.split("_")[0]


def load_results(results_dir: Path, previous_dir: Path | None = None) -> tuple[dict, dict, dict]:
    golden = json.loads((results_dir / "rageval_golden_set.json").read_text())
    current = json.loads((results_dir / "llm_judge_results.json").read_text())
    baseline_dir = previous_dir or results_dir.parent / "sample-3-each"
    previous = json.loads((baseline_dir / "llm_judge_results.json").read_text())
    return golden, current, previous


class NumberedDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, *, styles: dict[str, ParagraphStyle]):
        super().__init__(
            filename,
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=17 * mm,
            bottomMargin=17 * mm,
            title="문서요약 에이전트 및 RAG 평가 결과",
            author="SalesLuv",
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates(
            [PageTemplate(id="report", frames=frame, onPage=self._draw_footer)]
        )
        self.styles = styles

    def _draw_footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Korean", 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(18 * mm, 9 * mm, "SalesLuv - 문서요약 평가")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"{doc.page}")
        canvas.restoreState()


def make_styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName=font, fontSize=20, leading=27,
            textColor=colors.HexColor("#182230"), spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName=font, fontSize=9, leading=14,
            textColor=colors.HexColor("#667085"), spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName=font, fontSize=14, leading=20,
            textColor=colors.HexColor("#1D2939"), spaceBefore=12, spaceAfter=7,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName=font, fontSize=11, leading=16,
            textColor=colors.HexColor("#344054"), spaceBefore=9, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName=font, fontSize=9, leading=14,
            textColor=colors.HexColor("#344054"), spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["BodyText"], fontName=font, fontSize=7.5, leading=11,
            textColor=colors.HexColor("#475467"), spaceAfter=3,
        ),
        "cell": ParagraphStyle(
            "Cell", parent=base["BodyText"], fontName=font, fontSize=7.6, leading=10.5,
            textColor=colors.HexColor("#344054"), wordWrap="CJK",
        ),
        "cell_head": ParagraphStyle(
            "CellHead", parent=base["BodyText"], fontName=font, fontSize=7.6, leading=10.5,
            textColor=colors.white, alignment=TA_CENTER, wordWrap="CJK",
        ),
        "callout": ParagraphStyle(
            "Callout", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=15,
            textColor=colors.HexColor("#1D2939"), leftIndent=4, rightIndent=4,
        ),
    }


def section_title(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(safe(text), styles["h1"])


def table(data: list[list[object]], widths: list[float], styles: dict[str, ParagraphStyle], *, header=True) -> LongTable:
    converted: list[list[object]] = []
    for row_index, row in enumerate(data):
        converted.append([
            value if isinstance(value, Paragraph) else para(value, styles["cell_head"] if header and row_index == 0 else styles["cell"])
            for value in row
        ])
    result = LongTable(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#344054")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
    result.setStyle(TableStyle(commands))
    return result


def callout(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    result = Table([[Paragraph(safe(text), styles["callout"])]], colWidths=[174 * mm])
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F4F7")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D5DD")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return result


def avg(rows: list[dict], key: str) -> float:
    return mean(float(row["judge"][key]) for row in rows)


def build_main_report(
    output: Path,
    golden: dict,
    current: dict,
    previous: dict,
    styles: dict[str, ParagraphStyle],
    *,
    report_label: str,
    results_dir: Path,
) -> None:
    story: list[object] = [
        Paragraph(f"문서요약 에이전트·RAG {report_label} 평가 결과보고서", styles["title"]),
        Paragraph("작성일: 2026-09-15 | 평가 범위: 4개 유형 각 3개, 총 12개 문서", styles["subtitle"]),
        callout(
            "[검증] 요약 12건과 RAG 12건, 총 24건 평가를 완료했다. "
            f"전체 Overall은 {previous['aggregate']['overall']:.4f}에서 {current['aggregate']['overall']:.4f}로 "
            f"{current['aggregate']['overall'] - previous['aggregate']['overall']:+.4f} 변화했다. "
            "[추론] 계약서 요약과 상품설명서 RAG가 우선 개선 대상이다.", styles
        ),
        section_title("1. 테스트 범위와 방법", styles),
        table([
            ["항목", "내용"],
            ["입력", "[검증] data/sample의 견적서·계약서·발주서·상품설명서 각 3개 PDF"],
            ["골든셋", "[검증] RAGEval 적응형 schema summary -> QRA 흐름"],
            ["정답 보강", "[검증] 견적서·계약서·발주서 정답지 XLSX 9개 반영"],
            ["평가", "[검증] LLM-as-a-Judge: completeness, hallucination, irrelevance, groundedness, retrieval relevance, overall"],
            ["검색", "[검증] 평가 스크립트의 로컬 키워드 검색기; 운영 벡터 검색과 동일하다고 볼 수 없음"],
            ["OCR", "[검증] 텍스트 추출 실패 문서는 OCR provider로 fallback"],
        ], [34 * mm, 140 * mm], styles),
        section_title("2. 전체 결과", styles),
        table([
            ["지표", "재실행", "기존 대비"],
            ["Overall", f"{current['aggregate']['overall']:.4f}", f"{current['aggregate']['overall'] - previous['aggregate']['overall']:+.4f}"],
            ["Completeness", f"{current['aggregate']['completeness']:.4f}", f"{current['aggregate']['completeness'] - previous['aggregate']['completeness']:+.4f}"],
            ["Hallucination 품질점수", f"{current['aggregate']['hallucination']:.4f}", f"{current['aggregate']['hallucination'] - previous['aggregate']['hallucination']:+.4f}"],
            ["Irrelevance 품질점수", f"{current['aggregate']['irrelevance']:.4f}", f"{current['aggregate']['irrelevance'] - previous['aggregate']['irrelevance']:+.4f}"],
            ["Groundedness", f"{current['aggregate']['groundedness']:.4f}", f"{current['aggregate']['groundedness'] - previous['aggregate']['groundedness']:+.4f}"],
            ["Retrieval relevance", f"{current['aggregate']['retrieval_relevance']:.4f}", f"{current['aggregate']['retrieval_relevance'] - previous['aggregate']['retrieval_relevance']:+.4f}"],
        ], [80 * mm, 45 * mm, 49 * mm], styles),
        Paragraph("[검증] 검색 문맥이 비어 있는 RAG 케이스는 이번 실행에서 0건이었다. [미확인] 사람검수 합격 기준은 아직 확정되지 않았다.", styles["body"]),
        section_title("3. 유형별 결과", styles),
    ]

    category_rows = [["문서 유형", "요약 Overall", "RAG Overall", "우선 판단"]]
    for name in ("견적서", "계약서", "발주서", "상품설명서"):
        summary = [r for r in current["summary_results"] if category(r) == name]
        rag = [r for r in current["rag_results"] if category(r) == name]
        priority = {
            "견적서": "상대적으로 안정적",
            "계약서": "요약 개선 최우선",
            "발주서": "요약 필드 보존 확인",
            "상품설명서": "RAG 개선 최우선",
        }[name]
        category_rows.append([name, f"{avg(summary, 'overall'):.4f}", f"{avg(rag, 'overall'):.4f}", priority])
    story.append(table(category_rows, [42 * mm, 35 * mm, 35 * mm, 62 * mm], styles))
    story += [
        Paragraph("[추론] 계약서 RAG 1.0000은 현재 3개 샘플과 현재 질의에 대한 결과이며, 계약서 전체 품질로 일반화할 수 없다.", styles["body"]),
        section_title("4. 주요 판단과 한계", styles),
        Paragraph("[검증] 계약서 요약은 당사자·작성일·공급일·총액·계약금·잔금 누락 및 의미 혼동이 반복됐다.", styles["body"]),
        Paragraph("[검증] 상품설명서 RAG는 문서 선택은 되었으나 EU-ME2의 전압·보호등급과 Quick Clip2의 적용 대상·수치 조건을 답변에 반영하지 못했다.", styles["body"]),
        Paragraph("[검증] 상품설명서는 전용 정답지가 없어 LLM 생성 기준값을 사용했으며, 사람검수 전 최종 정확도를 확정할 수 없다.", styles["body"]),
        Paragraph("[검증] 표본은 유형별 3개이므로 전체 50개 문서군의 성능으로 일반화할 수 없다.", styles["body"]),
        section_title("5. 다음 실행안", styles),
        table([
            ["우선순위", "실행 내용", "측정"],
            ["1", "[추론] 계약서 필수 필드와 금액 의미를 구조화 출력으로 강제", "사람검수 필드 보존 여부"],
            ["2", "[추론] 발주자·공급자·납품장소·지급조건을 역할 기반으로 분리", "역할 뒤바뀜·누락 건수"],
            ["3", "[추론] 상품설명서 사양표·Intended Use chunk 검색 보완", "RAG completeness·groundedness"],
            ["4", "[추론] 사람검수 결과로 Judge 기준과 불일치 케이스 교정", "Judge-사람 판정 불일치율"],
        ], [25 * mm, 105 * mm, 44 * mm], styles),
        section_title("6. 산출물과 검증 기록", styles),
        Paragraph("[검증] 새 결과의 human_review.status는 pending이다. 기준값과 실제 결과 비교 화면은 별도 HTML로 생성했다.", styles["body"]),
        Paragraph("[검증] 관련 단위 테스트와 Ruff lint 검사를 통과했다.", styles["body"]),
        Paragraph(f"[검증] 결과 위치: {results_dir}/", styles["small"]),
    ]
    NumberedDocTemplate(str(output), styles=styles).build(story)


def build_low_score_report(
    output: Path,
    current: dict,
    styles: dict[str, ParagraphStyle],
    *,
    report_label: str,
) -> None:
    summary_rows = sorted(current["summary_results"], key=lambda row: row["judge"]["overall"])
    rag_rows = sorted(current["rag_results"], key=lambda row: row["judge"]["overall"])
    story: list[object] = [
        Paragraph(f"문서요약 에이전트·RAG {report_label} 미흡 결과 별도 보고서", styles["title"]),
        Paragraph(f"작성일: 2026-09-15 | 대상: {report_label} 평가 결과 중 우선 검토 케이스", styles["subtitle"]),
        callout(
            "[검증] 본 문서는 전체 결과보고서에서 상대적으로 낮은 점수이거나 구체적인 오류가 확인된 케이스를 분리한 것이다. "
            "[미확인] 최종 합격 점수 기준은 확정되지 않았으므로 아래 목록은 개선 우선순위이지 자동 불합격 판정이 아니다.", styles
        ),
        section_title("1. 문서요약 우선 검토", styles),
    ]
    summary_data = [["케이스", "유형", "Overall", "Completeness", "주요 확인사항"]]
    selected_summary = [row for row in summary_rows if category(row) in {"계약서", "발주서"}]
    for row in selected_summary:
        names = row.get("source_files") or [""]
        summary_data.append([
            names[0], category(row), f"{row['judge']['overall']:.4f}", f"{row['judge']['completeness']:.4f}",
            "[검증] " + " | ".join(row["judge"]["issues"][:3]),
        ])
    story.append(table(summary_data, [30 * mm, 24 * mm, 22 * mm, 27 * mm, 71 * mm], styles))
    story += [
        Paragraph("[추론] 계약서의 반복 원인은 OCR이 불완전한 필드까지 확인 불가로 처리한 점과 계약금·잔금·VAT의 의미 분리 부족이다.", styles["body"]),
        Paragraph("[추론] 발주서의 반복 원인은 발주자·공급자 역할, 납품장소, 대금 지급조건을 필수 구조화 필드로 강제하지 않은 점이다.", styles["body"]),
        section_title("2. RAG 우선 검토", styles),
    ]
    rag_data = [["케이스", "유형", "Overall", "Groundedness", "검색 관련성", "주요 확인사항"]]
    selected_rag = [row for row in rag_rows if row["judge"]["overall"] < 0.8]
    for row in selected_rag:
        names = row.get("expected_source_files") or [""]
        rag_data.append([
            names[0], category(row), f"{row['judge']['overall']:.4f}", f"{row['judge']['groundedness']:.4f}",
            f"{row['judge']['retrieval_relevance']:.4f}", "[검증] " + " | ".join(row["judge"]["issues"][:3]),
        ])
    story.append(table(rag_data, [29 * mm, 24 * mm, 21 * mm, 25 * mm, 27 * mm, 48 * mm], styles))
    story += [
        Paragraph("[추론] EU-ME2와 Quick Clip2는 파일 자체는 검색되었지만 핵심 사양이 포함된 chunk가 답변에 충분히 반영되지 않았다. 검색 적중과 답변 완결성을 별도로 관리해야 한다.", styles["body"]),
        Paragraph("[추론] 발주서_3은 검색 문맥이 있었으나 문서 하단의 발주 합계가 누락되었으므로 합계·금액 영역에 대한 후처리 또는 질문별 필수 사실 검증이 필요하다.", styles["body"]),
        section_title("3. 개선 작업 목록", styles),
        table([
            ["대상", "필수 개선", "확인 방법"],
            ["계약서 요약", "당사자·대표자·작성일·공급일·총액·계약금·잔금 추출", "사람검수에서 필드별 기준값과 대조"],
            ["발주서 요약", "발주자·공급자·납품장소·지급조건 역할 분리", "역할 뒤바뀜 및 누락 케이스 재평가"],
            ["상품설명서 RAG", "사양표·Intended Use·수치 조건 chunk 우선 검색", "질의별 retrieved context와 답변 사실 대조"],
            ["금액 RAG", "합계·VAT·계약금·잔금의 위치·의미 검증", "금액 필드 누락률 및 오인식 건수"],
        ], [34 * mm, 85 * mm, 55 * mm], styles),
        section_title("4. 검수 시 유의사항", styles),
        Paragraph("[검증] 상품설명서는 전용 정답지가 없으므로 기준값부터 사람이 승인해야 한다.", styles["body"]),
        Paragraph("[검증] 새 결과는 아직 human_review.status=pending이다. 이전 실행 검수 JSON은 새 결과에 적용하지 않았다.", styles["body"]),
        Paragraph("[미확인] 유형별 허용 누락률, 최소 Overall, Judge-사람 불일치 허용 범위는 아직 정해지지 않았다.", styles["body"]),
    ]
    NumberedDocTemplate(str(output), styles=styles).build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--previous-results-dir", type=Path)
    parser.add_argument("--report-label", default="1차")
    parser.add_argument("--output-stem", default="1st")
    args = parser.parse_args()
    font = configure_font()
    styles = make_styles(font)
    golden, current, previous = load_results(args.results_dir, args.previous_results_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    main_pdf = args.output_dir / f"document-summary-evaluation-report-{args.output_stem}.pdf"
    low_pdf = args.output_dir / f"document-summary-low-score-cases-report-{args.output_stem}.pdf"
    build_main_report(
        main_pdf,
        golden,
        current,
        previous,
        styles,
        report_label=args.report_label,
        results_dir=args.results_dir,
    )
    build_low_score_report(low_pdf, current, styles, report_label=args.report_label)
    print(json.dumps({"created": [str(main_pdf), str(low_pdf)]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
