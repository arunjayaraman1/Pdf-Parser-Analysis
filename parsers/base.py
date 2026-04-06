from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def seconds_per_10_pages(execution_time_sec: float, pages_processed: int) -> float | None:
    """Normalized latency: extrapolated seconds for 10 pages. None if pages unknown/zero."""
    if pages_processed <= 0:
        return None
    return (execution_time_sec / pages_processed) * 10.0


@dataclass
class ParseResult:
    parser_name: str
    license_name: str
    commercial_use_ok: bool
    execution_time_sec: float = 0.0
    memory_delta_mb: float = 0.0
    memory_rss_delta_mb: float = 0.0
    pages_processed: int = 0
    text: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    structured: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def seconds_per_10_pages(self) -> float | None:
        return seconds_per_10_pages(self.execution_time_sec, self.pages_processed)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        sp = self.seconds_per_10_pages()
        if sp is not None:
            d["seconds_per_10_pages"] = sp
        return d


class BasePDFParser(ABC):
    name = "base-parser"
    license_name = "Unknown"
    commercial_use_ok = True

    @abstractmethod
    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        raise NotImplementedError
