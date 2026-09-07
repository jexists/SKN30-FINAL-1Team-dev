from io import BytesIO
from zipfile import ZipFile

import pytest

from app.agents.document_summary import SYSTEM_PROMPT, chunks
from app.services.document_extraction import ExtractionError, extract_document


def _zip_xml(path: str, xml: str) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(path, xml)
    return stream.getvalue()


def test_document_summary_prompt_uses_korean_honorific_style():
    assert "한국어 존댓말" in SYSTEM_PROMPT
    assert "합니다체" in SYSTEM_PROMPT
    assert "summary·key_points·sales_relevance·risk_flags" in SYSTEM_PROMPT


def test_document_summary_prompt_requires_natural_prose_without_inventing_facts():
    assert "자연스럽고 읽기 쉽게" in SYSTEM_PROMPT
    assert "완결된 문장" in SYSTEM_PROMPT
    assert "원인·평가·전망을 추가" in SYSTEM_PROMPT


def test_text_and_html_extraction_create_markdown_and_json_payload():
    text = extract_document(
        file_name="proposal.txt",
        media_type="text/plain",
        content="제품 소개\n\n계약기간: 1년".encode(),
    )
    html = extract_document(
        file_name="proposal.html",
        media_type="text/html",
        content="<h1>제안서</h1><p>계약기간: 1년</p>".encode(),
    )

    assert "계약기간" in text.plain_text
    assert "제안서" in html.plain_text
    assert html.payload["source_type"] == "html"
    assert html.payload["page_count"] == 1
    assert "## 제안서" not in html.markdown  # HTML heading은 보수적으로 본문으로 보존한다.


def test_docx_extraction_preserves_table_rows():
    xml = """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>계약서</w:t></w:r></w:p>
        <w:tbl>
          <w:tr><w:tc><w:p><w:r><w:t>항목</w:t></w:r></w:p></w:tc>
          <w:tc><w:p><w:r><w:t>내용</w:t></w:r></w:p></w:tc></w:tr>
        </w:tbl>
      </w:body>
    </w:document>"""
    result = extract_document(
        file_name="contract.docx",
        media_type=None,
        content=_zip_xml("word/document.xml", xml),
    )

    assert "항목" in result.plain_text
    assert "| 항목 | 내용 |" in result.markdown
    assert result.payload["source_type"] == "docx"
    assert result.payload["pages"][0]["markdown"]
    assert chunks(result.markdown, pages=result.payload["pages"])[0]["page_start"] == 1


def test_pptx_extraction_creates_slide_source_pages():
    xml = """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:cSld><a:t>영업 전략</a:t></p:cSld>
    </p:sld>"""
    result = extract_document(
        file_name="sales.pptx",
        media_type=None,
        content=_zip_xml("ppt/slides/slide1.xml", xml),
    )

    assert "영업 전략" in result.plain_text
    assert result.payload["pages"][0]["page_number"] == 1
    assert result.payload["pages"][0]["markdown"]
    assert chunks(result.markdown, pages=result.payload["pages"])[0]["page_start"] == 1
    assert result.payload["page_count"] == 1


def test_pptx_extraction_sorts_double_digit_slides_numerically():
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        for number in (1, 10, 2):
            xml = f"""<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"
              xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">
              <p:cSld><a:t>슬라이드 {number}</a:t></p:cSld>
            </p:sld>"""
            archive.writestr(f"ppt/slides/slide{number}.xml", xml)

    result = extract_document(file_name="sales.pptx", media_type=None, content=stream.getvalue())

    assert [page["blocks"][0]["text"] for page in result.payload["pages"]] == [
        "슬라이드 1",
        "슬라이드 2",
        "슬라이드 10",
    ]


def test_pptx_extraction_uses_recorded_presentation_order():
    stream = BytesIO()
    presentation = """<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:sldIdLst>
        <p:sldId id="1" r:id="rId10"/><p:sldId id="2" r:id="rId11"/><p:sldId id="3" r:id="rId12"/>
      </p:sldIdLst>
    </p:presentation>"""
    relationships = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId10" Target="slides/slide10.xml" Type="slide"/>
      <Relationship Id="rId11" Target="slides/slide2.xml" Type="slide"/>
      <Relationship Id="rId12" Target="slides/slide1.xml" Type="slide"/>
    </Relationships>"""
    with ZipFile(stream, "w") as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
        for number in (1, 10, 2):
            xml = f"""<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"
              xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">
              <p:cSld><a:t>기록순서 {number}</a:t></p:cSld>
            </p:sld>"""
            archive.writestr(f"ppt/slides/slide{number}.xml", xml)

    result = extract_document(
        file_name="reordered.pptx", media_type=None, content=stream.getvalue()
    )

    assert [page["blocks"][0]["text"] for page in result.payload["pages"]] == [
        "기록순서 10",
        "기록순서 2",
        "기록순서 1",
    ]


def test_scanned_pdf_is_not_silently_indexed():
    with pytest.raises(ExtractionError, match="invalid_pdf|ocr_required"):
        extract_document(
            file_name="scan.pdf",
            media_type="application/pdf",
            content=b"%PDF-not-a-real-pdf",
        )


def test_chunks_keep_section_and_overlap_long_text():
    result = chunks("## 지급조건\n\n" + ("계약금액과 지급조건을 확인한다. " * 200))

    assert len(result) > 1
    assert all(item["section"] == "지급조건" for item in result)
    assert all(item["content"] for item in result)


def test_chunks_preserve_pdf_page_numbers():
    result = chunks(
        "전체 문서",
        pages=[
            {"page_number": 3, "markdown": "## 계약 조건\n\n계약기간은 1년이다."},
            {"page_number": 4, "markdown": "## 지급 조건\n\n검수 후 지급한다."},
        ],
    )

    assert [(item["page_start"], item["page_end"]) for item in result] == [(3, 3), (4, 4)]
