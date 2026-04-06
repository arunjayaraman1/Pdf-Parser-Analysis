from parsers.base import ParseResult
from utils.evaluator import infer_document_type, recommend_parser


def test_infer_table_heavy_document() -> None:
    r1 = ParseResult(parser_name="a", license_name="MIT", commercial_use_ok=True, tables=[{"a": 1}] * 3)
    r2 = ParseResult(parser_name="b", license_name="MIT", commercial_use_ok=True, tables=[{"a": 1}] * 2)
    assert infer_document_type([r1, r2]) == "table_heavy"


def test_recommend_parser_prefers_quality_without_errors() -> None:
    slow_but_good = ParseResult(
        parser_name="good",
        license_name="MIT",
        commercial_use_ok=True,
        execution_time_sec=2.5,
        text="x" * 6000,
        structured={"a": 1, "b": 2, "c": 3},
    )
    fast_but_bad = ParseResult(
        parser_name="bad",
        license_name="MIT",
        commercial_use_ok=True,
        execution_time_sec=0.1,
        text="short",
        errors=["failed"],
    )
    rec = recommend_parser([slow_but_good, fast_but_bad])
    assert rec.parser_name == "good"
