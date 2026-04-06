from __future__ import annotations

import json
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class PDFPlumberParser(BasePDFParser):
    name = "pdfplumber"
    license_name = "MIT"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            import pdfplumber

            text_parts: list[str] = []
            with pdfplumber.open(path) as pdf:
                result.pages_processed = len(pdf.pages)
                for p_idx, page in enumerate(pdf.pages):
                    text_parts.append(page.extract_text() or "")
                    table = page.extract_table()
                    if table:
                        result.tables.append({"page": p_idx + 1, "rows": table})
            result.text = "\n".join(text_parts).strip()
            result.structured = {"tables_found": len(result.tables), "pages": result.pages_processed}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)


class PDFMinerParser(BasePDFParser):
    name = "pdfminer.six"
    license_name = "MIT"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            from pdfminer.high_level import extract_pages, extract_text

            result.text = (extract_text(path) or "").strip()
            result.pages_processed = sum(1 for _ in extract_pages(path))
            result.structured = {"pages": result.pages_processed, "text_length": len(result.text)}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
