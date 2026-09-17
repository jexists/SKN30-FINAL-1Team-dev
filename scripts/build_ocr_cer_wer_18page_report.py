"""Build the presentation-ready formal OCR CER/WER report for the reviewed sample."""

from __future__ import annotations

import json
from pathlib import Path

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
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "output/evals/ocr-cer-wer/cer_wer_summary.json"
CAPTURE = ROOT / "output/evals/ocr-cer-wer/hypothesis_capture_summary.json"
OUTPUT = ROOT / "output/pdf/ocr-cer-wer-18page-report-20260916.pdf"
FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

pdfmetrics.registerFont(TTFont("AppleGothic", FONT))
score = json.loads(SUMMARY.read_text(encoding="utf-8"))
capture = json.loads(CAPTURE.read_text(encoding="utf-8"))

NAVY = colors.HexColor("#18324B")
BLUE = colors.HexColor("#2D6CDF")
PALE = colors.HexColor("#EAF2FF")
GRAY = colors.HexColor("#5E6B78")
LIGHT = colors.HexColor("#F5F7FA")
TEXT = colors.HexColor("#243444")
LINE = colors.HexColor("#D8DEE7")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleKr", parent=styles["Title"], fontName="AppleGothic", fontSize=21, leading=27, textColor=NAVY, spaceAfter=4))
styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontName="AppleGothic", fontSize=9.2, leading=13, textColor=GRAY, spaceAfter=6))
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="AppleGothic", fontSize=13.2, leading=17, textColor=NAVY, spaceBefore=4, spaceAfter=5))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontName="AppleGothic", fontSize=10.1, leading=13, textColor=BLUE, spaceBefore=5, spaceAfter=3))
styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.45, leading=12, textColor=TEXT, spaceAfter=3))
styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.2, leading=9.5, textColor=TEXT))
styles.add(ParagraphStyle(name="Header", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.2, leading=9.2, textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.65, leading=12.4, textColor=NAVY, backColor=PALE, borderColor=BLUE, borderWidth=0.5, borderPadding=6, spaceAfter=6))
styles.add(ParagraphStyle(name="Note", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.0, leading=9.4, textColor=GRAY, spaceAfter=2))


def p(text: str, style: str = "Body") -> Paragraph:
    return Paragraph(text, styles[style])


def table(rows: list[list[object]], widths: list[float], *, header: bool = True) -> Table:
    cells = []
    for row_index, row in enumerate(rows):
        style = "Header" if header and row_index == 0 else "Cell"
        cells.append([value if hasattr(value, "wrap") else p(str(value), style) for value in row])
    result = Table(cells, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.7),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    for row_index in range(1 if header else 0, len(rows)):
        if row_index % 2 == 0:
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), LIGHT))
    result.setStyle(TableStyle(commands))
    return result


def rate(value: float | None) -> str:
    return "미산출" if value is None else f"{value * 100:.1f}%"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("AppleGothic", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9 * mm, "SalesLuv | OCR CER/WER 소표본 검증 | 2026-09-16")
    canvas.drawRightString(192 * mm, 9 * mm, str(doc.page))
    canvas.restoreState()


def build():
    overall = score["overall"]
    by_type = score["by_document_type"]
    sample = score["sample"]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame = Frame(18 * mm, 20 * mm, 174 * mm, 257 * mm, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=20 * mm,
        title="OCR CER/WER 정식 검증 결과",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])

    story = [
        p("OCR CER/WER 정식 검증 결과", "TitleKr"),
        p("사람이 확정한 18페이지 전사 골드셋과 OCR 출력의 전체 문자·단어 비교", "Sub"),
        HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=7),
        p("결론", "H1"),
        p(
            f"[검증] 총 18페이지의 확정 전사본과 OCR 출력을 비교한 결과, 전체 CER은 {rate(overall['cer'])}, WER은 {rate(overall['wer'])}다. CER과 WER은 낮을수록 좋다. 이 결과는 OCR 본문 전체의 편집거리 기준이며, 선정 필드 일치율과는 다른 지표다.",
            "Callout",
        ),
        p("1. 정식 CER/WER 결과", "H1"),
        table([
            ["문서 유형", "페이지", "CER", "WER", "문자 편집거리 / 정답 문자", "단어 편집거리 / 정답 단어"],
            ["전체", overall["page_count"], rate(overall["cer"]), rate(overall["wer"]), f"{overall['char_distance']:,} / {overall['char_reference']:,}", f"{overall['word_distance']:,} / {overall['word_reference']:,}"],
            *[
                [
                    document_type,
                    result["page_count"],
                    rate(result["cer"]),
                    rate(result["wer"]),
                    f"{result['char_distance']:,} / {result['char_reference']:,}",
                    f"{result['word_distance']:,} / {result['word_reference']:,}",
                ]
                for document_type, result in by_type.items()
            ],
        ], [29 * mm, 16 * mm, 18 * mm, 18 * mm, 47 * mm, 46 * mm]),
        Spacer(1, 5),
        p("지표 해석", "H2"),
        table([
            ["항목", "계산식", "해석"],
            ["CER", "문자 편집거리 ÷ 정답 문자 수", "문자 단위 오류율. 낮을수록 원문과 가깝다."],
            ["WER", "단어 편집거리 ÷ 정답 단어 수", "공백으로 나눈 단어 단위 오류율. 삽입 오류가 많으면 100%를 넘을 수 있다."],
            ["정규화", "Unicode NFKC + 공백 연속 축소", "문자·숫자·구두점은 유지해 표·서식의 원문 보존 차이도 오류에 반영했다."],
        ], [26 * mm, 59 * mm, 89 * mm]),
        p("[검증] 발주서 WER 101.7%는 계산 오류가 아니다. OCR 단어 삽입과 치환·삭제의 합이 정답 단어 수보다 큰 경우 WER은 100%를 넘을 수 있다.", "Note"),
        p("2. 테스트 모델과 진행 방법", "H1"),
        table([
            ["구분", "실행 내용", "판정 기준"],
            ["OCR 모델", "백엔드 OCR 어댑터의 RunPod OCR 경로. 한국어 PDF 결과가 비정상일 때 조건부 PDF-to-PNG 재시도를 적용.", "동일 설정으로 저장한 OCR 출력"],
            ["OCR 출력 수집", f"원본 124문서·277페이지 OCR 출력을 수집. 오류 문서 {capture['error_document_count']}건.", "사람 전사 표본 18페이지의 OCR 출력만 점수에 사용"],
            ["골드셋", "계약서·발주서·사업자등록증 각 6페이지를 1차·2차 전사 후 확정 전사로 검수.", "확정 상태 18/18페이지"],
            ["비교", "확정 전사 전체 텍스트와 OCR 전체 텍스트를 페이지 단위로 연결해 코퍼스 편집거리 집계.", "CER·WER 산출"],
        ], [28 * mm, 86 * mm, 60 * mm]),
        PageBreak(),
        p("3. 결과 해석", "H1"),
        table([
            ["관측", "판단"],
            [f"사업자등록증 CER {rate(by_type['사업자등록증']['cer'])}", "이번 표본에서는 세 유형 중 문자 오류율이 가장 낮았다. 다만 6페이지 결과이므로 전체 사업자등록증 성능으로 일반화할 수 없다."],
            [f"계약서 CER {rate(by_type['계약서']['cer'])}", "계약 조항·당사자 정보 등 전체 본문에서 OCR 차이가 크게 남아 있다. 선정 필드만 맞아도 전체 문자 품질이 높다는 뜻은 아니다."],
            [f"발주서 CER {rate(by_type['발주서']['cer'])}, WER {rate(by_type['발주서']['wer'])}", "표·공급자 정보·조건 문구에서 단어 단위 삽입·삭제가 많이 발생한 것으로 해석할 수 있다. 원인 필드는 개별 오류 분석이 필요하다."],
        ], [55 * mm, 119 * mm]),
        p("[추론] 본 CER/WER은 전체 문자를 비교하므로, 이전의 ‘선정 정답값이 OCR 본문에 포함되는지’ 기준 필드 일치율보다 엄격하다. 두 수치를 직접 같은 정확도로 비교하면 안 된다.", "Callout"),
        p("4. 발표 시 한계와 표기", "H1"),
        table([
            ["항목", "발표 표기"],
            ["표본 범위", "계약서·발주서·사업자등록증 각 6페이지, 총 18페이지의 고정 층화 소표본"],
            ["전사 검수", "단일 검수자의 1차·2차 전사 및 확정 전사를 사용"],
            ["해석 한계", "소표본 결과이므로 전체 문서군의 확정 성능·모델 간 우열·인과 효과로 일반화하지 않음"],
            ["원문 보관", "개인정보가 포함될 수 있는 원문·OCR 전문·전사 전문은 Git에 포함하지 않고 로컬에만 보관"],
        ], [37 * mm, 137 * mm]),
        p("5. PPT 삽입 문구", "H1"),
        p(
            f"> [검증] 사람 확정 전사 골드셋 18페이지로 OCR 전체 본문을 평가한 결과, CER {rate(overall['cer'])}, WER {rate(overall['wer'])}<br/>"
            "> [검증] 계약서·발주서·사업자등록증을 각 6페이지씩 포함한 고정 층화 소표본<br/>"
            "> [검증] CER/WER은 선정 필드 포함 여부가 아니라 원문 전체의 문자·단어 편집거리를 평가<br/>"
            "> [미확인] 표본이 18페이지이므로 전체 OCR 성능의 확정값으로 일반화하지 않음",
            "Callout",
        ),
        p("자료 기준: 2026-09-16 로컬 OCR 출력 집계와 사람이 확정한 전사 골드셋. 원문·OCR 전문은 보고서에 포함하지 않았다.", "Note"),
    ]
    doc.build(story)


if __name__ == "__main__":
    build()
