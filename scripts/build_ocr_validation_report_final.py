from pathlib import Path
import json

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, HRFlowable, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/pdf/ocr-validation-report-final-20260915.pdf"
SUMMARY = ROOT / "output/evals/ocr-runpod/runpod_dataset_summary.json"
FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
pdfmetrics.registerFont(TTFont("AppleGothic", FONT))
runpod = json.loads(SUMMARY.read_text(encoding="utf-8"))

NAVY = colors.HexColor("#18324B")
BLUE = colors.HexColor("#2D6CDF")
PALE = colors.HexColor("#EAF2FF")
GRAY = colors.HexColor("#5E6B78")
LIGHT = colors.HexColor("#F5F7FA")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="T", parent=styles["Title"], fontName="AppleGothic", fontSize=22, leading=27, textColor=NAVY, alignment=TA_LEFT, spaceAfter=4))
styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontName="AppleGothic", fontSize=9.5, leading=13, textColor=GRAY, spaceAfter=5))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="AppleGothic", fontSize=14, leading=18, textColor=NAVY, spaceBefore=2, spaceAfter=5))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="AppleGothic", fontSize=10.5, leading=14, textColor=BLUE, spaceBefore=5, spaceAfter=3))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.5, leading=12, textColor=colors.HexColor("#243444"), spaceAfter=3))
styles.add(ParagraphStyle(name="Cellx", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.1, leading=9.2, textColor=colors.HexColor("#243444")))
styles.add(ParagraphStyle(name="Headx", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.1, leading=9.2, textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Notex", parent=styles["BodyText"], fontName="AppleGothic", fontSize=7.1, leading=9.5, textColor=GRAY, spaceAfter=2))
styles.add(ParagraphStyle(name="Callx", parent=styles["BodyText"], fontName="AppleGothic", fontSize=8.8, leading=12.5, textColor=NAVY, backColor=PALE, borderColor=BLUE, borderWidth=0.5, borderPadding=6, spaceBefore=2, spaceAfter=6))


def P(text, style="Bodyx"):
    return Paragraph(text, styles[style])


def make_table(rows, widths, header=True):
    converted = []
    for index, row in enumerate(rows):
        style = "Headx" if header and index == 0 else "Cellx"
        converted.append([cell if hasattr(cell, "wrap") else P(str(cell), style) for cell in row])
    table = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8DEE7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    for row in range(1 if header else 0, len(rows)):
        if row % 2 == 0:
            commands.append(("BACKGROUND", (0, row), (-1, row), LIGHT))
    table.setStyle(TableStyle(commands))
    return table


def totals(name):
    fields = runpod["datasets"][name]["field_matches"]
    return sum(v["matched"] for v in fields.values()), sum(v["labeled"] for v in fields.values())


def ratio(name):
    matched, labeled = totals(name)
    return f"{matched}/{labeled} = {matched / labeled * 100:.1f}%"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D8DEE7"))
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("AppleGothic", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9 * mm, "SalesLuv | OCR 검증 결과 | 2026-09-15")
    canvas.drawRightString(192 * mm, 9 * mm, str(doc.page))
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame = Frame(18 * mm, 20 * mm, 174 * mm, 257 * mm, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=20 * mm, title="OCR 검증 결과 보고서")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])
    story = []

    story += [P("OCR 검증 결과 보고서", "T"), P("로컬 OCR과 RunPod OCR의 동일 샘플 비교 | 발표용 요약본", "Sub"), HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=7)]
    story += [P("핵심 결론", "H1x"), P("[검증] RunPod 210건 중 207건이 처리 성공했다(207 ÷ 210 = 98.6%). 선정 필드 일치율은 견적서 100.0%, 계약서 25.0%, 발주서 66.9%, 명함 94.8%로 문서 유형별 편차가 확인됐다. 사업자등록증은 24건 중 21건 처리됐고, 독립 정답지가 없어 파일명에서 파생한 상호만 보조적으로 평가했다.", "Callx")]
    story += [P("평가 모델 및 설정", "H1x")]
    story += [make_table([
        ["구분", "실제 사용 모델·설정", "적용 범위"],
        ["로컬 문서 OCR", "PaddleOCR 3.x · lang=korean · 문서 방향 분류·문서 보정·텍스트라인 방향 사용 · MKL-DNN 비활성화. 문서 검출 모델명은 앱 코드에서 고정하지 않음.", "견적서·계약서·발주서"],
        ["로컬 명함 OCR", "PaddleOCR 3.x · PP-OCRv5_mobile_det · korean_PP-OCRv5_mobile_rec · 문서 보정 비활성화", "실제 명함 36건"],
        ["RunPod 워커", "PaddleOCR 기반 GPU 워커. 이미지에 PP-LCNet_x1_0_doc_ori, UVDoc, PP-LCNet_x1_0_textline_ori, PP-OCRv5_server_det, korean_PP-OCRv5_mobile_rec 모델을 번들링.", "문서·명함·사업자등록증"],
        ["요약 평가", "OCR 정확도 계산에는 LLM-as-a-judge를 사용하지 않음. 해당 방법은 요약의 충실성·완전성 평가에 사용.", "OCR과 요약 지표 분리"],
    ], [31*mm, 104*mm, 39*mm])]
    story += [Spacer(1, 5), P("핵심 수치", "H1x")]
    story += [make_table([
        ["평가 대상", "표본·처리", "결과"],
        ["로컬 명함", "36/36", "126/134 = 94.0% · 필수값 전체 32/36 = 88.9%"],
        ["로컬 문서", "견적서·계약서·발주서 각 50/50 구조 처리", "선정 필드 존재율 100.0% · 100.0% · 60.0%"],
        ["RunPod", "207/210 성공", "견적서·계약서·발주서·명함 필드 집계"],
        ["사업자등록증", "21/24 성공", "상호 파일명 파생 라벨 10/21 = 47.6%"],
    ], [37*mm, 52*mm, 85*mm])]

    story += [Spacer(1, 14), P("1. 테스트 진행 방법과 기준", "H1x")]
    story += [make_table([
        ["단계", "진행 방법", "판정 기준"],
        ["입력 고정", "정답 XLSX와 원본 파일을 파일명·번호로 연결", "누락·중복·표본 수 확인"],
        ["OCR 실행", "로컬 또는 RunPod에 동일 파일 바이트와 profile 전달", "처리 상태·페이지·Markdown 생성"],
        ["필드 비교", "정답값과 OCR 본문을 NFC/NFKC·공백·구두점·날짜·금액 규칙으로 정규화", "정답값이 OCR 본문에 포함되는지"],
        ["문자 지표", "정식 전사 정답지가 있는 경우에만 전체 문자를 편집거리로 비교", "CER = 문자 편집거리 ÷ 정답 문자 수; WER = 단어 편집거리 ÷ 정답 단어 수"],
    ], [28*mm, 80*mm, 66*mm])]
    story += [P("[주의] 필드 일치율은 필드 위치·문자 단위 정확도·추출값의 중복을 평가하지 않는 보조 지표다. 이번 실행의 원문과 OCR 본문은 저장하지 않고 집계값만 기록했다.", "Callx")]
    story += [P("2. 로컬·RunPod 상세 결과", "H1x")]
    story += [make_table([
        ["대상", "로컬 결과", "RunPod 결과", "해석"],
        ["견적서 50건", "200/200 = 100.0%", ratio("견적서"), "날짜·고객사·번호·총액 선정 필드"],
        ["계약서 50건", "200/200 = 100.0%", ratio("계약서"), "RunPod PDF 경로에서 한글 필드 인식 저하"],
        ["발주서 50건", "450/750 = 60.0%", ratio("발주서"), "공급자 영역과 표·조건 필드 개선 필요"],
        ["명함 36건", "126/134 = 94.0%", ratio("명함"), "RunPod 전화·이름은 높고 회사·이메일 일부 누락"],
        ["사업자등록증 24건", "필드 정확도 미산출", "21/24 처리 · 10/21 상호 약한 라벨", "사업자번호·대표자·주소 독립 정답지 필요"],
    ], [34*mm, 39*mm, 45*mm, 56*mm])]
    story += [Spacer(1, 5), P("[검증] 회귀 테스트는 40/40 통과했다. RunPod 전체 평가에서 사업자등록증 3건은 작업 실패로 필드 평가에서 제외됐다.", "Bodyx")]

    story += [Spacer(1, 14), P("3. CER/WER와 한계", "H1x")]
    story += [make_table([
        ["대상", "CER", "WER", "근거·해석"],
        ["견적서 50건", "36.5%*", "63.5%*", "[추론] PDF 임베디드 텍스트 레이어와 비교한 proxy"],
        ["계약서 50건", "미산출", "미산출", "스캔 PDF라 신뢰 가능한 전사 기준 없음"],
        ["발주서 50건", "79.4%*", "89.3%*", "[추론] PDF 임베디드 텍스트 레이어와 비교한 proxy"],
        ["명함·사업자등록증", "미산출", "미산출", "사람이 전사한 전체 원문 정답지 없음"],
    ], [34*mm, 25*mm, 25*mm, 90*mm])]
    story += [P("* [추론] 위 proxy는 사람이 검수한 골드 전사가 아니므로 최종 OCR 정확도·품질 보증 수치로 사용하지 않는다. 정식 CER/WER에는 문서별 전체 전사 라벨이 필요하다.", "Notex")]
    story += [P("4. 결과 해석과 후속 조치", "H1x")]
    story += [make_table([
        ["관측 결과", "실무 판단", "후속 조치"],
        ["RunPod 계약서 선정 필드 25.0%", "PDF 경로에서 한국어 필드가 크게 손실됨", "PDF에도 language 설정 전달 또는 PDF를 PNG로 렌더링해 이미지 경로로 재평가"],
        ["발주서 66.9%", "공급자 영역·조건·표 보존이 병목", "레이아웃별 필드 추출 규칙과 표 인식 검증 추가"],
        ["사업자등록증 상호 47.6%", "파일명 파생 라벨의 보조 결과일 뿐 전체 필드 정확도가 아님", "사업자번호·상호·대표자·주소 독립 정답 XLSX 작성"],
        ["정식 CER/WER 미산출", "현재 proxy를 최종 정확도로 발표하면 안 됨", "사람 전사 골드셋 작성 후 문자·단어 지표 재산출"],
    ], [39*mm, 65*mm, 70*mm])]
    story += [P("5. PPT 삽입용 문구", "H1x"), P("> [검증] RunPod OCR 처리 성공률 207/210 = 98.6%<br/>> [검증] RunPod 선정 필드 일치율: 견적서 100.0%, 계약서 25.0%, 발주서 66.9%, 명함 94.8%<br/>> [검증] 사업자등록증 24건 중 21건 처리. 필드별 정확도는 독립 정답지 작성 후 확정<br/>> [미확인] 정식 CER/WER는 전체 전사 골드셋 구축 후 산출", "Callx")]
    story += [P("자료 기준: 2026-09-15 현재 저장된 로컬 샘플·XLSX 정답지·RunPod 집계 JSON. 개인정보가 포함된 원문은 PDF에 포함하지 않았다.", "Notex")]
    doc.build(story)


if __name__ == "__main__":
    build()
