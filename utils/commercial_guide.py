from __future__ import annotations

from typing import Iterable

from parsers.base import ParseResult

# Scenario labels match benchmark/fixtures/README.md
SCENARIOS = (
    "complex_tables",
    "multipage_tables",
    "hierarchical_text",
    "scanned",
)

# Rule-based default order (parser display names) when no benchmark run exists yet.
_SCENARIO_DEFAULT_ORDER: dict[str, list[str]] = {
    "complex_tables": [
        "Camelot",
        "Tabula-py",
        "Unstructured (advanced)",
        "pdfplumber",
        "Docling",
    ],
    "multipage_tables": [
        "Camelot",
        "Tabula-py",
        "Unstructured (advanced)",
        "pdfplumber",
    ],
    "hierarchical_text": [
        "Unstructured (advanced)",
        "Docling",
        "pdfplumber",
        "pdfminer.six",
        "GROBID",
    ],
    "scanned": [
        "Tesseract OCR (pytesseract)",
        "EasyOCR",
        "PaddleOCR",
        "DocTR",
        "Unstructured (advanced)",
    ],
}


def suggested_parsers_for_scenario(scenario: str) -> list[str]:
    """Static ranking of parsers to try first for a document scenario (commercial-agnostic)."""
    return list(_SCENARIO_DEFAULT_ORDER.get(scenario, []))


def rank_parsers_for_scenario(scenario: str, results: Iterable[ParseResult]) -> list[tuple[str, float]]:
    """
    Rank parsers using benchmark results for a scenario.
    Higher score is better: prefers no errors, more text, more tables when scenario is table-heavy.
    """
    results = list(results)
    ranked: list[tuple[str, float]] = []
    for r in results:
        if r.errors:
            ranked.append((r.parser_name, -1.0))
            continue
        score = 0.0
        score += min(1.0, len(r.text) / 8000.0) * 3.0
        score += min(1.0, len(r.structured) / 10.0)
        if scenario in ("complex_tables", "multipage_tables"):
            score += min(2.0, len(r.tables) * 0.5)
        if scenario == "scanned":
            if "ocr" in r.parser_name.lower() or "DocTR" in r.parser_name:
                score += 1.5
        if scenario == "hierarchical_text":
            score += min(1.5, len(r.text) / 12000.0)
        score += max(0.0, 1.0 - r.execution_time_sec / 120.0)
        ranked.append((r.parser_name, score))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def best_parser_for_scenario(scenario: str, results: list[ParseResult]) -> str | None:
    ranked = rank_parsers_for_scenario(scenario, results)
    for name, sc in ranked:
        if sc >= 0:
            return name
    return None
