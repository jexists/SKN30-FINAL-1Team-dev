"""문서요약 1차·2차 실제 요약문 비교 PDF 생성기."""

# 보고서용 한글 문장은 가독성을 위해 코드 한 줄 길이 검사를 제외한다.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

import pdfplumber
from build_document_summary_pdfs import (
    NumberedDocTemplate,
    callout,
    configure_font,
    make_styles,
    para,
    section_title,
    table,
)
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle

CATEGORY_ORDER = ("견적서", "계약서", "발주서", "상품설명서")
PRODUCT_FILES = {"EU-ME2.pdf", "Quick Clip2.pdf", "URF-V2.pdf"}


def nfc(value: object) -> str:
    return unicodedata.normalize("NFC", str(value))


def source_file(row: dict[str, Any]) -> str:
    values = row.get("source_files") or row.get("expected_source_files") or [""]
    return nfc(values[0])


def category(row: dict[str, Any]) -> str:
    name = source_file(row)
    if name in PRODUCT_FILES:
        return "상품설명서"
    return name.split("_")[0]


def load_summary_rows(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text())
    return {row["case_id"]: row for row in data["summary_results"]}


def match_rows(first: dict[str, dict[str, Any]], second: dict[str, dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """case_id가 재실행 과정에서 표기만 달라져도 같은 문서를 짝짓는다."""
    second_by_normalized = {nfc(key).replace("_", "-"): row for key, row in second.items()}
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for key, first_row in first.items():
        second_row = second.get(key) or second_by_normalized.get(nfc(key).replace("_", "-"))
        if second_row is None:
            raise KeyError(f"second_result_missing:{key}")
        pairs.append((first_row, second_row))
    return pairs


def score_text(row: dict[str, Any]) -> str:
    score = row.get("judge", {}).get("overall")
    return "-" if score is None else f"{float(score):.4f}"


def score_delta(first: dict[str, Any], second: dict[str, Any]) -> str:
    first_score = float(first.get("judge", {}).get("overall", 0))
    second_score = float(second.get("judge", {}).get("overall", 0))
    return f"{second_score - first_score:+.4f}"


def summary_text(row: dict[str, Any]) -> str:
    value = row.get("output", {}).get("summary") or "(요약 결과 없음)"
    return nfc(value)


def source_path(sample_dir: Path, file_name: str) -> Path:
    target = nfc(file_name)
    for path in sample_dir.rglob("*.pdf"):
        if nfc(path.name) == target:
            return path
    raise FileNotFoundError(target)


def source_page_count(pdf_path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"source_pages_missing:{pdf_path}")


def source_raw_text(pdf_path: Path, render_dir: Path, page_count: int) -> str:
    """요약 입력에 사용되는 원문을 텍스트 추출 또는 로컬 OCR로 복원한다."""
    pages: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                pages.append(f"[p.{index}]\n{text}" if text else "")
    except Exception as exc:
        pages = []
        extraction_error = f"텍스트 레이어 추출 실패: {exc}"
    else:
        extraction_error = ""

    if pages and any(text.strip() for text in pages):
        return "\n\n".join(pages)

    ocr_pages: list[str] = []
    ocr_dir = render_dir / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    for page_number in range(1, page_count + 1):
        prefix = ocr_dir / f"{pdf_path.parent.name}-{pdf_path.stem}-p{page_number}"
        image_path = prefix.with_suffix(".png")
        if not image_path.exists():
            subprocess.run(
                ["pdftoppm", "-png", "-r", "180", "-f", str(page_number), "-l", str(page_number), "-singlefile", str(pdf_path), str(prefix)],
                check=True,
                capture_output=True,
            )
        result = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", "kor+eng", "--psm", "6"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        text = result.stdout.strip()
        ocr_pages.append(f"[p.{page_number}]\n{text}" if text else f"[p.{page_number}]\n(OCR 결과 없음)")
    prefix = "[검증] PDF 텍스트 레이어가 없어 원본 페이지를 로컬 OCR(kor+eng)한 결과입니다.\n"
    if extraction_error:
        prefix += f"[미확인] {extraction_error}\n"
    return prefix + "\n\n".join(ocr_pages)


def summary_criteria(sty: dict[str, Any]) -> Table:
    return table([
        ["기준", "적용 내용"],
        ["사실성", "[검증] 원문에 명시된 사실만 사용하고, 원문에 없는 원인·평가·전망·수치는 추가하지 않음"],
        ["핵심 요약", "[검증] 결론이 먼저 드러나는 짧은 문단으로 작성하고, 중요도와 논리 흐름에 따라 재구성"],
        ["핵심 필드", "[검증] 계약금액·날짜·당사자·납기·품목 등 판독 가능한 필드를 보존"],
        ["불확실성", "[검증] OCR 손상은 해당 필드에만 제한해 표시하고, 다른 명확한 필드까지 미확인으로 만들지 않음"],
        ["추가 섹션", "[검증] key_points·sales_relevance·risk_flags는 원문 근거가 있는 내용만 완결된 문장으로 작성"],
        ["원문 보존 필드", "[검증] extracted_fields와 source_refs는 문체 변환보다 원문 값과 근거 보존을 우선"],
        ["출력 형식", "[검증] summary, key_points, sales_relevance, risk_flags, extracted_fields, source_refs JSON 구조"],
    ], [31 * mm, 143 * mm], sty)


def category_conclusion(name: str) -> str:
    conclusions = {
        "견적서": "[추론] 2차는 견적서 2번에서 견적번호를 보완했지만, 3번에서는 문장을 간결하게 줄였다. 금액·고객·일자·유효기간은 두 실행에서 공통으로 유지된다.",
        "계약서": "[추론] 2차는 계약서 1번과 3번에서 품목별 금액과 금액 성격을 더 구체적으로 적었다. 다만 세 케이스 모두 OCR 손상으로 당사자·일정·조항 확인이 제한되는 점은 해소되지 않았다.",
        "발주서": "[추론] 2차는 발주서 1번에서 총수량과 누락된 일정·결제 정보를 명시했고, 2번에서는 담당자를 추가했다. 반면 1번의 품목 코드·세부 수량은 요약문에서 빠져 확인 범위가 달라졌다.",
        "상품설명서": "[추론] 2차는 EU-ME2에서 Doppler·저장·측정·PIP 기능을 더 명시했고, QuickClip2와 URF-V2는 핵심 기능 중심으로 더 짧게 정리했다. 제품별 사양·용도 표현의 포함 범위가 달라졌다.",
    }
    return conclusions[name]


def comparison_card(
    first: dict[str, Any],
    second: dict[str, Any],
    sty: dict[str, Any],
) -> Table:
    file_name = source_file(first)
    title = f"{file_name}  |  Overall {score_text(first)} → {score_text(second)}  ({score_delta(first, second)})"
    header_style = sty["cell_head"]
    body_style = sty["cell"]
    header = Table([[Paragraph(title, header_style)]], colWidths=[174 * mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#344054")),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#344054")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    body = Table([
        [
            para("1차 실제 요약 결과", header_style),
            para("2차 실제 요약 결과", header_style),
        ],
        [
            para(summary_text(first), body_style),
            para(summary_text(second), body_style),
        ],
    ], colWidths=[87 * mm, 87 * mm], hAlign="LEFT")
    body.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#667085")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    wrapper = Table([[header], [body]], colWidths=[174 * mm], hAlign="LEFT")
    wrapper.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return wrapper


def build_pdf(output: Path, first_path: Path, second_path: Path, sample_dir: Path) -> None:
    font = configure_font()
    sty = make_styles(font)
    first = load_summary_rows(first_path)
    second = load_summary_rows(second_path)
    pairs = match_rows(first, second)
    render_dir = output.parent.parent / "tmp" / "pdfs" / "summary-output-comparison-source-pages"
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {name: [] for name in CATEGORY_ORDER}
    for first_row, second_row in pairs:
        grouped.setdefault(category(first_row), []).append((first_row, second_row))

    story: list[object] = [
        Paragraph("문서요약 1차·2차 실제 요약내용 비교", sty["title"]),
        Paragraph("작성일: 2026-09-15 | 평가 결과 JSON의 summary_results 12건을 문서별로 직접 대조", sty["subtitle"]),
        callout(
            "[검증] 각 문서의 1차 실제 요약문과 2차 실제 요약문을 좌우로 배치하고, 요약 전 원문은 부록에 별도로 수록했다. "
            "Overall 점수는 내용 변화의 참고값이며, 최종 판단은 요약문과 원본 문서의 대응을 사람이 확인해야 한다.", sty
        ),
        section_title("1. 요약 기준", sty),
        Paragraph("[검증] 아래 기준은 문서요약 에이전트의 document_summary.v2 지침을 사람이 확인할 수 있도록 요약한 것이다.", sty["body"]),
        summary_criteria(sty),
        Spacer(1, 4 * mm),
        section_title("2. 비교 결론", sty),
        table([
            ["문서 유형", "1차·2차 요약내용 변화", "판단 포인트"],
            ["견적서", "[검증] 고객·금액·일자·유효기간은 대체로 공통 유지", "[추론] 견적번호·문장 길이 등 표현 범위 변화 확인"],
            ["계약서", "[검증] 2차에서 품목별 금액과 금액 성격 표현이 증가", "[추론] OCR 손상에 따른 당사자·일정 누락은 계속 확인 필요"],
            ["발주서", "[검증] 2차에서 총수량·담당자·누락 일정 정보가 케이스별로 추가", "[추론] 품목 코드·세부 수량이 요약문에서 빠진 케이스 확인 필요"],
            ["상품설명서", "[검증] 2차에서 EU-ME2 기능 설명은 구체화, 일부 제품은 간결화", "[추론] 제품별 핵심 사양과 사용범위의 포함 여부를 별도 확인"],
        ], [27 * mm, 73 * mm, 74 * mm], sty),
        Spacer(1, 4 * mm),
        callout("[추론] 2차 요약은 문장 표현과 포함 정보가 케이스별로 달라졌다. 따라서 점수만 비교하기보다 아래 문서별 좌우 비교에서 핵심 필드의 유지·추가·누락을 직접 판정해야 한다.", sty),
    ]

    for category_name in CATEGORY_ORDER:
        story.append(PageBreak())
        story.append(Paragraph(f"{CATEGORY_ORDER.index(category_name) + 3}. {category_name} 요약내용 비교", sty["h1"]))
        story.append(Paragraph(category_conclusion(category_name), sty["body"]))
        for index, (first_row, second_row) in enumerate(grouped.get(category_name, []), start=1):
            story.append(KeepTogether([
                Paragraph(f"{index}. {source_file(first_row)}", sty["h2"]),
                comparison_card(first_row, second_row, sty),
            ]))
            if index < len(grouped.get(category_name, [])):
                story.append(Spacer(1, 5 * mm))

    story.extend([
        PageBreak(),
        section_title("7. 부록 - 요약 전 원문", sty),
        Paragraph(
            "[검증] 각 문서의 요약 실행 전에 사용된 입력 원문을 문서별로 수록했다. 텍스트 레이어가 있는 PDF는 추출 텍스트를, "
            "텍스트 레이어가 없는 PDF는 원본 페이지를 로컬 OCR한 결과를 표시했다.",
            sty["body"],
        ),
    ])
    seen_files: set[str] = set()
    for first_row, _second_row in pairs:
        file_name = source_file(first_row)
        if file_name in seen_files:
            continue
        seen_files.add(file_name)
        source_pdf = source_path(sample_dir, file_name)
        pages = source_page_count(source_pdf)
        story.extend([
            Paragraph(f"{file_name} - 원문 ({pages}페이지)", sty["h2"]),
            para(source_raw_text(source_pdf, render_dir, pages), sty["small"]),
        ])

    NumberedDocTemplate(str(output), styles=sty).build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(args.output, args.first, args.second, args.sample_dir)
    print(json.dumps({"created": str(args.output), "pages_expected": "auto"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
