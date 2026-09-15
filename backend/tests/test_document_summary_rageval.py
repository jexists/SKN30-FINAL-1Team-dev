from pathlib import Path

from scripts import document_summary_rageval


def test_default_rageval_sources_are_synthetic_and_include_scope_boundaries():
    paths = document_summary_rageval.default_source_paths(
        Path(__file__).parents[2] / "test-data" / "briefing-rag-lite"
    )

    names = [path.name for path in paths]
    assert "03_초음파도입_납품계약서.pdf" in names
    assert "05_다른고객사_제외자료.txt" in names
    assert "07_다른담당자_비공개자료.txt" in names


def test_local_retriever_respects_allowed_source_files():
    source_dir = Path(__file__).parents[2] / "test-data" / "briefing-rag-lite"
    sources = document_summary_rageval.load_sources(
        [source_dir / "04_같은고객사_설치점검.txt", source_dir / "05_다른고객사_제외자료.txt"]
    )

    matches = document_summary_rageval.retrieve(
        sources,
        query="BLUE-731 검수코드",
        allowed_source_files=["04_같은고객사_설치점검.txt"],
    )

    assert matches == []


def test_local_retriever_returns_page_and_source_metadata():
    source_dir = Path(__file__).parents[2] / "test-data" / "briefing-rag-lite"
    sources = document_summary_rageval.load_sources(
        [source_dir / "03_초음파도입_납품계약서.pdf"]
    )

    matches = document_summary_rageval.retrieve(
        sources,
        query="BLUE-731 검수코드",
        allowed_source_files=["03_초음파도입_납품계약서.pdf"],
    )

    assert matches
    assert matches[0]["file_name"] == "03_초음파도입_납품계약서.pdf"
    assert matches[0]["page_start"] in {1, 2}
