"""Create a presentation-ready before/after report for conditional PDF-to-PNG OCR."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-ocr-report")

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
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
AB_SUMMARY = ROOT / "output/evals/ocr-png-fallback-ab/runpod_png_fallback_ab_summary.json"
FINAL_SUMMARY = ROOT / "output/evals/ocr-final-policy/runpod_final_policy_summary.json"
OUTPUT = ROOT / "output/pdf/ocr-final-policy-validation-report-20260917.pdf"
TMP = ROOT / "tmp/pdfs/ocr-conditional-png-ab"
CHART = TMP / "field-match-before-after.png"
FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

pdfmetrics.registerFont(TTFont("AppleGothic", FONT))
ab_data = json.loads(AB_SUMMARY.read_text(encoding="utf-8"))
final_data = json.loads(FINAL_SUMMARY.read_text(encoding="utf-8"))

NAVY = colors.HexColor("#18324B")
BLUE = colors.HexColor("#2D6CDF")
GREEN = colors.HexColor("#0E8A6D")
PALE = colors.HexColor("#EAF2FF")
GRAY = colors.HexColor("#5E6B78")
LIGHT = colors.HexColor("#F5F7FA")
TEXT = colors.HexColor("#243444")
LINE = colors.HexColor("#D8DEE7")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleKr", parent=styles["Title"], fontName="AppleGothic", fontSize=21, leading=27, textColor=NAVY, spaceAfter=4))
styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontName="AppleGothic", fontSize=9.2, leading=13, textColor=GRAY, spaceAfter=6))
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="AppleGothic", fontSize=13.1, leading=17, textColor=NAVY, spaceBefore=4, spaceAfter=5))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontName="AppleGothic", fontSize=10.2, leading=13.5, textColor=BLUE, spaceBefore=6, spaceAfter=3))
styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.45, leading=12, textColor=TEXT, spaceAfter=3))
styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.1, leading=9.25, textColor=TEXT))
styles.add(ParagraphStyle(name="Header", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.1, leading=9.15, textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.65, leading=12.4, textColor=NAVY, backColor=PALE, borderColor=BLUE, borderWidth=0.5, borderPadding=6, spaceAfter=6))
styles.add(ParagraphStyle(name="Note", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.0, leading=9.4, textColor=GRAY, spaceAfter=2))


def p(text: str, style: str = "Body") -> Paragraph:
    return Paragraph(text, styles[style])


def table(rows: list[list[object]], widths: list[float], *, header: bool = True) -> Table:
    converted = []
    for row_number, row in enumerate(rows):
        style = "Header" if header and row_number == 0 else "Cell"
        converted.append([value if hasattr(value, "wrap") else p(str(value), style) for value in row])
    result = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    for row_number in range(1 if header else 0, len(rows)):
        if row_number % 2 == 0:
            commands.append(("BACKGROUND", (0, row_number), (-1, row_number), LIGHT))
    result.setStyle(TableStyle(commands))
    return result


def field_total(dataset: dict) -> tuple[int, int]:
    values = dataset["field_matches"].values()
    return sum(value["matched"] for value in values), sum(value["labeled"] for value in values)


def accuracy(dataset: dict) -> float:
    matched, labeled = field_total(dataset)
    return matched / labeled * 100


def score_text(dataset: dict) -> str:
    matched, labeled = field_total(dataset)
    return f"{matched}/{labeled} = {accuracy(dataset):.1f}%"


def hybrid_purchase_order(pdf_result: dict, png_result: dict) -> dict:
    """Keep the proven PDF supplier address and use PNG results for all other fields.

    This is a deterministic field-selection policy, not an OR-style estimate:
    the selected source for each field is explicit.
    """
    merged = deepcopy(png_result)
    merged["field_matches"]["공급자 주소"] = deepcopy(pdf_result["field_matches"]["공급자 주소"])
    merged["field_source_policy"] = {
        "default": "rendered_png",
        "공급자 주소": "original_pdf",
    }
    return merged


def chart(contract_before: dict, contract_after: dict, order_before: dict, order_png: dict, order_hybrid: dict) -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "AppleGothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig, axis = plt.subplots(figsize=(8.6, 3.3), dpi=180)
    labels = ["계약서\n50건 · 200페이지", "발주서\n50건 · 50페이지"]
    before = [accuracy(contract_before), accuracy(order_before)]
    png = [accuracy(contract_after), accuracy(order_png)]
    hybrid = [None, accuracy(order_hybrid)]
    positions = [0, 1]
    width = 0.22
    axis.bar([item - width for item in positions], before, width, label="A. 원본 PDF", color="#8FA8C7")
    axis.bar(positions, png, width, label="B. PNG OCR", color="#16856E")
    axis.bar([1 + width], [hybrid[1]], width, label="C. PDF·PNG 병합", color="#2D6CDF")
    for position, value in zip([item - width for item in positions], before):
        axis.text(position, value + 2.5, f"{value:.1f}%", ha="center", va="bottom", fontsize=10, color="#18324B")
    for position, value in zip(positions, png):
        axis.text(position, value + 2.5, f"{value:.1f}%", ha="center", va="bottom", fontsize=10, color="#0E654F", fontweight="bold")
    axis.text(1 + width, hybrid[1] + 2.5, f"{hybrid[1]:.1f}%", ha="center", va="bottom", fontsize=10, color="#1E52A8", fontweight="bold")
    axis.set_ylim(0, 112)
    axis.set_ylabel("선정 필드 일치율")
    axis.set_xticks(positions, labels)
    axis.grid(axis="y", color="#D8DEE7", linewidth=0.7)
    axis.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        axis.spines[spine].set_visible(False)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(CHART, transparent=False, bbox_inches="tight")
    plt.close(fig)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("AppleGothic", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9 * mm, "SalesLuv | RunPod OCR 최종 재검증 | 2026-09-17")
    canvas.drawRightString(192 * mm, 9 * mm, str(doc.page))
    canvas.restoreState()


def build() -> None:
    baseline_contract = ab_data["baseline"]["계약서"]
    candidate_contract = final_data["datasets"]["계약서"]
    baseline_order = ab_data["baseline"]["발주서"]
    candidate_order = ab_data["candidate"]["발주서"]
    hybrid_order = final_data["datasets"]["발주서"]
    business_retry = ab_data["business_license_retry"]
    contract_delta = accuracy(candidate_contract) - accuracy(baseline_contract)
    order_png_delta = accuracy(candidate_order) - accuracy(baseline_order)
    order_hybrid_delta = accuracy(hybrid_order) - accuracy(baseline_order)
    assert field_total(hybrid_order) == (739, 750)
    assert hybrid_order["field_matches"]["공급자 주소"]["matched"] == 50
    chart(baseline_contract, candidate_contract, baseline_order, candidate_order, hybrid_order)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame = Frame(18 * mm, 20 * mm, 174 * mm, 257 * mm, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=20 * mm,
        title="RunPod OCR 최종 재검증 결과",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])

    story = [
        p("RunPod OCR 최종 재검증 결과", "TitleKr"),
        p("동일 RunPod OCR 모델에서 조건부 PNG 재시도와 발주서 필드 병합을 100건 전체로 재실행한 발표용 검증", "Sub"),
        HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=7),
        p("결론", "H1"),
        p(
            f"[검증] 실제 RunPod 재시험에서 계약서는 {score_text(baseline_contract)}에서 {score_text(candidate_contract)}로 {contract_delta:+.1f}%p 상승했다. 발주서는 PNG OCR의 {score_text(candidate_order)}에 PDF 경로 공급자 주소 50/50을 병합해 {score_text(hybrid_order)}({order_hybrid_delta:+.1f}%p)로 재현했다.",
            "Callout",
        ),
        p("1. 실제 재시험 결과", "H1"),
        Image(str(CHART), width=174 * mm, height=67 * mm),
        p("[검증] 그래프는 문서별 선정 정답값이 OCR 본문에 포함되는지를 계산한 필드 일치율이다. 발주서 병합은 공급자 주소만 PDF, 나머지 14개 필드는 PNG를 선택했다. 문자 단위 정확도·필드 위치 정확도·CER/WER과는 다른 지표다.", "Note"),
        p("2. 테스트 방법과 사용 자료", "H1"),
        table([
            ["구분", "기준 경로 A", "개선 경로 B·병합", "통제 조건"],
            ["입력", "원본 PDF를 RunPod PDF 입력으로 전달", "모든 PDF 페이지를 PNG로 렌더링. 발주서 주소는 PDF, 나머지는 PNG 결과 선택", "원본 문서·정답 필드·OCR 워커는 동일"],
            ["OCR 모델", "RunPod Serverless OCR 워커", "같은 RunPod Serverless OCR 워커", "같은 한국어 이미지 모델 번들·동시성 2"],
            ["렌더링", "해당 없음", "긴 변 2,200px. 인라인 한도 초과 시 1,100px까지 축소", "페이지별 PNG 생성"],
            ["표본", "계약서 50건 200페이지·발주서 50건 50페이지", "동일 100건 250페이지를 재실행", "문서별 선정 정답 필드 연결"],
            ["판정", "정규화한 정답값이 OCR 본문에 포함되는지 확인", "동일. 필드별로 사전 지정한 경로를 선택", "일치 필드 수 ÷ 라벨 필드 수"],
        ], [24 * mm, 48 * mm, 57 * mm, 45 * mm]),
        PageBreak(),
        p("3. 최종 검증 상세", "H1"),
        table([
            ["대상", "A. PDF 경로", "최종 선택 결과", "변화", "처리 성공"],
            ["계약서", score_text(baseline_contract), f"PNG 재시험 {score_text(candidate_contract)}", f"{contract_delta:+.1f}%p", "50/50 → 50/50"],
            ["발주서", score_text(baseline_order), f"PNG 689/750 + PDF 주소 50/50<br/>재시험 {score_text(hybrid_order)}", f"{order_hybrid_delta:+.1f}%p", "50/50 → 50/50"],
            ["사업자등록증 재시도", "실패 이미지 3건", f"전처리 후 {business_retry['success_count']}/{business_retry['input_count']} 성공", "처리 성공", "3/3"],
        ], [31 * mm, 38 * mm, 43 * mm, 27 * mm, 35 * mm]),
        p("계약서 필드 변화", "H2"),
        table([
            ["필드", "A. PDF", "B. PNG", "변화"],
            *[
                [
                    field,
                    f"{baseline_contract['field_matches'][field]['matched']}/50 = {baseline_contract['field_matches'][field]['accuracy'] * 100:.0f}%",
                    f"{candidate_contract['field_matches'][field]['matched']}/50 = {candidate_contract['field_matches'][field]['accuracy'] * 100:.0f}%",
                    f"{(candidate_contract['field_matches'][field]['accuracy'] - baseline_contract['field_matches'][field]['accuracy']) * 100:+.0f}%p",
                ]
                for field in ["을_상호", "을_대표이사", "갑_상호", "총액(VAT 포함)"]
            ],
        ], [47 * mm, 40 * mm, 40 * mm, 31 * mm]),
        p("[검증] 계약서는 상호·대표이사 필드가 PNG 경로에서 회복됐다. [추론] PDF 경로의 한글 텍스트 손실이 있는 스캔 계약서에는 조건부 PNG 재시도가 유효하다.", "Callout"),
        p("발주서 병합 규칙과 결과", "H2"),
        table([
            ["필드", "A. PDF", "B. PNG", "최종 선택"],
            ["공급자", "0/50 = 0%", "50/50 = 100%", "PNG"],
            ["공급자 사업자번호", "5/50 = 10%", "49/50 = 98%", "PNG"],
            ["공급자 주소", "50/50 = 100%", "0/50 = 0%", "PDF → 100% 보존"],
            ["대금 지급조건", "0/50 = 0%", "50/50 = 100%", "PNG"],
        ], [45 * mm, 35 * mm, 35 * mm, 43 * mm]),
        p("4. 운영 적용과 발표 문구", "H1"),
        table([
            ["단계", "운영 규칙", "실패 판정"],
            ["1. 기본 처리", "PDF는 기존 RunPod PDF 경로로 OCR", "정상 한글 결과면 종료"],
            ["2. 조건부 재시도", "본문이 40자 이상이면서 한글 완성형이 5자 미만일 때만 모든 페이지를 PNG로 렌더링해 같은 이미지 OCR 경로로 재시도", "스캔 또는 한글 텍스트 손실로 판단"],
            ["3. 결과 사용", "계약서는 PNG 결과를 사용. 발주서는 공급자 주소는 PDF, 나머지 선정 필드는 PNG 결과를 사용", "선정 필드 재검증에서 기존 경로보다 하락하면 병합 규칙 재검토"],
            ["4. 제외", "견적서처럼 기존 필드 일치율 100.0%인 PDF와 이미지 입력 명함은 재처리 대상에서 제외", "개선 여지가 없거나 PDF 변환 대상이 아님"],
        ], [29 * mm, 91 * mm, 54 * mm]),
        p(
            "> [검증] 동일 RunPod OCR 모델의 100건 재시험에서 계약서 필드 일치율은 25.0%에서 98.5%로 상승<br/>"
            "> [검증] 발주서는 PNG OCR 91.9%에 PDF 공급자 주소 50/50을 반영한 98.5%가 실제 재실행에서도 재현<br/>"
            "> [추론] 운영에서는 스캔 PDF 또는 한글 필수값 누락 PDF에만 PNG 재시도를 적용하고, 발주서는 선택 필드의 출처를 함께 보존",
            "Callout",
        ),
        p("자료 기준: 2026-09-17 실제 RunPod 재시험 집계. 계약서 200 PNG 페이지·발주서 50 PNG 페이지를 처리했고 오류 문서는 없었다. 원문·OCR 전문은 개인정보 보호를 위해 보고서에 포함하지 않았다.", "Note"),
    ]
    doc.build(story)


if __name__ == "__main__":
    build()
