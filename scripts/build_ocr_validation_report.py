from pathlib import Path
import json

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
OUTPUT = ROOT / "output" / "pdf" / "ocr-validation-report-complete-20260915.pdf"
RUNPOD_SUMMARY = ROOT / "output" / "evals" / "ocr-runpod" / "runpod_dataset_summary.json"
FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
pdfmetrics.registerFont(TTFont("AppleGothic", FONT))

runpod = json.loads(RUNPOD_SUMMARY.read_text(encoding="utf-8")) if RUNPOD_SUMMARY.exists() else {}


def _field_totals(name):
    fields = runpod.get("datasets", {}).get(name, {}).get("field_matches", {})
    matched = sum(item.get("matched", 0) for item in fields.values())
    labeled = sum(item.get("labeled", 0) for item in fields.values())
    return matched, labeled


def _pct(matched, labeled):
    return f"{matched}/{labeled} = {matched / labeled * 100:.1f}%" if labeled else "미산출"

NAVY = colors.HexColor("#18324B")
BLUE = colors.HexColor("#2D6CDF")
PALE_BLUE = colors.HexColor("#EAF2FF")
GREEN = colors.HexColor("#16866A")
ORANGE = colors.HexColor("#D97706")
RED = colors.HexColor("#B42318")
GRAY = colors.HexColor("#5E6B78")
LIGHT = colors.HexColor("#F5F7FA")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="KRTitle", parent=styles["Title"], fontName="AppleGothic", fontSize=24, leading=31, textColor=NAVY, alignment=TA_LEFT, spaceAfter=8))
styles.add(ParagraphStyle(name="KRSubtitle", parent=styles["Normal"], fontName="AppleGothic", fontSize=11, leading=17, textColor=GRAY, spaceAfter=8))
styles.add(ParagraphStyle(name="KRH1", parent=styles["Heading1"], fontName="AppleGothic", fontSize=16, leading=22, textColor=NAVY, spaceBefore=3, spaceAfter=8))
styles.add(ParagraphStyle(name="KRH2", parent=styles["Heading2"], fontName="AppleGothic", fontSize=12, leading=17, textColor=BLUE, spaceBefore=6, spaceAfter=5))
styles.add(ParagraphStyle(name="KRBody", parent=styles["BodyText"], fontName="AppleGothic", fontSize=9.3, leading=15, textColor=colors.HexColor("#243444"), spaceAfter=5))
styles.add(ParagraphStyle(name="KRSmall", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8, leading=12, textColor=GRAY, spaceAfter=3))
styles.add(ParagraphStyle(name="KRCell", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.9, leading=11, textColor=colors.HexColor("#243444")))
styles.add(ParagraphStyle(name="KRCellCenter", parent=styles["KRCell"], alignment=TA_CENTER))
styles.add(ParagraphStyle(name="KRHeader", parent=styles["KRCell"], textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="KRCallout", parent=styles["BodyText"], fontName="AppleGothic", fontSize=10, leading=16, textColor=NAVY, backColor=PALE_BLUE, borderColor=BLUE, borderWidth=0.6, borderPadding=8, spaceBefore=4, spaceAfter=10))


def P(text, style="KRBody"):
    return Paragraph(text, styles[style])


def table(data, widths, header=True, font_size=7.9):
    converted = []
    for r, row in enumerate(data):
        style = "KRHeader" if header and r == 0 else "KRCell"
        converted.append([cell if hasattr(cell, "wrap") else P(str(cell), style) for cell in row])
    t = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), "AppleGothic"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8DEE7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    for r in range(1 if header else 0, len(data)):
        if r % 2 == 0:
            commands.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    t.setStyle(TableStyle(commands))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D8DEE7"))
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("AppleGothic", 7.5)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9 * mm, "SalesLuv | OCR 검증 결과 | 2026-09-15")
    canvas.drawRightString(192 * mm, 9 * mm, f"{doc.page}")
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame = Frame(18 * mm, 20 * mm, 174 * mm, 257 * mm, id="normal", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=20 * mm, title="OCR 검증 결과 보고서")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])
    story = []

    story += [P("OCR 검증 결과 보고서", "KRTitle"), P("SalesLuv 문서 처리 파이프라인 | 로컬 OCR 샘플 검증", "KRSubtitle"), HRFlowable(width="100%", thickness=1.2, color=BLUE, spaceAfter=13)]
    story += [P("결론", "KRH1"), P("[검증] 로컬 OCR 기준으로 견적서·계약서·발주서 150건과 명함 36건의 구조 처리 및 필드 비교를 완료했다. 명함 필드 일치율은 94.0%였고, 문서 OCR의 정답 필드 존재율은 문서 유형별로 차이가 있었다.", "KRCallout")]
    story += [P("[검증] RunPod 운영 경로도 동일 샘플로 추가 평가했다. RunPod 처리 성공률은 문서·명함 186/186, 사업자등록증 21/24였고, 사업자등록증은 파일명으로 확인 가능한 상호만 약한 라벨로 평가했다.", "KRBody")]
    story += [P("[주의] 사업자등록번호·대표자·주소의 독립 정답지와 사람이 전사한 전체 원문이 없어 사업자등록증 전체 필드 정확도와 정식 CER/WER는 아직 산출하지 않았다.", "KRBody")]
    story += [P("핵심 수치", "KRH1")]
    story += [table([
        ["평가 대상", "표본", "처리 결과", "핵심 수치"],
        ["명함 OCR", "36건", "36/36 처리", "필드 일치율 126/134 = 94.0%"],
        ["명함 필수값", "36건", "36/36 처리", "이름·회사·전화 전체 일치 32/36 = 88.9%"],
        ["견적서 OCR", "50건", "구조 50/50", "선정 필드 존재율 200/200 = 100.0%"],
        ["계약서 OCR", "50건", "구조 50/50", "선정 필드 존재율 200/200 = 100.0%"],
        ["발주서 OCR", "50건", "구조 50/50", "선정 필드 존재율 450/750 = 60.0%"],
        ["OCR 코드 회귀", "40개 테스트", "40/40 통과", "예외·응답 정규화 검증"],
        ["RunPod OCR", "210건", "207/210 처리", "견적서·계약서·발주서·명함 필드 집계"],
        ["사업자등록증", "24건", "21/24 처리", "상호 파일명 파생 라벨 10/21 = 47.6%"],
    ], [34*mm, 24*mm, 34*mm, 82*mm])]
    story += [Spacer(1, 8), P("판단 요약", "KRH1"), P("[추론] 명함 OCR은 필드 단위 성능이 상대적으로 높다. 문서 OCR은 발주서에서 정답값 존재율이 낮아, 표·레이아웃 보존과 공급자·납품·지급조건 영역의 추가 검증이 필요하다.", "KRBody")]

    story += [PageBreak(), P("1. 테스트 진행 방법", "KRH1")]
    story += [P("[검증] 로컬 평가는 원본 파일을 로컬에서 처리했다. 추가 RunPod 평가는 동일 파일을 RunPod Serverless OCR 어댑터로 전송해 처리 결과만 집계했다. 원문과 OCR 본문은 보고서에 저장하지 않았다.", "KRBody")]
    story += [table([
        ["단계", "진행 방법", "확인 항목"],
        ["1. 입력 준비", "정답지 XLSX와 원본 파일을 파일명으로 연결", "평가 문서 수·누락 파일"],
        ["2. OCR·추출", "PDF·DOCX 추출 또는 로컬 OCR 실행", "본문·Markdown·페이지 목록"],
        ["3. 구조 검사", "페이지 번호와 출력 구조를 자동 검사", "페이지가 1부터 연속인지, 내용이 비어 있지 않은지"],
        ["4. 필드 비교", "OCR 결과와 XLSX 정답 필드를 정규화해 비교", "정답값이 OCR 텍스트에 존재하는지"],
        ["5. 명함 평가", "이름·회사·전화·이메일을 필드 단위로 비교", "필드 일치율·필수값 전체 일치율"],
        ["6. RunPod 비교", "동일 입력을 RunPod 경로로 처리", "처리 성공률·필드 일치율·관측 처리시간"],
    ], [30*mm, 86*mm, 58*mm])]
    story += [P("2. 판정 기준", "KRH1")]
    story += [table([
        ["판정 항목", "통과·일치 기준"],
        ["문서 구조 통과", "본문·Markdown·페이지 목록이 모두 존재하고 페이지 번호가 1부터 연속"],
        ["OCR 필드 존재", "정답값이 정규화 후 OCR 텍스트 안에 존재"],
        ["명함 필드 일치", "OCR 결과 필드값과 정답 필드값이 일치"],
        ["명함 필수값 전체 일치", "이름·회사·전화가 한 명함에서 모두 일치"],
        ["표기 정규화", "날짜는 날짜 형식, 금액은 통화기호·쉼표를 제거하고 비교; 일반 텍스트는 공백·구두점 정규화"],
    ], [45*mm, 129*mm])]
    story += [P("[주의] ‘OCR 텍스트에 값이 포함됨’은 문자 단위 정확도나 필드 위치 정확도를 의미하지 않는다. RunPod 필드 수치도 같은 보조 지표이며, 정식 CER/WER는 사람이 전사한 전체 원문 정답지가 필요하다.", "KRCallout")]

    story += [PageBreak(), P("3. 상세 결과", "KRH1")]
    story += [P("3.1 명함 OCR", "KRH2")]
    story += [table([
        ["지표", "계산", "결과"],
        ["필드 일치율", "일치 필드 ÷ 입력된 정답 필드", "126 ÷ 134 = 94.0%"],
        ["회사 필드", "정답과 일치한 회사명", "33/36"],
        ["이름 필드", "정답이 입력된 명함 기준", "34/35"],
        ["전화 필드", "정답과 일치한 전화번호", "36/36"],
        ["이메일 필드", "정답이 입력된 명함 기준", "23/27"],
        ["필수값 전체 일치", "이름·회사·전화가 모두 일치한 명함", "32/36 = 88.9%"],
    ], [48*mm, 76*mm, 50*mm])]
    story += [Spacer(1, 8), P("3.2 문서 OCR", "KRH2")]
    story += [table([
        ["문서 유형", "표본", "구조 처리", "선정 필드 존재율", "판정"],
        ["견적서", "50", "50/50", "200/200 = 100.0%", "통과"],
        ["계약서", "50", "50/50", "200/200 = 100.0%", "통과"],
        ["발주서", "50", "50/50", "450/750 = 60.0%", "개선 필요"],
        ["사업자등록증", "24개 파일 확인", "별도 정확도 미산출", "정답 필드 평가 필요", "추가 평가"],
    ], [35*mm, 28*mm, 29*mm, 48*mm, 34*mm])]
    story += [Spacer(1, 9), P("필드 존재율 비교", "KRH2")]
    # simple bar table; avoids chart font/layout issues while remaining visually scannable
    story += [table([
        ["유형", "비율", "시각화"],
        ["견적서", "100.0%", "####################"],
        ["계약서", "100.0%", "####################"],
        ["발주서", "60.0%", "############........"],
    ], [30*mm, 26*mm, 100*mm])]
    story += [Spacer(1, 8), P("3.3 RunPod 추가 평가", "KRH2")]
    story += [table([
        ["대상", "처리", "선정 필드 일치율", "CER/WER"],
        ["견적서", "50/50", _pct(*_field_totals("견적서")), "CER 36.5%, WER 63.5%*"],
        ["계약서", "50/50", _pct(*_field_totals("계약서")), "정식 산출 불가"],
        ["발주서", "50/50", _pct(*_field_totals("발주서")), "CER 79.4%, WER 89.3%*"],
        ["명함", "36/36", _pct(*_field_totals("명함")), "전체 전사 정답지 없음"],
        ["사업자등록증", "21/24", _pct(*_field_totals("사업자등록증")), "필드 정답지 없음"],
    ], [31*mm, 25*mm, 52*mm, 48*mm])]
    story += [P("* [추론] CER/WER는 PDF에 이미 포함된 텍스트 레이어와 RunPod 결과를 비교한 진단용 proxy다. 사람이 전사한 골드 텍스트가 아니므로 최종 OCR 정확도로 해석하지 않는다.", "KRSmall")]

    story += [PageBreak(), P("4. 해석과 한계", "KRH1")]
    story += [P("[검증] 현재 결과는 로컬 및 RunPod OCR 파이프라인의 샘플 처리 결과다. 문서 150건은 구조·필드 비교, 명함 36건은 필드값 비교, 사업자등록증 24건은 처리 성공 여부와 파일명 파생 상호 라벨을 확인했다.", "KRBody")]
    story += [table([
        ["확인된 내용", "해석"],
        ["명함 필드 일치율 94.0%", "이름·회사·전화·이메일 필드가 정답과 일치한 비율"],
        ["발주서 필드 존재율 60.0%", "OCR 텍스트에서 정답 필드가 확인되지 않는 사례가 상대적으로 많음"],
        ["구조 처리 50/50", "페이지·본문·Markdown 산출은 성공했지만 값의 정확성을 보장하지 않음"],
        ["RunPod 사업자등록증 21/24", "3건은 RunPod 작업 실패로 필드 평가에서 제외됨"],
    ], [58*mm, 98*mm])]
    story += [P("5. 미검증 범위", "KRH1")]
    story += [table([
        ["항목", "현재 상태", "추가 작업"],
        ["RunPod 운영 OCR", "[검증] 210건 처리, 207건 성공", "실패 3건 재시도·원인 분석"],
        ["CER/WER", "[추론] PDF 텍스트 레이어 proxy만 산출", "사람이 전사한 전체 원문 정답지 작성"],
        ["사업자등록증", "[검증] 상호 파일명 파생 라벨 10/21", "사업자번호·상호·대표자·주소 독립 정답지 작성"],
        ["OCR와 요약 오류 분리", "[미확인] 완전 분리 집계 없음", "OCR 출력과 Agent JSON을 단계별로 따로 채점"],
    ], [42*mm, 54*mm, 60*mm])]
    story += [P("6. 발표용 문구", "KRH1"), P("> [검증] 로컬 OCR 구조 처리: 견적서·계약서·발주서 각 50/50, 명함 36/36<br/>> [검증] RunPod OCR 처리 성공: 문서·명함 186/186, 사업자등록증 21/24<br/>> [검증] RunPod 선정 필드 일치율: 견적서 200/200, 계약서 50/200, 발주서 502/750, 명함 127/134<br/>> [추론] CER/WER는 PDF 텍스트 레이어 기반 proxy이며 정식 골드 전사 평가는 추가 필요<br/>> [미확인] 사업자등록증 사업자번호·대표자·주소 필드 정확도", "KRCallout")]
    story += [P("자료 기준: 2026-09-15 현재 저장된 로컬 샘플 및 XLSX 정답지. 개인정보가 포함된 원본 본문은 이 PDF에 포함하지 않았다.", "KRSmall")]
    doc.build(story)


if __name__ == "__main__":
    build()
