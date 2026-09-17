"""Build the presentation-ready RunPod PDF-to-PNG OCR A/B report."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "output/evals/ocr-png-fallback-ab/runpod_png_fallback_ab_summary.json"
OUTPUT = ROOT / "output/pdf/ocr-png-fallback-ab-report-20260916.pdf"
FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

pdfmetrics.registerFont(TTFont("AppleGothic", FONT))
data = json.loads(SUMMARY.read_text(encoding="utf-8"))

NAVY = colors.HexColor("#18324B")
BLUE = colors.HexColor("#2D6CDF")
PALE = colors.HexColor("#EAF2FF")
GRAY = colors.HexColor("#5E6B78")
LIGHT = colors.HexColor("#F5F7FA")
TEXT = colors.HexColor("#243444")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleKr", parent=styles["Title"], fontName="AppleGothic", fontSize=22, leading=28, textColor=NAVY, alignment=TA_LEFT, spaceAfter=4))
styles.add(ParagraphStyle(name="Subtitle", parent=styles["Normal"], fontName="AppleGothic", fontSize=9.3, leading=13, textColor=GRAY, spaceAfter=6))
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="AppleGothic", fontSize=13.5, leading=17, textColor=NAVY, spaceBefore=3, spaceAfter=5))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontName="AppleGothic", fontSize=10.3, leading=13.5, textColor=BLUE, spaceBefore=6, spaceAfter=3))
styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.5, leading=12, textColor=TEXT, spaceAfter=3))
styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.15, leading=9.3, textColor=TEXT))
styles.add(ParagraphStyle(name="Header", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.15, leading=9.2, textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.7, leading=12.4, textColor=NAVY, backColor=PALE, borderColor=BLUE, borderWidth=0.5, borderPadding=6, spaceAfter=6))
styles.add(ParagraphStyle(name="Note", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.05, leading=9.5, textColor=GRAY, spaceAfter=2))


def p(text: str, style: str = "Body") -> Paragraph:
    return Paragraph(text, styles[style])


def table(rows: list[list[object]], widths: list[float], *, header: bool = True) -> Table:
    rendered = []
    for row_number, row in enumerate(rows):
        style = "Header" if header and row_number == 0 else "Cell"
        rendered.append([cell if hasattr(cell, "wrap") else p(str(cell), style) for cell in row])
    value = Table(rendered, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8DEE7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    for index in range(1 if header else 0, len(rows)):
        if index % 2 == 0:
            commands.append(("BACKGROUND", (0, index), (-1, index), LIGHT))
    value.setStyle(TableStyle(commands))
    return value


def field_total(dataset: dict) -> tuple[int, int]:
    values = dataset["field_matches"].values()
    return sum(item["matched"] for item in values), sum(item["labeled"] for item in values)


def percent(dataset: dict) -> float:
    matched, labeled = field_total(dataset)
    return matched / labeled * 100


def fmt(dataset: dict) -> str:
    matched, labeled = field_total(dataset)
    return f"{matched}/{labeled} = {percent(dataset):.1f}%"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D8DEE7"))
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("AppleGothic", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9 * mm, "SalesLuv | RunPod PDF→PNG OCR A/B 검증 | 2026-09-16")
    canvas.drawRightString(192 * mm, 9 * mm, str(doc.page))
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame = Frame(18 * mm, 20 * mm, 174 * mm, 257 * mm, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=20 * mm, title="RunPod PDF→PNG OCR A/B 검증 결과")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])

    contract_base = data["baseline"]["계약서"]
    contract_image = data["candidate"]["계약서"]
    order_base = data["baseline"]["발주서"]
    order_image = data["candidate"]["발주서"]
    business = data["business_license_retry"]
    contract_delta = percent(contract_image) - percent(contract_base)
    order_delta = percent(order_image) - percent(order_base)

    story = [
        p("RunPod PDF→PNG OCR A/B 검증 보고서", "TitleKr"),
        p("동일 OCR 모델에서 PDF 입력 경로와 렌더링 PNG 이미지 경로를 비교한 발표용 결과", "Subtitle"),
        HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=7),
        p("결론", "H1"),
        p(
            f"[검증] 동일 RunPod OCR 모델에서 PNG 경로의 선정 필드 일치율은 계약서 25.0%→98.5%(+{contract_delta:.1f}%p), 발주서 66.9%→91.9%(+{order_delta:.1f}%p)로 상승했다. 계약서에는 조건부 PNG 재시도가 유효하다. 발주서는 공급자 주소가 100.0%→0.0%로 하락해 모든 PDF를 PNG로 일괄 전환하면 안 된다.",
            "Callout",
        ),
        p("1. 테스트 모델과 진행 방법", "H1"),
        table([
            ["항목", "실행 내용", "통제 기준"],
            ["OCR 모델", "RunPod Serverless의 동일 PaddleOCR 기반 워커·한국어 이미지 모델 번들", "모델·프롬프트·정답지·샘플은 변경하지 않음"],
            ["기준 경로 A", "원본 PDF를 RunPod PDF 입력으로 전달", "기존 2026-09-15 집계값"],
            ["비교 경로 B", "PDF의 모든 페이지를 PNG로 렌더링해 같은 RunPod 이미지 OCR로 전달", "긴 변 2,200px, 인라인 한도 초과 시 1,100px까지 축소"],
            ["표본", "계약서 50건·200페이지, 발주서 50건·50페이지", "문서별 XLSX 정답 필드를 같은 파일명으로 연결"],
            ["동시성", "RunPod 요청 최대 2건", "운영 OCR 설정과 동일"],
        ], [30*mm, 84*mm, 60*mm]),
        Spacer(1, 6),
        p("2. 판정 기준", "H1"),
        table([
            ["단계", "방법", "판정"],
            ["처리 성공", "RunPod가 문서(또는 해당 PDF의 모든 페이지)에 정상 OCR 응답", "성공 문서 수 ÷ 입력 문서 수"],
            ["필드 일치", "정답과 OCR 본문을 NFKC·공백·구두점 정규화 후 비교", "정답값이 OCR 본문에 포함되면 일치"],
            ["집계", "문서별 선정 필드의 일치 수를 합산", "일치 필드 수 ÷ 라벨 필드 수"],
        ], [30*mm, 85*mm, 59*mm]),
        p("[검증] 이 수치는 필드 위치 또는 사람이 검수한 전체 전사 정확도가 아니라, 선정 정답값의 본문 포함 여부를 계산한 필드 일치율이다. 원문과 OCR 본문은 결과 파일에 저장하지 않았다.", "Note"),
        Spacer(1, 5),
        p("3. 전체 결과", "H1"),
        table([
            ["대상", "A: PDF 경로", "B: PNG 이미지 경로", "변화", "처리 성공"],
            ["계약서", fmt(contract_base), fmt(contract_image), f"+{contract_delta:.1f}%p", "50/50 → 50/50"],
            ["발주서", fmt(order_base), fmt(order_image), f"+{order_delta:.1f}%p", "50/50 → 50/50"],
        ], [25*mm, 37*mm, 43*mm, 27*mm, 42*mm]),
        p("[검증] 계약서는 200페이지, 발주서는 50페이지를 PNG로 렌더링해 비교했다. B 경로는 계약서 197/200, 발주서 689/750 필드가 일치했다.", "Note"),
        PageBreak(),
        p("4. 필드별 결과와 해석", "H1"),
        p("계약서 50건 · 선정 4개 필드", "H2"),
        table([
            ["필드", "A: PDF", "B: PNG", "변화"],
            *[
                [
                    field,
                    f"{contract_base['field_matches'][field]['matched']}/50 = {contract_base['field_matches'][field]['accuracy']*100:.1f}%",
                    f"{contract_image['field_matches'][field]['matched']}/50 = {contract_image['field_matches'][field]['accuracy']*100:.1f}%",
                    f"{(contract_image['field_matches'][field]['accuracy']-contract_base['field_matches'][field]['accuracy'])*100:+.1f}%p",
                ]
                for field in ["을_상호", "을_대표이사", "갑_상호", "총액(VAT 포함)"]
            ],
        ], [39*mm, 41*mm, 41*mm, 31*mm]),
        p("[검증] 계약서에서 상호·대표이사 필드가 PNG 경로로 회복됐다. 조건부 재시도의 직접 적용 대상으로 판단한다.", "Callout"),
        p("발주서 50건 · 선정 15개 필드", "H2"),
        table([
            ["필드", "A: PDF", "B: PNG", "변화"],
            *[
                [
                    field,
                    f"{order_base['field_matches'][field]['accuracy']*100:.0f}%",
                    f"{order_image['field_matches'][field]['accuracy']*100:.0f}%",
                    f"{(order_image['field_matches'][field]['accuracy']-order_base['field_matches'][field]['accuracy'])*100:+.0f}%p",
                ]
                for field in order_base["field_matches"]
            ],
        ], [53*mm, 34*mm, 34*mm, 31*mm]),
        p("[검증] PNG 경로는 공급자·담당자·지급조건 등을 개선했지만 공급자 주소는 100%→0%로 하락했다. [추론] 주소가 필요한 업무에서는 PDF·PNG 결과를 필드 단위로 비교·선택하는 병합 규칙이 필요하다.", "Callout"),
        p("5. 구현과 운영 기준", "H1"),
        table([
            ["항목", "적용 내용", "실패 판정·대응"],
            ["트리거", "한국어 설정의 RunPod PDF 결과가 40자 이상이면서 한글 완성형이 5자 미만일 때만 재시도", "정상 한글 PDF에는 PNG 재시도를 하지 않음"],
            ["재처리", "모든 PDF 페이지를 PNG로 렌더링 후 동일 RunPod 이미지 경로로 OCR", "페이지 하나라도 실패하면 기존 원격 장애 fallback을 적용"],
            ["전환 범위", "계약서형 한글 깨짐 PDF에 우선 적용", "발주서처럼 일부 필드 하락이 보이면 원본 결과 보존·필드 병합 검증 후 확대"],
            ["사업자등록증", f"실패 3건을 EXIF 보정·RGB 변환·2,400px 축소·PNG 재인코딩 후 재시도: {business['success_count']}/{business['input_count']} 성공", "독립 정답지가 없어 필드 정확도는 미산출"],
        ], [31*mm, 82*mm, 61*mm]),
        Spacer(1, 6),
        p("6. 해석 한계와 다음 검증", "H1"),
        p("[미확인] 사람 전사 골드셋이 없으므로 정식 CER/WER은 이번 A/B에서 산출하지 않았다. [추론] 전체 문자 정확도를 발표하려면 계약서·발주서·사업자등록증별 사람 검수 전사본을 만들고, 동일 표본에서 CER·WER을 재계산해야 한다.", "Callout"),
        p("PPT 삽입 문구", "H2"),
        p(
            "> [검증] 동일 RunPod OCR 모델의 PDF→PNG 경로 A/B 결과, 계약서 필드 일치율은 25.0%에서 98.5%로 상승<br/>"
            "> [검증] 발주서는 66.9%에서 91.9%로 상승했으나 공급자 주소는 100.0%에서 0.0%로 하락<br/>"
            "> [검증] 따라서 한글 깨짐 PDF에만 조건부 PNG 재시도를 적용하고, 발주서는 필드 병합 검증 후 확대",
            "Callout",
        ),
    ]
    doc.build(story)


if __name__ == "__main__":
    build()
