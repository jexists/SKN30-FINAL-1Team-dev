"""Build a presentation-ready product-description OCR validation report."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-product-ocr-report")

import matplotlib.pyplot as plt
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
    Image,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
DIRECT = ROOT / "output/evals/ocr-product-description/runpod_product_description_summary.json"
PNG = ROOT / "output/evals/ocr-product-description/runpod_product_description_failure_png_check.json"
OUTPUT = ROOT / "output/pdf/ocr-product-description-validation-report-20260917.pdf"
TMP = ROOT / "tmp/pdfs/product-description-ocr"
CHART = TMP / "product-description-ocr-comparison.png"
FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

pdfmetrics.registerFont(TTFont("AppleGothic", FONT))

NAVY = colors.HexColor("#18324B")
BLUE = colors.HexColor("#2D6CDF")
GREEN = colors.HexColor("#0E8A6D")
PALE = colors.HexColor("#EAF2FF")
TEXT = colors.HexColor("#243444")
GRAY = colors.HexColor("#5E6B78")
LIGHT = colors.HexColor("#F5F7FA")
LINE = colors.HexColor("#D8DEE7")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleKr", parent=styles["Title"], fontName="AppleGothic", fontSize=21, leading=27, textColor=NAVY, spaceAfter=3))
styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontName="AppleGothic", fontSize=9.2, leading=13, textColor=GRAY, spaceAfter=7))
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="AppleGothic", fontSize=12.8, leading=16, textColor=NAVY, spaceBefore=6, spaceAfter=5))
styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.35, leading=11.6, textColor=TEXT, spaceAfter=3))
styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.3, leading=9.45, textColor=TEXT))
styles.add(ParagraphStyle(name="Header", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.3, leading=9.2, textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.8, leading=12.5, textColor=NAVY, backColor=PALE, borderColor=BLUE, borderWidth=0.5, borderPadding=7, spaceAfter=7))
styles.add(ParagraphStyle(name="Note", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.05, leading=9.5, textColor=GRAY, spaceAfter=3))


def p(value: str, style: str = "Body") -> Paragraph:
    return Paragraph(value, styles[style])


def make_table(rows: list[list[str]], widths: list[float]) -> Table:
    values = [[p(value, "Header" if row_index == 0 else "Cell") for value in row] for row_index, row in enumerate(rows)]
    result = Table(values, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.2),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row in range(1, len(rows)):
        if row % 2 == 0:
            commands.append(("BACKGROUND", (0, row), (-1, row), LIGHT))
    result.setStyle(TableStyle(commands))
    return result


def metric_block(label: str, value: str, note: str, color: colors.Color) -> Table:
    item = Table(
        [[p(label, "Note")], [p(value, "TitleKr")], [p(note, "Note")]],
        colWidths=[55 * mm],
    )
    item.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 1.2, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return item


def build_chart(direct: dict, png: dict) -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    direct_dataset = direct["dataset"]
    matched = direct_dataset["product_identifier"]["matched"]
    total = direct_dataset["input_count"]
    direct_e2e = matched / total * 100
    final_matched = matched + int(bool(png["matched"]))
    final_e2e = final_matched / total * 100
    fig, axes = plt.subplots(1, 2, figsize=(8.7, 2.55), dpi=180)
    for axis, values, title, formatter in [
        (axes[0], [direct_e2e, final_e2e], "Identifier match rate", lambda value: f"{value:.1f}%"),
        (axes[1], [direct_dataset["success_count"] / total * 100, 100.0], "Document processing success", lambda value: f"{value:.1f}%"),
    ]:
        bars = axis.bar(["PDF direct", "PNG retry"], values, color=["#8FA8C7", "#16856E"], width=0.58)
        axis.set_ylim(0, 112)
        axis.set_title(title, fontsize=11, color="#18324B", pad=10)
        axis.grid(axis="y", color="#D8DEE7", linewidth=0.7)
        axis.set_axisbelow(True)
        for spine in ("top", "right", "left"):
            axis.spines[spine].set_visible(False)
        axis.tick_params(axis="y", left=False, labelleft=False)
        axis.tick_params(axis="x", labelsize=8.4)
        for bar, value in zip(bars, values):
            axis.text(bar.get_x() + bar.get_width() / 2, value + 3, formatter(value), ha="center", va="bottom", fontsize=10, fontweight="bold", color="#18324B")
    fig.tight_layout(w_pad=2.8)
    fig.savefig(CHART, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("AppleGothic", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9 * mm, "SalesLuv | 상품설명서 OCR 검증 | 2026-09-17")
    canvas.drawRightString(192 * mm, 9 * mm, str(doc.page))
    canvas.restoreState()


def build() -> None:
    direct = json.loads(DIRECT.read_text(encoding="utf-8"))
    png = json.loads(PNG.read_text(encoding="utf-8"))
    dataset = direct["dataset"]
    total = dataset["input_count"]
    direct_matched = dataset["product_identifier"]["matched"]
    direct_success = dataset["success_count"]
    final_matched = direct_matched + int(bool(png["matched"]))
    assert total == 50 and direct_success == 49 and final_matched == 43 and png["rendered_page_count"] == 3
    build_chart(direct, png)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=A4, title="상품설명서 RunPod OCR 검증 결과",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=20 * mm,
    )
    frame = Frame(18 * mm, 20 * mm, 174 * mm, 257 * mm, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])
    story = [
        p("상품설명서 RunPod OCR 검증 결과", "TitleKr"),
        p("파일명 기반 제품 식별자 50개를 기준으로 PDF 직접 OCR과 실패 시 PNG 이미지 OCR 재시도를 비교한 검증", "Sub"),
        HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=9),
        p("결론", "H1"),
        p("[검증] PDF 직접 처리에서는 42/50건이 일치했고 1건이 RunPod 작업 실패였다. 실패 문서 `urf-v.pdf`를 같은 RunPod 이미지 OCR 경로로 3페이지 재처리한 결과 식별자가 일치했다. 조건부 복구를 포함한 최종 결과는 43/50 = 86.0%, 처리 성공 50/50 = 100.0%다.", "Callout"),
        Table([[metric_block("최종 제품 식별자 일치율", "86.0%", "43 / 50문서", GREEN), metric_block("최종 처리 성공률", "100.0%", "50 / 50문서", BLUE), metric_block("PDF 직접 일치율", "84.0%", "42 / 50문서", colors.HexColor("#6A829E"))]], colWidths=[58 * mm, 58 * mm, 58 * mm]),
        Spacer(1, 7),
        Image(str(CHART), width=174 * mm, height=50 * mm),
        p("[검증] PDF 직접 일치율은 실패 문서도 전체 분모에 포함해 42/50으로 계산했다. 성공 문서만 분모로 한 값은 42/49 = 85.7%이며, 두 수치를 혼용하지 않았다.", "Note"),
        p("테스트 방법과 사용 자료", "H1"),
        make_table([
            ["항목", "내용"],
            ["테스트 모델", "RunPod Serverless OCR 워커의 `salesluv` 내부 계약. PDF 직접 경로와 PNG 이미지 경로는 같은 RunPod 워커를 사용."],
            ["입력 표본", "상품설명서 PDF 50건, 총 156페이지. 파일명에서 제품 식별자 50개를 추출해 정답지로 고정."],
            ["정답지", "파일명 기반 제품 식별자. 각 정답값을 영문·숫자만 남기고 소문자로 정규화."],
            ["판정식", "일치율 = OCR 본문에 정규화된 제품 식별자가 포함된 문서 수 ÷ 전체 입력 문서 수."],
            ["오류 복구", "PDF OCR 작업 실패 시에만 해당 PDF의 모든 페이지를 PNG로 렌더링해 같은 RunPod 이미지 OCR로 재요청."],
        ], [31 * mm, 143 * mm]),
        p("결과 상세", "H1"),
        make_table([
            ["구간", "OCR 경로", "일치", "처리", "판정"],
            ["기준", "원본 PDF → RunPod PDF OCR", "42/50 = 84.0%", "49/50 = 98.0%", "`urf-v.pdf` 1건 작업 실패"],
            ["복구 확인", "`urf-v.pdf` 3페이지 → PNG → RunPod 이미지 OCR", "1/1 일치", "1/1 성공", "실패 문서 식별자 복구"],
            ["최종", "PDF 직접 결과 + 실패 문서 PNG 결과", "43/50 = 86.0%", "50/50 = 100.0%", "+2.0%p, +1문서"],
        ], [26 * mm, 57 * mm, 29 * mm, 27 * mm, 35 * mm]),
        p("해석과 한계", "H1"),
        p("[검증] 이 검증은 제품 식별자 1개가 OCR 본문에 존재하는지 평가한다. [미확인] 전체 문서 전사 정확도, 사양 값 추출 정확도, 표 구조 보존, CER/WER, 페이지 내 필드 위치 정확도는 이 정답지로 측정하지 않았다. [추론] 제품 검색·분류의 최소 식별에는 활용 가능하지만, 제품 사양 자동 등록의 정확도를 주장하려면 별도 사양 필드 정답지가 필요하다.", "Callout"),
        p("검증 산출물: 파일명 기반 정답지 50건, PDF 직접 OCR 집계, 실패 문서 PNG 재시도 집계. OCR 전문은 저장하지 않아 원문 노출을 줄였다.", "Note"),
    ]
    doc.build(story)


if __name__ == "__main__":
    build()
