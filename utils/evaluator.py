from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from parsers.base import ParseResult


@dataclass
class Recommendation:
    parser_name: str
    score: float
    reason: str


def infer_document_type(results: Iterable[ParseResult]) -> str:
    results = list(results)
    table_count = sum(len(r.tables) for r in results)
    avg_text = (sum(len(r.text) for r in results) / max(1, len(results))) if results else 0
    avg_pages = (sum(r.pages_processed for r in results) / max(1, len(results))) if results else 0
    if avg_text < 700 and avg_pages > 0:
        return "scanned_or_image_heavy"
    if table_count >= 3:
        return "table_heavy"
    return "textual_structured"


def score_result(result: ParseResult, doc_type: str) -> float:
    quality = min(1.0, len(result.text) / 4000)
    structure = min(1.0, len(result.structured.keys()) / 8)
    tables = min(1.0, len(result.tables) / 3)
    speed = 1.0 / max(result.execution_time_sec, 0.01)
    speed = min(speed / 30.0, 1.0)
    reliability_penalty = 0.15 * len(result.errors)

    if doc_type == "table_heavy":
        score = 0.4 * tables + 0.2 * quality + 0.2 * structure + 0.2 * speed
    elif doc_type == "scanned_or_image_heavy":
        ocr_signal = 1.0 if "ocr" in result.parser_name.lower() else 0.4
        score = 0.35 * quality + 0.2 * structure + 0.2 * speed + 0.25 * ocr_signal
    else:
        score = 0.4 * quality + 0.35 * structure + 0.15 * tables + 0.1 * speed
    return max(0.0, score - reliability_penalty)


def recommend_parser(results: list[ParseResult]) -> Recommendation:
    if not results:
        return Recommendation(parser_name="N/A", score=0.0, reason="No parsers were executed.")
    doc_type = infer_document_type(results)
    scored = [(r, score_result(r, doc_type)) for r in results]
    best, best_score = max(scored, key=lambda t: t[1])
    reason = (
        f"Document type inferred as '{doc_type}'. "
        f"{best.parser_name} had the best weighted blend of extraction quality, structure, and speed."
    )
    return Recommendation(parser_name=best.parser_name, score=best_score, reason=reason)
