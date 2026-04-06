from parsers.base import ParseResult, seconds_per_10_pages
from parsers.registry import get_all_parsers, get_commercial_parsers, get_commercial_parsers_local_only


def test_seconds_per_10_pages() -> None:
    assert seconds_per_10_pages(20.0, 10) == 20.0
    assert seconds_per_10_pages(10.0, 5) == 20.0
    assert seconds_per_10_pages(1.0, 0) is None


def test_parse_result_seconds_per_10_pages_method() -> None:
    r = ParseResult(
        parser_name="x",
        license_name="MIT",
        commercial_use_ok=True,
        execution_time_sec=30.0,
        pages_processed=15,
    )
    assert r.seconds_per_10_pages() == 20.0


def test_commercial_parsers_excludes_agpl_pymupdf() -> None:
    all_names = {p.name for p in get_all_parsers()}
    commercial_names = {p.name for p in get_commercial_parsers()}
    assert "PyMuPDF (fitz)" in all_names
    assert "PyMuPDF (fitz)" not in commercial_names


def test_local_only_excludes_llmsherpa() -> None:
    local = {p.name for p in get_commercial_parsers_local_only()}
    assert "LLMSherpa" not in local
    assert "pdfplumber" in local


def test_streamlit_registry_includes_script_parsers() -> None:
    names = {p.name for p in get_all_parsers()}
    assert "RapidOCR PDF" in names
    assert "Surya OCR" in names
    assert "Marker" in names


def test_commercial_guide_import() -> None:
    from utils.commercial_guide import suggested_parsers_for_scenario

    assert "Camelot" in suggested_parsers_for_scenario("complex_tables")
