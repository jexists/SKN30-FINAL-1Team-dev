"""문서 원본을 자료요약 Agent가 소비하는 공통 구조로 바꾼다.

텍스트가 이미 들어 있는 Office/HTML 문서는 외부 API 없이 처리한다. PDF 스캔본과
이미지는 별도 OCR 어댑터가 필요하므로, 현재는 명시적인 오류를 내어 깨진 결과를
RAG에 넣지 않도록 한다.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from app.core.config import settings


class ExtractionError(Exception):
    """문서 추출 실패. 호출부에 안전한 코드만 전달한다."""


@dataclass(frozen=True)
class ExtractedDocument:
    plain_text: str
    markdown: str
    payload: dict[str, Any]


_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_PPT_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _clean_text(value: str) -> str:
    value = html.unescape(value).replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _markdown_from_blocks(blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        text = _clean_text(str(block.get("text", "")))
        if not text and block_type != "table":
            continue
        if block_type == "heading":
            lines.append(f"## {text}")
        elif block_type == "table":
            rows = block.get("rows") or []
            if rows:
                lines.append("| " + " | ".join(str(cell) for cell in rows[0]) + " |")
                lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
                lines.extend(
                    "| " + " | ".join(str(cell) for cell in row) + " |" for row in rows[1:]
                )
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _from_text(text: str, *, source_type: str) -> ExtractedDocument:
    text = _clean_text(text)
    if not text:
        raise ExtractionError("empty_extracted_text")
    blocks = [{"type": "paragraph", "text": paragraph} for paragraph in text.split("\n\n")]
    return ExtractedDocument(
        plain_text=text,
        markdown=_markdown_from_blocks(blocks),
        payload={
            "version": 1,
            "source_type": source_type,
            "pages": [{"page_number": 1, "blocks": blocks}],
            "page_count": 1,
        },
    )


def _docx(content: bytes) -> ExtractedDocument:
    try:
        with ZipFile(__import__("io").BytesIO(content)) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (BadZipFile, KeyError, ET.ParseError) as error:
        raise ExtractionError("invalid_docx") from error

    blocks: list[dict[str, Any]] = []
    body = root.find(f"{_WORD_NS}body")
    if body is None:
        raise ExtractionError("empty_docx")
    for child in body:
        if child.tag == f"{_WORD_NS}p":
            text = "".join(node.text or "" for node in child.iter(f"{_WORD_NS}t"))
            style = child.find(f"{_WORD_NS}pPr/{_WORD_NS}pStyle")
            is_heading = style is not None and style.attrib.get(
                f"{_WORD_NS}val", ""
            ).lower().startswith("heading")
            blocks.append({"type": "heading" if is_heading else "paragraph", "text": text})
        elif child.tag == f"{_WORD_NS}tbl":
            rows: list[list[str]] = []
            for row in child.findall(f"{_WORD_NS}tr"):
                rows.append(
                    [
                        "".join(node.text or "" for node in cell.iter(f"{_WORD_NS}t")).strip()
                        for cell in row.findall(f"{_WORD_NS}tc")
                    ]
                )
            blocks.append({"type": "table", "rows": rows})
    return _blocks_result(blocks, "docx")


def _pptx(content: bytes) -> ExtractedDocument:
    try:
        with ZipFile(__import__("io").BytesIO(content)) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
            # 문자열 정렬은 slide10을 slide2보다 먼저 배치한다. 파일명의 숫자를
            # 실제 슬라이드 번호로 해석해 출처 페이지와 본문 순서를 맞춘다.
            names.sort(
                key=lambda name: (
                    int(match.group(1))
                    if (match := re.search(r"slide(\d+)\.xml$", name))
                    else 0,
                    name,
                )
            )
            pages: list[dict[str, Any]] = []
            blocks: list[dict[str, Any]] = []
            for page_number, name in enumerate(names, start=1):
                root = ET.fromstring(archive.read(name))
                texts = [node.text or "" for node in root.iter(f"{_A_NS}t")]
                page_blocks = [
                    {"type": "paragraph", "text": text} for text in texts if text.strip()
                ]
                pages.append({"page_number": page_number, "blocks": page_blocks})
                blocks.append({"type": "heading", "text": f"슬라이드 {page_number}"})
                blocks.extend(page_blocks)
    except (BadZipFile, KeyError, ET.ParseError) as error:
        raise ExtractionError("invalid_pptx") from error
    if not blocks:
        raise ExtractionError("empty_pptx")
    return _blocks_result(blocks, "pptx", pages=pages)


def _blocks_result(
    blocks: list[dict[str, Any]],
    source_type: str,
    *,
    pages: list[dict[str, Any]] | None = None,
) -> ExtractedDocument:
    markdown = _markdown_from_blocks(blocks)
    plain = "\n\n".join(
        _clean_text(str(block.get("text", "")))
        if block.get("type") != "table"
        else "\n".join(" | ".join(str(cell) for cell in row) for row in block.get("rows", []))
        for block in blocks
        if block.get("text") or block.get("rows")
    )
    if not plain.strip():
        raise ExtractionError(f"empty_{source_type}")
    page_payload = pages or [{"page_number": 1, "blocks": blocks}]
    normalized_pages: list[dict[str, Any]] = []
    for index, page in enumerate(page_payload, start=1):
        normalized_page = dict(page)
        normalized_page.setdefault("page_number", index)
        if not str(normalized_page.get("markdown", "")).strip():
            normalized_page["markdown"] = _markdown_from_blocks(
                list(normalized_page.get("blocks") or [])
            )
        normalized_pages.append(normalized_page)
    return ExtractedDocument(
        plain_text=_clean_text(plain),
        markdown=markdown,
        payload={
            "version": 1,
            "source_type": source_type,
            "pages": normalized_pages,
            "page_count": len(normalized_pages),
        },
    )


def from_page_markdown(
    *,
    pages: list[dict[str, Any]],
    source_type: str,
    payload_extra: dict[str, Any] | None = None,
) -> ExtractedDocument:
    """페이지별 Markdown을 원문·payload 공통 구조로 정규화한다."""
    normalized_pages: list[dict[str, Any]] = []
    page_markdowns: list[str] = []
    for page in pages:
        markdown = str(page.get("markdown", "")).strip()
        page_number = int(page.get("page_number", len(normalized_pages) + 1))
        normalized = dict(page)
        normalized["page_number"] = page_number
        normalized["markdown"] = markdown
        normalized_pages.append(normalized)
        if markdown:
            page_markdowns.append(markdown)
    if not page_markdowns:
        raise ExtractionError("empty_page_markdown")
    markdown = "\n\n".join(page_markdowns).strip() + "\n"
    payload = {
        "version": 1,
        "source_type": source_type,
        "pages": normalized_pages,
        "page_count": len(normalized_pages),
    }
    if payload_extra:
        payload.update(payload_extra)
    return ExtractedDocument(
        plain_text=_clean_text(markdown),
        markdown=markdown,
        payload=payload,
    )


def from_ocr_blocks(
    *,
    pages: list[dict[str, Any]],
    tables: list[dict[str, Any]] | None = None,
    source_type: str = "ocr",
) -> ExtractedDocument:
    """외부 OCR 응답을 동일한 페이지·블록 구조로 정규화한다."""
    normalized_pages: list[dict[str, Any]] = []
    all_blocks: list[dict[str, Any]] = []
    for page in pages:
        page_blocks = [
            {"type": "paragraph", "text": str(line.get("content", ""))}
            for line in page.get("lines", [])
            if str(line.get("content", "")).strip()
        ]
        normalized_page = {
            "page_number": page.get("page_number"),
            "blocks": page_blocks,
            "markdown": _markdown_from_blocks(page_blocks),
        }
        normalized_pages.append(normalized_page)
        all_blocks.extend(page_blocks)
    for table in tables or []:
        rows: dict[int, dict[int, str]] = {}
        for cell in table.get("cells", []):
            rows.setdefault(int(cell.get("rowIndex", 0)), {})[int(cell.get("columnIndex", 0))] = (
                str(cell.get("content", ""))
            )
        ordered_rows = [
            [row.get(index, "") for index in range(max(row, default=-1) + 1)]
            for row in rows.values()
        ]
        if ordered_rows:
            all_blocks.append({"type": "table", "rows": ordered_rows})
    return _blocks_result(all_blocks, source_type, pages=normalized_pages)


class _HtmlTextParser:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def feed(self, source: str) -> None:
        # HTML is converted to text after scripts/styles are removed. This is deliberately
        # conservative; CSS-only visual layout is not treated as document structure.
        source = re.sub(
            r"<(script|style)[^>]*>.*?</\1>",
            " ",
            source,
            flags=re.IGNORECASE | re.DOTALL,
        )
        source = re.sub(r"<br\s*/?>", "\n", source, flags=re.IGNORECASE)
        source = re.sub(r"</(p|div|li|h[1-6]|tr|table)>", "\n", source, flags=re.IGNORECASE)
        source = re.sub(r"<[^>]+>", " ", source)
        self.parts.append(html.unescape(source))


def _html(content: bytes) -> ExtractedDocument:
    parser = _HtmlTextParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    return _from_text(parser.parts[0], source_type="html")


def _pdf(content: bytes) -> ExtractedDocument:
    inspected = _pdf_inspector(content)
    if inspected is not None:
        return inspected
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise ExtractionError("pdf_dependency_missing") from error
    try:
        reader = PdfReader(__import__("io").BytesIO(content))
        pages = [
            {
                "page_number": index + 1,
                "blocks": [{"type": "paragraph", "text": page.extract_text() or ""}],
            }
            for index, page in enumerate(reader.pages)
        ]
    except Exception as error:
        raise ExtractionError("invalid_pdf") from error
    blocks = [block for page in pages for block in page["blocks"]]
    # 텍스트 페이지와 스캔 페이지가 섞인 PDF는 텍스트가 있는 페이지만 RAG에
    # 넣으면 원문 일부가 조용히 누락된다. 빈 페이지가 하나라도 있으면 전체를
    # 페이지 단위 OCR 경로로 넘겨 두 종류를 함께 보존한다.
    if any(not str(page["blocks"][0].get("text", "")).strip() for page in pages):
        raise ExtractionError("ocr_required")
    return _blocks_result(blocks, "pdf", pages=pages)


def _pdf_inspector(content: bytes) -> ExtractedDocument | None:
    """설치되어 있으면 pdf-inspector를 우선 사용하고, 없으면 pypdf로 fallback한다."""
    _configure_pdfium()
    try:
        import pdf_inspector
    except ImportError:
        return None
    extract_pages = getattr(pdf_inspector, "extract_pages_markdown_bytes", None)
    if extract_pages is not None:
        try:
            result = extract_pages(content)
        except Exception:
            result = None
        if result is not None:
            page_results = _value_list(result, "pages")
            if page_results:
                pages: list[dict[str, Any]] = []
                pages_needing_ocr: list[int] = []
                for index, page in enumerate(page_results, start=1):
                    page_number = _value(page, "page")
                    page_number = int(page_number) + 1 if isinstance(page_number, int) else index
                    markdown = str(_value(page, "markdown") or "")
                    needs_ocr = bool(_value(page, "needs_ocr")) or not markdown.strip()
                    if needs_ocr:
                        pages_needing_ocr.append(page_number)
                    pages.append(
                        {
                            "page_number": page_number,
                            "markdown": markdown,
                            "needs_ocr": needs_ocr,
                            "ocr_reason": _value(page, "ocr_reason"),
                        }
                    )
                if pages_needing_ocr:
                    raise ExtractionError("ocr_required")
                if any(page["markdown"].strip() for page in pages):
                    return from_page_markdown(
                        pages=pages,
                        source_type="pdf_inspector",
                        payload_extra={
                            "extractor": "pdf_inspector",
                            "pages_needing_ocr": pages_needing_ocr,
                            "pages_with_tables": _value_list(result, "pages_with_tables"),
                            "pages_with_columns": _value_list(result, "pages_with_columns"),
                        },
                    )

    process = getattr(pdf_inspector, "process_pdf_bytes", None)
    if process is None:
        return None
    try:
        result = process(content)
    except Exception:
        # Inspector가 손상되었거나 지원하지 않는 PDF를 만나면 pypdf가
        # 표준적인 invalid_pdf/ocr_required 판정을 이어서 수행한다.
        return None
    markdown = getattr(result, "markdown", None)
    if callable(markdown):
        markdown = markdown()
    if not isinstance(markdown, str) or not markdown.strip():
        return None
    pdf_type = getattr(result, "pdf_type", None)
    if callable(pdf_type):
        pdf_type = pdf_type()
    page_count = getattr(result, "page_count", None)
    if callable(page_count):
        page_count = page_count()
    extracted = _from_text(markdown, source_type="pdf_inspector")
    payload = dict(extracted.payload)
    payload.update(
        {
            "pdf_type": str(pdf_type) if pdf_type is not None else None,
            "page_count": page_count if isinstance(page_count, int) else None,
            "extractor": "pdf_inspector",
        }
    )
    return ExtractedDocument(
        plain_text=extracted.plain_text,
        markdown=extracted.markdown,
        payload=payload,
    )


def _configure_pdfium() -> None:
    """pdf-inspector import 전에 pypdfium2의 플랫폼별 라이브러리 경로를 설정한다."""
    if os.environ.get("PDFIUM_LIB_PATH"):
        return
    try:
        import pypdfium2_raw
    except ImportError:
        return
    root = Path(pypdfium2_raw.__file__).parent
    candidates = (
        root / "libpdfium.dylib",
        root / "libpdfium.so",
        root / "libpdfium.dll",
        root / "pdfium.dll",
    )
    for candidate in candidates:
        if candidate.is_file():
            os.environ["PDFIUM_LIB_PATH"] = str(candidate)
            return


def _value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    candidate = getattr(value, key, None)
    if callable(candidate):
        candidate = candidate()
    return candidate


def _value_list(value: Any, key: str) -> list[Any]:
    result = _value(value, key)
    return result if isinstance(result, list) else []


def _hwp(content: bytes) -> ExtractedDocument:
    # Windows는 NamedTemporaryFile을 연 상태로 subprocess가 다시 열 수 없으므로
    # 파일을 닫은 뒤 실행하고 finally에서 삭제한다.
    command = shutil.which(settings.hwp5txt_path or "hwp5txt")
    if command is None:
        return _hwp_with_soffice(content)
    source_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as source:
            source.write(content)
            source_path = source.name
        try:
            result = subprocess.run(
                [command, source_path],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExtractionError("hwp_extractor_unavailable") from error
    finally:
        if source_path is not None:
            Path(source_path).unlink(missing_ok=True)
    if result.returncode != 0:
        raise ExtractionError("invalid_hwp")
    return _from_text(result.stdout, source_type="hwp")


def _hwp_with_soffice(content: bytes) -> ExtractedDocument:
    """hwp5txt가 없는 환경에서 LibreOffice headless로 HWP를 텍스트화한다."""
    command = shutil.which(settings.soffice_path or "soffice")
    if command is None:
        raise ExtractionError("hwp_extractor_unavailable")
    try:
        with tempfile.TemporaryDirectory(prefix="salesluv-hwp-") as work_dir:
            work_path = Path(work_dir)
            source_path = work_path / "document.hwp"
            output_path = work_path / "document.txt"
            profile_path = work_path / "libreoffice-profile"
            source_path.write_bytes(content)
            result = subprocess.run(
                [
                    command,
                    f"-env:UserInstallation={profile_path.as_uri()}",
                    "--headless",
                    "--convert-to",
                    "txt:Text",
                    "--outdir",
                    str(work_path),
                    str(source_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            if result.returncode != 0 or not output_path.is_file():
                raise ExtractionError("invalid_hwp")
            text = output_path.read_text(encoding="utf-8", errors="replace")
    except ExtractionError:
        raise
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExtractionError("hwp_extractor_unavailable") from error
    return _from_text(text, source_type="hwp")


def extract_document(
    *, file_name: str, media_type: str | None, content: bytes
) -> ExtractedDocument:
    suffix = Path(file_name).suffix.lower()
    if suffix in {".txt", ".text", ".md", ".markdown"}:
        return _from_text(content.decode("utf-8", errors="replace"), source_type="text")
    if suffix in {".html", ".htm"} or media_type == "text/html":
        return _html(content)
    if suffix == ".docx":
        return _docx(content)
    if suffix == ".pptx":
        return _pptx(content)
    if suffix == ".pdf" or media_type == "application/pdf":
        return _pdf(content)
    if suffix == ".hwp":
        return _hwp(content)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        raise ExtractionError("ocr_provider_required")
    raise ExtractionError("unsupported_document_type")
