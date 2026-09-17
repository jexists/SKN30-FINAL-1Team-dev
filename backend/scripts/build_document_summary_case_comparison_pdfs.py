"""문서요약 평가 케이스별 원본·실제출력 비교 PDF 생성기.

원본 PDF는 페이지 이미지로 삽입하고, 평가 결과 JSON의 실제 출력·기준값·Judge 지적을
같은 케이스에 묶어 사람이 직접 확인할 수 있게 한다.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import subprocess
import unicodedata
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import pdfplumber
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepInFrame,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)
SAMPLE_DIR_NAME = "data/sample"
LOW_CASE_IDS = (
    "summary_계약서_2",
    "summary_발주서_1",
    "summary_계약서_1",
    "summary_계약서_3",
    "summary_발주서_2",
    "summary_발주서_3",
    "rag_EU-ME2",
    "rag_Quick_Clip2",
    "rag_발주서_3",
)
GOOD_CASE_IDS = ("summary_견적서_3", "summary_URF-V2")


def nfc(value: object) -> str:
    return unicodedata.normalize("NFC", str(value))


def safe(value: object) -> str:
    return escape(nfc(value)).replace("\n", "<br/>")


def configure_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("Korean", path))
            return "Korean"
    raise RuntimeError("korean_font_not_found")


def p(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(safe(value), style)


def styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName=font, fontSize=19, leading=26, textColor=colors.HexColor("#182230"), spaceAfter=8),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontName=font, fontSize=9, leading=13, textColor=colors.HexColor("#667085"), spaceAfter=12),
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontName=font, fontSize=14, leading=19, textColor=colors.HexColor("#1D2939"), spaceBefore=11, spaceAfter=6),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName=font, fontSize=10.5, leading=15, textColor=colors.HexColor("#344054"), spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName=font, fontSize=8.5, leading=13, textColor=colors.HexColor("#344054"), spaceAfter=5, wordWrap="CJK"),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName=font, fontSize=7.2, leading=10, textColor=colors.HexColor("#475467"), spaceAfter=3, wordWrap="CJK"),
        "tiny": ParagraphStyle("Tiny", parent=base["BodyText"], fontName=font, fontSize=6.5, leading=9, textColor=colors.HexColor("#475467"), wordWrap="CJK"),
        "cell": ParagraphStyle("Cell", parent=base["BodyText"], fontName=font, fontSize=7.2, leading=10, textColor=colors.HexColor("#344054"), wordWrap="CJK"),
        "cell_head": ParagraphStyle("CellHead", parent=base["BodyText"], fontName=font, fontSize=7.2, leading=10, textColor=colors.white, alignment=TA_CENTER, wordWrap="CJK"),
        "label": ParagraphStyle("Label", parent=base["BodyText"], fontName=font, fontSize=7.5, leading=10, textColor=colors.HexColor("#667085"), spaceAfter=2),
    }


class ReportDoc(BaseDocTemplate):
    def __init__(self, path: Path, sty: dict[str, ParagraphStyle], title: str):
        super().__init__(str(path), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=15 * mm, bottomMargin=17 * mm, title=title, author="SalesLuv")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="report", frames=frame, onPage=self.footer)])
        self.sty = sty

    def footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Korean", 7.5)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(17 * mm, 8.5 * mm, "SalesLuv - 문서요약 케이스 비교")
        canvas.drawRightString(A4[0] - 17 * mm, 8.5 * mm, str(doc.page))
        canvas.restoreState()


def styled_table(rows: list[list[object]], widths: list[float], sty: dict[str, ParagraphStyle], header: bool = True) -> LongTable:
    converted = []
    for ri, row in enumerate(rows):
        cell_style = sty["cell_head"] if header and ri == 0 else sty["cell"]
        converted.append([item if isinstance(item, Paragraph) else p(item, cell_style) for item in row])
    result = LongTable(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#344054")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    result.setStyle(TableStyle(commands))
    return result


def callout(text: str, sty: dict[str, ParagraphStyle]) -> Table:
    result = Table([[p(text, sty["body"])]], colWidths=[176 * mm])
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F4F7")),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return result


def rows_by_id(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["case_id"]: row for group in ("summary_results", "rag_results") for row in results[group]}


def source_path(sample_dir: Path, file_name: str) -> Path:
    target = nfc(file_name)
    for path in sample_dir.rglob("*.pdf"):
        if nfc(path.name) == target:
            return path
    raise FileNotFoundError(target)


def render_source(pdf_path: Path, render_dir: Path) -> list[Path]:
    render_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{pdf_path.parent.name}-{pdf_path.stem}"
    prefix = render_dir / stem
    expected = sorted(render_dir.glob(f"{stem}-*.png"))
    if expected:
        return expected
    subprocess.run(["pdftoppm", "-png", "-r", "100", str(pdf_path), str(prefix)], check=True, capture_output=True)
    return sorted(render_dir.glob(f"{stem}-*.png"))


def fit_image(path: Path, max_width: float, max_height: float) -> Image:
    width, height = ImageReader(str(path)).getSize()
    scale = min(max_width / width, max_height / height)
    return Image(str(path), width=width * scale, height=height * scale)


def source_text(pdf_path: Path, limit: int = 3500) -> str:
    chunks: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    chunks.append(f"[p.{index}] {text}")
    except Exception as exc:
        return f"텍스트 추출 실패: {exc}"
    if not chunks:
        return "이 PDF에는 텍스트 레이어가 없어 원본 페이지 이미지로 확인합니다. (OCR 대상)"
    value = "\n\n".join(chunks)
    return value if len(value) <= limit else value[:limit] + "\n...[원본 텍스트 일부 생략]"


def output_text(row: dict[str, Any]) -> str:
    output = row.get("output", {})
    if row["task_type"] == "rag_query":
        return f"답변:\n{output.get('answer', '')}\n\n인용 파일: {', '.join(output.get('cited_source_files', []))}"
    parts = [f"요약:\n{output.get('summary', '')}"]
    points = output.get("key_points") or []
    if points:
        parts.append("핵심 추출 필드:\n" + "\n".join(f"- {x}" for x in points))
    fields = output.get("extracted_fields") or {}
    if fields:
        parts.append("구조화 추출값:\n" + json.dumps(fields, ensure_ascii=False, indent=2)[:5000])
    return "\n\n".join(parts)


def reference_text(row: dict[str, Any]) -> str:
    fields = row.get("reference_fields") or {}
    if row["task_type"] == "rag_query":
        return f"기준 답변:\n{row.get('reference_answer', '')}"
    return "정답지 기준 필드:\n" + (json.dumps(fields, ensure_ascii=False, indent=2) if fields else "전용 정답지 없음")


def case_category(row: dict[str, Any]) -> str:
    names = row.get("source_files") or row.get("expected_source_files") or [""]
    name = nfc(names[0])
    if name in {"EU-ME2.pdf", "Quick Clip2.pdf", "URF-V2.pdf"}:
        return "상품설명서"
    return name.split("_")[0]


def build_case(story: list[object], row: dict[str, Any], sample_dir: Path, render_dir: Path, sty: dict[str, ParagraphStyle], index: int, total: int, good: bool) -> None:
    names = row.get("source_files") or row.get("expected_source_files") or [""]
    file_name = nfc(names[0])
    pdf_path = source_path(sample_dir, file_name)
    images = render_source(pdf_path, render_dir)
    score = row["judge"]
    label = "양호 케이스" if good else "미흡 케이스"
    story += [
        PageBreak() if index > 1 else Spacer(1, 3 * mm),
        Paragraph(f"{index}. {label} - {file_name}", sty["h1"]),
        styled_table([
            ["케이스", "문서 유형", "작업", "Overall", "Completeness", "Groundedness"],
            [row["case_id"], case_category(row), "요약" if row["task_type"] == "document_summary" else "RAG 질의", f"{score['overall']:.4f}", f"{score['completeness']:.4f}", f"{score['groundedness']:.4f}"],
        ], [36 * mm, 28 * mm, 25 * mm, 24 * mm, 31 * mm, 32 * mm], sty),
        Spacer(1, 3 * mm),
    ]
    source_block = KeepInFrame(73 * mm, 76 * mm, [p("원본 데이터 - 1면 미리보기", sty["label"]), fit_image(images[0], 73 * mm, 72 * mm)], mode="shrink")
    actual_block = KeepInFrame(86 * mm, 76 * mm, [p("실제 생성 결과 - 핵심", sty["label"]), p(output_text(row)[:1700], sty["small"]), Spacer(1, 2 * mm), p(reference_text(row)[:1700], sty["small"])], mode="shrink")
    compare = Table([[source_block, actual_block]], colWidths=[82 * mm, 94 * mm], hAlign="LEFT")
    compare.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FCFCFD")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(compare)
    story += [
        Spacer(1, 3 * mm),
        Paragraph("원본 데이터 텍스트 발췌", sty["h2"]),
        p(source_text(pdf_path, 3000), sty["tiny"]),
        Paragraph("실제 생성 결과 상세", sty["h2"]),
        p(output_text(row), sty["small"]),
        Paragraph("기준값 상세", sty["h2"]),
        p(reference_text(row), sty["small"]),
        Paragraph("Judge 확인사항", sty["h2"]),
        p("[검증] " + (score.get("rationale") or ""), sty["body"]),
    ]
    issues = score.get("issues") or []
    if issues:
        story.append(styled_table([["지적사항"]] + [[f"[검증] {issue}"] for issue in issues], [176 * mm], sty))
    story += [
        Spacer(1, 3 * mm),
        p(f"[검증] 원본 전체 {len(images)}페이지는 아래 페이지에 이미지로 첨부했습니다. 텍스트 레이어가 없는 문서는 이미지가 원본 확인 자료입니다.", sty["small"]),
    ]
    for page_number, image_path in enumerate(images, start=1):
        story += [PageBreak(), Paragraph(f"{file_name} - 원본 페이지 {page_number}/{len(images)}", sty["h2"]), fit_image(image_path, 176 * mm, 245 * mm)]


def build_pdf(path: Path, title: str, case_ids: tuple[str, ...], results: dict[str, Any], sample_dir: Path, render_dir: Path, good: bool) -> None:
    sty = styles(configure_font())
    by_id = rows_by_id(results)
    story: list[object] = [
        Paragraph(title, sty["title"]),
        Paragraph("작성일: 2026-09-15 | 원본 문서와 실제 생성 결과를 케이스별로 직접 대조", sty["subtitle"]),
        callout(
            ("[검증] Judge Overall이 0.80 미만이거나 구체적인 오류가 확인된 대표 케이스를 수록했다. " if not good else "[검증] Judge Overall이 높은 케이스 중 원본과 실제 요약의 대응이 비교적 명확한 2건을 수록했다. ")
            + "점수는 사람검수 전 참고값이며 자동 합격 판정이 아니다.", sty
        ),
        Paragraph("비교 방법", sty["h1"]),
        p("[검증] 왼쪽에는 실제 입력 PDF의 1면 이미지와 텍스트 레이어가 있으면 추출 텍스트를 표시했다. 오른쪽에는 같은 평가 케이스의 실제 생성 결과와 기준값을 표시했다. 이후 해당 원본 PDF의 전체 페이지를 이미지로 첨부했다.", sty["body"]),
        p("[추론] 이미지 원본과 텍스트 결과를 함께 보면 OCR 누락, 필드 역할 혼동, 검색 문맥 누락, 답변 누락을 구분해 확인할 수 있다.", sty["body"]),
    ]
    for index, case_id in enumerate(case_ids, start=1):
        row = by_id.get(case_id)
        if row is None:
            raise KeyError(case_id)
        build_case(story, row, sample_dir, render_dir, sty, index, len(case_ids), good)
    ReportDoc(path, sty, title).build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    results = json.loads((args.results_dir / "llm_judge_results.json").read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    render_dir = args.output_dir.parent.parent / "tmp" / "pdfs" / "case-comparison-source-pages"
    low = args.output_dir / "document-summary-insufficient-cases-comparison.pdf"
    good = args.output_dir / "document-summary-good-cases-comparison.pdf"
    build_pdf(low, "문서요약·RAG 미흡 케이스 원본·실제출력 비교", LOW_CASE_IDS, results, args.sample_dir, render_dir, False)
    build_pdf(good, "문서요약 양호 케이스 원본·실제출력 비교", GOOD_CASE_IDS, results, args.sample_dir, render_dir, True)
    print(json.dumps({"created": [str(low), str(good)]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
