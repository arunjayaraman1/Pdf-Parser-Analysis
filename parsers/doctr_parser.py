from __future__ import annotations

import json
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class DocTRParser(BasePDFParser):
    name = "DocTR"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            from doctr.io import DocumentFile
            from doctr.models import ocr_predictor

            predictor = ocr_predictor(pretrained=True)
            doc = DocumentFile.from_pdf(path)
            parsed = predictor(doc)
            exp = parsed.export()
            pages = exp.get("pages", [])
            result.pages_processed = len(pages)

            text_chunks: list[str] = []
            for page in pages:
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        words = [w.get("value", "") for w in line.get("words", [])]
                        text_chunks.append(" ".join(w for w in words if w))

            result.text = "\n".join(text_chunks).strip()
            result.structured = exp
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
