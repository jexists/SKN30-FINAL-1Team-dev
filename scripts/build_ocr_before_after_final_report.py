"""Create the final before/after OCR validation PDF and slide-reference PNG."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-ocr-before-after")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch
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
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
AB = ROOT / "output/evals/ocr-png-fallback-ab/runpod_png_fallback_ab_summary.json"
FINAL = ROOT / "output/evals/ocr-final-policy/runpod_final_policy_summary.json"
BASELINE = ROOT / "output/evals/ocr-runpod/runpod_dataset_summary.json"
PRODUCT = ROOT / "output/evals/ocr-product-description/runpod_product_description_summary.json"
PRODUCT_FALLBACK = ROOT / "output/evals/ocr-product-description/runpod_product_description_failure_png_check.json"
OUT_PDF = ROOT / "output/pdf/ocr-before-after-final-report-20260917.pdf"
OUT_IMAGE = ROOT / "output/images/ocr-before-after-slide-reference-20260917.png"
TMP = ROOT / "tmp/pdfs/ocr-before-after-final"
DETAIL_CHART = TMP / "ocr-before-after-detail.png"
FONT_PATH = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

pdfmetrics.registerFont(TTFont("AppleGothic", FONT_PATH))

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#2869D8")
GREEN = colors.HexColor("#0C8A6D")
SKY = colors.HexColor("#EAF2FF")
MINT = colors.HexColor("#E7F7F1")
TEXT = colors.HexColor("#27384A")
GRAY = colors.HexColor("#627283")
LIGHT = colors.HexColor("#F5F7FA")
LINE = colors.HexColor("#D7DFE8")
MUTED = colors.HexColor("#91A5BC")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleKr", parent=styles["Title"], fontName="AppleGothic", fontSize=22, leading=28, textColor=NAVY, spaceAfter=3))
styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontName="AppleGothic", fontSize=9.1, leading=13, textColor=GRAY, spaceAfter=8))
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="AppleGothic", fontSize=13.4, leading=17, textColor=NAVY, spaceBefore=4, spaceAfter=5))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontName="AppleGothic", fontSize=10.3, leading=13.5, textColor=BLUE, spaceBefore=5, spaceAfter=3))
styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.45, leading=12, textColor=TEXT, spaceAfter=3))
styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.25, leading=9.35, textColor=TEXT))
styles.add(ParagraphStyle(name="Header", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.15, leading=9.2, textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.7, leading=12.4, textColor=NAVY, backColor=SKY, borderColor=BLUE, borderWidth=0.5, borderPadding=7, spaceAfter=6))
styles.add(ParagraphStyle(name="Note", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.0, leading=9.35, textColor=GRAY, spaceAfter=2))


def p(value: str, style: str = "Body") -> Paragraph:
    return Paragraph(value, styles[style])


def value_pair(dataset: dict) -> tuple[int, int]:
    values = dataset["field_matches"].values()
    return sum(item["matched"] for item in values), sum(item["labeled"] for item in values)


def pct(matched: int, total: int) -> float:
    return matched / total * 100


def table(rows: list[list[str]], widths: list[float], *, header: bool = True) -> Table:
    converted = []
    for row_index, row in enumerate(rows):
        style = "Header" if header and row_index == 0 else "Cell"
        converted.append([p(value, style) for value in row])
    result = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.2),
        ("TOPPADDING", (0, 0), (-1, -1), 3.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.8),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    start = 1 if header else 0
    for index in range(start, len(rows)):
        if (index - start) % 2 == 1:
            commands.append(("BACKGROUND", (0, index), (-1, index), LIGHT))
    result.setStyle(TableStyle(commands))
    return result


def metric_card(label: str, value: str, note: str, color: colors.Color) -> Table:
    item = Table([[p(label, "Note")], [p(value, "TitleKr")], [p(note, "Note")]], colWidths=[55 * mm])
    item.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, color),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    return item


def draw_slide_reference(metrics: list[dict], core_before: float, core_after: float) -> None:
    OUT_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    font = FontProperties(fname=FONT_PATH)
    bold = FontProperties(fname=FONT_PATH, weight="bold")
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor="white")
    canvas = fig.add_axes([0, 0, 1, 1])
    canvas.set_axis_off()
    canvas.set_xlim(0, 16)
    canvas.set_ylim(0, 9)
    canvas.text(0.8, 8.25, "OCR 고도화 전후 비교", fontproperties=bold, fontsize=27, color="#17324D")
    canvas.text(0.8, 7.84, "RunPod OCR | 동일 표본과 동일 선정 정답값으로 1차 테스트와 최종 재시험을 비교", fontproperties=font, fontsize=11, color="#627283")
    canvas.plot([0.8, 15.2], [7.55, 7.55], color="#2869D8", linewidth=2)
    canvas.text(0.8, 6.95, "핵심 구조화 문서 필드 일치율", fontproperties=font, fontsize=12, color="#627283")
    canvas.text(0.8, 5.83, f"{core_before:.1f}%", fontproperties=bold, fontsize=43, color="#91A5BC")
    canvas.text(4.10, 6.06, "→", fontproperties=bold, fontsize=32, color="#2869D8")
    canvas.text(4.95, 5.83, f"{core_after:.1f}%", fontproperties=bold, fontsize=43, color="#0C8A6D")
    canvas.add_patch(FancyBboxPatch((8.95, 5.95), 2.20, 0.85, boxstyle="round,pad=0.12,rounding_size=0.11", facecolor="#E7F7F1", edgecolor="#0C8A6D", linewidth=1.2))
    canvas.text(10.05, 6.28, f"+{core_after - core_before:.1f}%p", ha="center", va="center", fontproperties=bold, fontsize=17, color="#0C8A6D")
    canvas.text(0.83, 5.40, "견적서·계약서·발주서 150건, 선정 필드 1,150개 기준", fontproperties=font, fontsize=10, color="#627283")
    card_y = 3.52
    card_width = 3.44
    for index, item in enumerate(metrics):
        x = 0.8 + index * 3.65
        canvas.add_patch(FancyBboxPatch((x, card_y), card_width, 1.28, boxstyle="round,pad=0.10,rounding_size=0.10", facecolor="#F7F9FC", edgecolor="#D7DFE8", linewidth=1))
        canvas.text(x + 0.22, card_y + 0.93, item["name"], fontproperties=bold, fontsize=12, color="#17324D")
        canvas.text(x + 0.22, card_y + 0.49, f"{item['before']:.1f}%  →  {item['after']:.1f}%", fontproperties=font, fontsize=14, color="#27384A")
        canvas.text(x + card_width - 0.20, card_y + 0.18, f"+{item['delta']:.1f}%p", ha="right", fontproperties=bold, fontsize=11, color="#0C8A6D")
    canvas.text(0.8, 2.75, "고도화 방법", fontproperties=bold, fontsize=15, color="#17324D")
    steps = [
        ("1차", "원본 PDF OCR", "스캔 PDF의 한글·표 영역 누락"),
        ("개선", "조건부 PNG 재시도", "한글 누락 또는 PDF 작업 실패일 때만 모든 페이지 렌더링"),
        ("최종", "필드별 결과 선택", "발주서 공급자 주소는 PDF 결과 보존"),
    ]
    for index, (label, title, desc) in enumerate(steps):
        x = 0.8 + index * 4.85
        canvas.add_patch(FancyBboxPatch((x, 1.27), 4.25, 0.95, boxstyle="round,pad=0.09,rounding_size=0.08", facecolor="#FFFFFF", edgecolor="#D7DFE8", linewidth=1))
        canvas.text(x + 0.18, 1.83, label, fontproperties=bold, fontsize=10, color="#2869D8")
        canvas.text(x + 0.18, 1.55, title, fontproperties=bold, fontsize=12, color="#17324D")
        canvas.text(x + 0.18, 1.32, desc, fontproperties=font, fontsize=8.5, color="#627283")
        if index < 2:
            canvas.text(x + 4.42, 1.65, "→", fontproperties=bold, fontsize=18, color="#2869D8")
    canvas.text(0.8, 0.55, "제품설명서: 파일명 기반 제품 식별자 일치율 84.0% → 86.0% | 명함·사업자등록증·엑셀은 별도 지표로 관리", fontproperties=font, fontsize=9, color="#627283")
    fig.savefig(OUT_IMAGE, dpi=120, facecolor="white", bbox_inches=None)
    plt.close(fig)


def draw_detail_chart(metrics: list[dict]) -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    font = FontProperties(fname=FONT_PATH)
    bold = FontProperties(fname=FONT_PATH, weight="bold")
    labels = [item["name"] for item in metrics]
    before = [item["before"] for item in metrics]
    after = [item["after"] for item in metrics]
    positions = list(range(len(metrics)))
    fig, axis = plt.subplots(figsize=(8.8, 3.4), dpi=180, facecolor="white")
    width = 0.30
    axis.bar([x - width / 2 for x in positions], before, width, label="1차 테스트", color="#91A5BC")
    axis.bar([x + width / 2 for x in positions], after, width, label="최종 테스트", color="#0C8A6D")
    for x, value in zip([x - width / 2 for x in positions], before):
        axis.text(x, value + 3.0, f"{value:.1f}", ha="center", fontsize=9, color="#17324D")
    for x, value in zip([x + width / 2 for x in positions], after):
        axis.text(x, value + 3.0, f"{value:.1f}", ha="center", fontsize=9, fontweight="bold", color="#0C6A54")
    axis.set_ylim(0, 114)
    axis.set_xticks(positions, labels, fontproperties=font, fontsize=10)
    axis.set_ylabel("일치율 (%)", fontproperties=font, fontsize=10)
    axis.grid(axis="y", color="#D7DFE8", linewidth=0.7)
    axis.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        axis.spines[spine].set_visible(False)
    axis.tick_params(axis="y", left=False)
    axis.legend(prop=font, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.13))
    fig.tight_layout()
    fig.savefig(DETAIL_CHART, dpi=180, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("AppleGothic", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9 * mm, "SalesLuv | OCR 고도화 전후 최종 결과보고서 | 2026-09-17")
    canvas.drawRightString(192 * mm, 9 * mm, str(doc.page))
    canvas.restoreState()


def build() -> None:
    ab = json.loads(AB.read_text(encoding="utf-8"))
    final = json.loads(FINAL.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    product = json.loads(PRODUCT.read_text(encoding="utf-8"))
    product_fallback = json.loads(PRODUCT_FALLBACK.read_text(encoding="utf-8"))

    quote_before, quote_total = value_pair(baseline["datasets"]["견적서"])
    contract_before, contract_total = value_pair(ab["baseline"]["계약서"])
    po_before, po_total = value_pair(ab["baseline"]["발주서"])
    contract_after, _ = value_pair(final["datasets"]["계약서"])
    po_after, _ = value_pair(final["datasets"]["발주서"])
    product_before = product["dataset"]["product_identifier"]["matched"]
    product_total = product["dataset"]["input_count"]
    product_after = product_before + int(bool(product_fallback["matched"]))
    assert (quote_before, quote_total) == (200, 200)
    assert (contract_before, contract_total, contract_after) == (50, 200, 197)
    assert (po_before, po_total, po_after) == (502, 750, 739)
    assert (product_before, product_total, product_after) == (42, 50, 43)

    metrics = [
        {"name": "견적서", "before": pct(quote_before, quote_total), "after": pct(quote_before, quote_total)},
        {"name": "계약서", "before": pct(contract_before, contract_total), "after": pct(contract_after, contract_total)},
        {"name": "발주서", "before": pct(po_before, po_total), "after": pct(po_after, po_total)},
        {"name": "상품설명서", "before": pct(product_before, product_total), "after": pct(product_after, product_total)},
    ]
    for item in metrics:
        item["delta"] = item["after"] - item["before"]
    core_before_count = quote_before + contract_before + po_before
    core_after_count = quote_before + contract_after + po_after
    core_total = quote_total + contract_total + po_total
    core_before = pct(core_before_count, core_total)
    core_after = pct(core_after_count, core_total)
    assert (core_before_count, core_after_count, core_total) == (752, 1136, 1150)

    draw_slide_reference(metrics, core_before, core_after)
    draw_detail_chart(metrics)
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(OUT_PDF), pagesize=A4, title="OCR 고도화 전후 최종 결과보고서", leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=20 * mm)
    frame = Frame(18 * mm, 20 * mm, 174 * mm, 257 * mm, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])

    story = [
        p("OCR 고도화 전후 최종 결과보고서", "TitleKr"),
        p("1차 테스트의 병목을 확인하고, 조건부 PNG 재시도와 필드별 결과 선택을 적용한 최종 재시험 결과", "Sub"),
        HRFlowable(width="100%", thickness=1.1, color=BLUE, spaceAfter=7),
        p("핵심 결과", "H1"),
        p(f"핵심 구조화 문서 150건의 선정 필드 일치율은 1차 {core_before_count}/{core_total} = {core_before:.1f}%에서 최종 {core_after_count}/{core_total} = {core_after:.1f}%로 {core_after - core_before:+.1f}%p 개선됐다. 계약서와 발주서의 한글·표 영역 손실을 조건부 이미지 OCR로 보완했고, 발주서 공급자 주소는 PDF 결과를 보존했다.", "Callout"),
        Table([[metric_card("핵심 구조화 문서", f"{core_after:.1f}%", f"1차 대비 {core_after - core_before:+.1f}%p", GREEN), metric_card("계약서", f"{metrics[1]['after']:.1f}%", f"1차 대비 {metrics[1]['delta']:+.1f}%p", BLUE), metric_card("발주서", f"{metrics[2]['after']:.1f}%", f"1차 대비 {metrics[2]['delta']:+.1f}%p", GREEN)]], colWidths=[58 * mm, 58 * mm, 58 * mm]),
        Spacer(1, 8),
        Image(str(OUT_IMAGE), width=174 * mm, height=98 * mm),
        p("요약 이미지에는 제품설명서의 별도 식별자 지표도 함께 표시했다. 상세 비교와 테스트 설계는 다음 페이지에 제시한다.", "Note"),
        PageBreak(),
        p("1. 테스트 대상과 방법", "H1"),
        table([
            ["대상", "표본", "비교 단위", "1차 경로", "최종 경로"],
            ["견적서", "50건", "고객사명·견적일자·견적번호·총액", "원본 PDF OCR", "원본 PDF OCR 유지"],
            ["계약서", "50건", "상호·대표이사·상대 상호·총액", "원본 PDF OCR", "한글 누락 시 모든 페이지 PNG OCR"],
            ["발주서", "50건", "공급자·발주자·납품·지급·총액 등 15개", "원본 PDF OCR", "PNG OCR, 공급자 주소만 PDF 결과 보존"],
            ["상품설명서", "50건", "파일명 기반 제품 식별자 1개", "원본 PDF OCR", "PDF 작업 실패 문서만 PNG OCR 재시도"],
        ], [24 * mm, 17 * mm, 49 * mm, 38 * mm, 46 * mm]),
        p("평가 방식", "H2"),
        table([
            ["항목", "설정"],
            ["OCR 워커", "동일 RunPod Serverless OCR 워커(`salesluv` 내부 계약)와 동일 한국어 이미지 모델 번들을 사용"],
            ["공정성", "같은 원본 문서와 같은 선정 정답값으로 비교. 원문과 OCR 전문은 결과 파일에 저장하지 않음"],
            ["판정", "정규화한 정답값이 OCR 본문에 포함되면 일치. 일치율 = 일치 항목 수 ÷ 정답 항목 수"],
            ["PNG 렌더링", "재시도 시 PDF의 모든 페이지를 최대 긴 변 2,200px으로 렌더링하고, 전송 한도 초과 시 1,100px까지 축소"],
            ["지표 범위", "선정 필드 일치율 또는 제품 식별자 일치율. 문자 단위 전사 정확도, CER/WER, 필드 좌표 정확도는 포함하지 않음"],
        ], [31 * mm, 143 * mm]),
        p("고도화 흐름", "H2"),
        table([
            ["단계", "처리", "의도"],
            ["1차", "원본 PDF를 RunPod PDF OCR로 처리", "기준 성능과 누락 필드 확인"],
            ["조건부 재시도", "한글 필수값 누락 또는 PDF OCR 작업 실패일 때만 모든 페이지를 PNG로 변환해 같은 RunPod 이미지 OCR로 처리", "스캔 PDF의 텍스트·표 영역 복구"],
            ["결과 선택", "발주서 공급자 주소는 PDF 결과, 나머지 선정 필드는 PNG 결과를 사용", "PNG 경로에서 발생한 주소 하락 방지"],
        ], [28 * mm, 93 * mm, 53 * mm]),
        p("비교 해석 원칙", "H2"),
        p("1차와 최종은 같은 문서와 같은 선정 정답값을 사용했다. 문서마다 최종 경로를 사전에 고정해 비교했으며, 최종 점수는 여러 OCR 결과 중 더 높은 값을 임의로 선택한 수치가 아니다. 제품설명서는 필드 집계가 아닌 문서별 제품 식별자 존재 여부로 별도 계산했다.", "Callout"),
        PageBreak(),
        p("2. 1차와 최종 결과 비교", "H1"),
        Image(str(DETAIL_CHART), width=174 * mm, height=67 * mm),
        table([
            ["대상", "1차 테스트", "최종 테스트", "변화", "최종 적용"],
            ["견적서", "200/200 = 100.0%", "200/200 = 100.0%", "0.0%p", "PDF 경로 유지"],
            ["계약서", "50/200 = 25.0%", "197/200 = 98.5%", "+73.5%p", "조건부 PNG OCR"],
            ["발주서", "502/750 = 66.9%", "739/750 = 98.5%", "+31.6%p", "PNG OCR + PDF 주소 보존"],
            ["상품설명서", "42/50 = 84.0%", "43/50 = 86.0%", "+2.0%p", "PDF 실패 시 PNG OCR"],
            ["핵심 구조화 문서", f"{core_before_count}/{core_total} = {core_before:.1f}%", f"{core_after_count}/{core_total} = {core_after:.1f}%", f"+{core_after - core_before:.1f}%p", "견적서·계약서·발주서 합산"],
        ], [28 * mm, 35 * mm, 35 * mm, 22 * mm, 54 * mm]),
        p("결과 해석", "H1"),
        p("계약서는 PDF 경로에서 상호·대표이사·상대 상호가 누락됐고 PNG OCR 적용 후 회복됐다. 발주서는 공급자·지급조건·표 영역이 개선됐지만 공급자 주소는 PNG OCR에서 하락해 PDF 결과를 선택했다. 견적서는 이미 100.0%였으므로 PNG 재처리 대상에서 제외했다.", "Callout"),
        p("3. 별도 관리 대상", "H1"),
        table([
            ["기능", "현재 확인 결과", "전후 비교 포함 여부", "다음 검증 기준"],
            ["명함 고객 등록", "OCR 필드 일치 127/134 = 94.8%", "이미지 입력이라 PDF-to-PNG 개선 대상 아님", "회사명·이름·전화·이메일 필드별 정답지 유지"],
            ["사업자등록증 고객 등록", "초기 21/24 처리 후 실패 3건 전처리 재시도 성공", "독립 필드 정답지가 없어 정확도 비교 제외", "상호·사업자번호·대표자·주소 정답지 구축"],
            ["엑셀 고객 등록", "OCR 기능이 아닌 파일 파싱·등록 기능", "OCR 전후 비교 대상 아님", "허용·거절·중복·필수값 검증률"],
        ], [31 * mm, 49 * mm, 46 * mm, 48 * mm]),
        p("발표용 결론: 스캔 또는 한글 필수값 누락 PDF에만 PNG 이미지 OCR을 재시도하고, 문서별 취약 필드는 기존 PDF 결과를 보존하는 방식으로 정확도를 개선했다. 전체 전사 정확도나 사양 값 자동 등록 정확도는 별도 사람 검수 정답지로 추가 측정해야 한다.", "Callout"),
        p("자료 기준: 2026-09-17 RunPod 실제 재시험 집계. 수치는 각 문서 유형의 선정 정답값과 OCR 본문 포함 여부를 비교해 계산했다.", "Note"),
    ]
    doc.build(story)


if __name__ == "__main__":
    build()
