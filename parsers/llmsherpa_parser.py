from __future__ import annotations

import json
import os
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class LLMSherpaParser(BasePDFParser):
    name = "LLMSherpa"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            from llmsherpa.readers import LayoutPDFReader

            api_url = os.getenv("LLMSHERPA_API_URL", "https://readers.llmsherpa.com/api/document/developer/parseDocument")
            # llmsherpa has had constructor signature changes across versions.
            try:
                reader = LayoutPDFReader(api_url=api_url)
            except TypeError:
                try:
                    reader = LayoutPDFReader(api_url)
                except TypeError:
                    reader = LayoutPDFReader()
            doc = reader.read_pdf(str(path))
            chunks = []
            for node in doc.chunks():
                chunks.append(node.to_text())
            result.text = "\n".join(chunks).strip()
            result.structured = {"chunks": len(chunks), "api_url": api_url}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
