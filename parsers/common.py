from __future__ import annotations

from pathlib import Path
from typing import Callable

from parsers.base import ParseResult
from utils.memory import memory_profiled
from utils.timer import timed


def _rss_mb() -> float | None:
    try:
        import os

        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return None


def profiled_parse(
    parser_name: str,
    license_name: str,
    commercial_use_ok: bool,
    parse_fn: Callable[[Path, Path, ParseResult], None],
    pdf_path: Path,
    output_dir: Path,
) -> ParseResult:
    result = ParseResult(
        parser_name=parser_name,
        license_name=license_name,
        commercial_use_ok=commercial_use_ok,
    )
    rss_before = _rss_mb()
    with timed() as t, memory_profiled() as m:
        try:
            parse_fn(pdf_path, output_dir, result)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{type(exc).__name__}: {exc}")
    result.execution_time_sec = t["seconds"]
    result.memory_delta_mb = m["delta_mb"]
    rss_after = _rss_mb()
    if rss_before is not None and rss_after is not None:
        result.memory_rss_delta_mb = max(0.0, rss_after - rss_before)
    return result
