"""표준 라이브러리만으로 최소 .docx 를 만든다.

자료실(document/file)에 붙일 첨부가 필요한데 upload_guard 가 받는 형식은
pdf·docx·pptx 뿐이다. PDF 는 한글을 쓰려면 폰트를 임베드해야 해서 reportlab 같은
의존성이 붙지만, docx 는 XML 을 담은 zip 이라 UTF-8 을 그대로 쓸 수 있다.

서식은 제목 한 줄과 문단 목록이 전부다. 표·이미지·스타일은 다루지 않는다.

    uv run python -m scripts.demo._docx    # 자체 검사
"""

import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels"
 ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml"
 ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1"
 Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
 Target="word/document.xml"/>
</Relationships>"""

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _paragraph(text: str, *, bold: bool = False, size_half_points: int = 22) -> str:
    """한 문단. 빈 문자열이면 빈 줄로 쓴다."""
    run_properties = f'<w:rPr>{"<w:b/>" if bold else ""}<w:sz w:val="{size_half_points}"/></w:rPr>'
    # xml:space 를 preserve 로 두지 않으면 앞뒤 공백이 사라진다.
    run = f'<w:r>{run_properties}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    return f"<w:p>{run}</w:p>"


def build_docx(title: str, paragraphs: list[str]) -> bytes:
    """제목 한 줄과 문단들로 된 .docx 바이트."""
    body = [_paragraph(title, bold=True, size_half_points=32)]
    body.extend(_paragraph(text) for text in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{"".join(body)}</w:body></w:document>'
    )

    buffer = BytesIO()
    # 압축을 켜 두면 자료실 12건이 수백 KB 안에서 끝난다.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def main() -> None:
    from xml.etree import ElementTree

    title = "의료기기 산업 동향 요약"
    paragraphs = [
        "이 문서는 아래 공개자료를 요약한 내부 메모입니다. 원문은 링크를 참고하세요.",
        "",
        "2025년 의료기기 생산·수출액이 전년 대비 각각 8.1%, 2.2% 증가했다.",
        "  들여쓴 줄과 <꺾쇠> & 앰퍼샌드가 그대로 살아야 한다.",
    ]
    blob = build_docx(title, paragraphs)

    assert blob[:2] == b"PK", "upload_guard 가 docx 를 PK 시그니처로 판별한다"

    with zipfile.ZipFile(BytesIO(blob)) as archive:
        names = set(archive.namelist())
        assert names == {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}, names
        assert archive.testzip() is None, "zip 이 깨졌다"
        root = ElementTree.fromstring(archive.read("word/document.xml"))

    texts = [node.text or "" for node in root.iter(f"{{{W}}}t")]
    assert texts[0] == title
    assert texts[1:] == paragraphs, texts[1:]
    assert "  들여쓴 줄과 <꺾쇠> & 앰퍼샌드가 그대로 살아야 한다." in texts

    print(f"docx {len(blob)} bytes · 문단 {len(texts)}개 · 자체 검사 통과")


if __name__ == "__main__":
    main()
