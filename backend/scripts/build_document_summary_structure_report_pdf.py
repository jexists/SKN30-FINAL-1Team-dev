"""문서요약 구조화 추출값·RAG 입력 형식·추출 기준 정리 PDF."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
from pathlib import Path
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


def text(value: object) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def make_styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName=font, fontSize=20, leading=27, textColor=colors.HexColor("#182230"), spaceAfter=8),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontName=font, fontSize=9, leading=13, textColor=colors.HexColor("#667085"), spaceAfter=12),
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontName=font, fontSize=14, leading=20, textColor=colors.HexColor("#1D2939"), spaceBefore=12, spaceAfter=7),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName=font, fontSize=10.5, leading=15, textColor=colors.HexColor("#344054"), spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName=font, fontSize=8.8, leading=14, textColor=colors.HexColor("#344054"), spaceAfter=5, wordWrap="CJK"),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName=font, fontSize=7.5, leading=11, textColor=colors.HexColor("#475467"), spaceAfter=3, wordWrap="CJK"),
        "cell": ParagraphStyle("Cell", parent=base["BodyText"], fontName=font, fontSize=7.4, leading=10.5, textColor=colors.HexColor("#344054"), wordWrap="CJK"),
        "head": ParagraphStyle("Head", parent=base["BodyText"], fontName=font, fontSize=7.4, leading=10.5, textColor=colors.white, alignment=TA_CENTER, wordWrap="CJK"),
    }


class ReportDoc(BaseDocTemplate):
    def __init__(self, path: Path, title: str):
        super().__init__(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=17 * mm, title=title, author="SalesLuv")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="report", frames=frame, onPage=self.footer)])

    def footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Korean", 7.5)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(18 * mm, 8.5 * mm, "SalesLuv - 문서요약 구조·RAG 입력 정리")
        canvas.drawRightString(A4[0] - 18 * mm, 8.5 * mm, str(doc.page))
        canvas.restoreState()


def para(value: object, sty: ParagraphStyle) -> Paragraph:
    return Paragraph(text(value), sty)


def table(rows: list[list[object]], widths: list[float], sty: dict[str, ParagraphStyle]) -> LongTable:
    converted = []
    for ri, row in enumerate(rows):
        cell_style = sty["head"] if ri == 0 else sty["cell"]
        converted.append([item if isinstance(item, Paragraph) else para(item, cell_style) for item in row])
    result = LongTable(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#344054")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return result


def callout(value: str, sty: dict[str, ParagraphStyle]) -> Table:
    result = Table([[para(value, sty["body"])]], colWidths=[174 * mm])
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F4F7")),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return result


def build(path: Path) -> None:
    sty = make_styles(configure_font())
    story: list[object] = [
        Paragraph("문서요약 구조화 추출값·RAG 입력 형식·추출 기준", sty["title"]),
        Paragraph("작성일: 2026-09-15 | 방금 확인한 구현 기준 정리", sty["subtitle"]),
        callout("[검증] 현재 구조는 출력 외곽과 처리 규칙은 고정되어 있지만, 문서별 내부 추출 필드는 변동되는 반고정 방식이다. [추론] 계약서·발주서 정확도를 높이려면 문서 유형별 필수 스키마가 필요하다.", sty),
        Paragraph("1. 구조화 추출값은 어디에 사용하는가", sty["h1"]),
        para("[검증] LLM 요약 결과는 summary, key_points, sales_relevance, risk_flags, extracted_fields, source_refs 구조로 반환됩니다. 이 중 extracted_fields가 계약금·납기·공급자처럼 기계적으로 사용할 수 있는 구조화 추출값입니다.", sty["body"]),
        table([
            ["사용 위치", "현재 사용 방식"],
            ["저장", "[검증] file.summary_payload JSONB에 summary 전체와 extracted_fields를 저장합니다."],
            ["API·화면", "[검증] 요약 조회 응답과 json artifact에서 summary_payload를 반환합니다."],
            ["감사 로그", "[검증] 처리 후 audit의 after_snapshot.summary_fields에 extracted_fields를 기록합니다."],
            ["브리핑 문맥", "[검증] briefing-context JSON의 summaries.summary_payload에 포함됩니다."],
            ["현재 RAG 청크", "[검증] extracted_fields를 직접 검색 청크로 사용하지 않고, extracted.markdown을 청킹합니다."],
        ], [38 * mm, 136 * mm], sty),
        para("[추론] 따라서 현재 extracted_fields는 RAG 검색 원문이라기보다 화면 표시, 계약 필드 조회, 금액·일정 검증, 감사 추적을 위한 기계 처리용 데이터입니다. 다만 현재 브리핑용 문자열 변환기는 summary_markdown과 검색 근거 content를 사용하고 summary_payload 전체를 문자열로 넣지는 않습니다.", sty["body"]),
        para("근거 코드: document_summary.py 41-50행, document_processing.py 123-177행·349-361행, sales_context.py 99-110행", sty["small"]),
        Paragraph("2. RAG에 보내는 형식", sty["h1"]),
        table([
            ["단계", "데이터 형식", "핵심 내용"],
            ["원본 추출", "TXT + MD + JSON", "[검증] plain_text, markdown, payload를 공통 결과로 보존합니다."],
            ["요약 LLM", "Markdown 문자열", "[검증] document_markdown을 LLM 입력으로 사용합니다. API 요청 외곽은 JSON입니다."],
            ["RAG 청킹", "Markdown 기반 텍스트", "[검증] markdown을 1,600자 청크와 200자 overlap으로 나눕니다."],
            ["임베딩", "청크 텍스트 문자열", "[검증] 임베딩이 설정되면 각 청크 content를 임베딩 API로 보냅니다."],
            ["검색 API", "JSON 응답", "[검증] 문서명·페이지·청크 content·score를 JSON으로 반환합니다."],
            ["최종 LLM", "텍스트 문맥 블록", "[검증] JSON 검색 결과를 <document_context> 안의 텍스트로 변환합니다."],
        ], [31 * mm, 38 * mm, 105 * mm], sty),
        callout("처리 흐름\n[검증] 원본 파일 → OCR/추출 → plain_text + markdown + payload(JSON) → markdown 기반 RAG 청크 → 키워드 또는 벡터 검색 → 검색 결과 JSON → LLM용 텍스트 문맥", sty),
        para("[검증] TXT와 MD를 RAG에 각각 중복 전송하는 방식은 아닙니다. 현재 운영 코드의 RAG 청크 원문은 markdown 기반이며, JSON은 API 응답·페이지 정보·구조화 결과 보존에 사용됩니다.", sty["body"]),
        para("근거 코드: document_summary.py 53-84행·102-125행, document_processing.py 109-162행·438-526행, sales_context.py 113-177행", sty["small"]),
        Paragraph("3. 추출 기준은 고정값인가, 변동값인가", sty["h1"]),
        table([
            ["구분", "현재 기준"],
            ["고정", "[검증] 출력 필드명, JSON 스키마, 입력 최대 60,000자, 청크 1,600자, overlap 200자, 지원 파일 형식"],
            ["변동", "[검증] extracted_fields 내부 키, 문서별 필드 수, OCR 결과, LLM이 선택하는 핵심 내용"],
            ["검색 방식", "[검증] 임베딩 설정 시 hybrid, 미설정 시 keyword fallback으로 환경에 따라 변동"],
            ["판정 기준", "[미확인] 유형별 필수 필드, 허용 누락률, 최소 점수는 아직 확정되지 않음"],
        ], [30 * mm, 144 * mm], sty),
        para("[검증] extracted_fields의 타입은 dict[str, Any]이므로 계약서마다 당사자·계약금·잔금 같은 필드가 반드시 존재하도록 강제하지 않습니다. [추론] 이것이 이번 평가에서 계약서 요약의 핵심 필드 누락과 금액 의미 혼동이 발생한 주요 구조적 원인입니다.", sty["body"]),
        Paragraph("4. 개선 권고", sty["h1"]),
        table([
            ["문서 유형", "권장 고정 필드"],
            ["견적서", "[추론] 고객사, 견적일, 유효기간, 견적번호, 총액, 품목"],
            ["계약서", "[추론] 갑/을, 작성일, 공급일, 총액, 계약금, 잔금, 보증기간"],
            ["발주서", "[추론] 발주자, 공급자, 납품장소, 지급조건, 총액, 품목"],
            ["상품설명서", "[추론] 모델명, 용도, 주요 사양, 적용 대상, 주의사항"],
        ], [33 * mm, 141 * mm], sty),
        para("[추론] 문서 유형을 먼저 분류한 뒤 유형별 JSON Schema로 extracted_fields를 검증하고, 누락 필드는 사람검수 대상으로 표시하는 2단계 구조가 적절합니다. RAG에는 원문 청크를 유지하되, 금액·날짜·역할처럼 오류 비용이 큰 필드는 구조화 값과 원문 청크를 함께 대조하는 방식이 필요합니다.", sty["body"]),
        Paragraph("5. 최종 정리", sty["h1"]),
        callout("[검증] JSON은 저장·API·LLM 구조화 응답의 포장 형식입니다. 실제 문서 내용은 Markdown 기반으로 요약·RAG에 사용됩니다. [검증] 현재 추출 기준은 외곽은 고정, 내부 필드는 변동입니다. [추론] 문서 유형별 고정 스키마를 추가해야 테스트에서 확인된 계약서·발주서 누락을 줄일 수 있습니다.", sty),
        para("참고 코드: backend/app/agents/document_summary.py, backend/app/services/document_processing.py, backend/app/services/sales_context.py, backend/app/api/documents.py", sty["small"]),
    ]
    ReportDoc(path, "문서요약 구조화 추출값·RAG 입력 형식·추출 기준").build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
