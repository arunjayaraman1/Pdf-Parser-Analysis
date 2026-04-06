from __future__ import annotations

import json
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class DoclingParser(BasePDFParser):
    name = "Docling"
    license_name = "MIT"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
            doc = converter.convert(str(path))
            markdown_text = doc.document.export_to_markdown()
            result.text = markdown_text
            result.structured = {"markdown_preview": markdown_text[:10000]}
            (out / "result.md").write_text(markdown_text, encoding="utf-8")
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
