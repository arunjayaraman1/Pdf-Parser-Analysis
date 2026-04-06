from __future__ import annotations

import json
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class PyMuPDFParser(BasePDFParser):
    name = "PyMuPDF (fitz)"
    license_name = "AGPL-3.0"
    commercial_use_ok = False

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            import fitz

            text_chunks: list[str] = []
            doc = fitz.open(path)
            result.pages_processed = len(doc)
            image_dir = out / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            for page_idx, page in enumerate(doc):
                text_chunks.append(page.get_text("text"))
                image_refs = page.get_images(full=True)
                for img_i, img in enumerate(image_refs):
                    xref = img[0]
                    img_obj = doc.extract_image(xref)
                    ext = img_obj.get("ext", "png")
                    img_path = image_dir / f"page-{page_idx + 1}-img-{img_i + 1}.{ext}"
                    img_path.write_bytes(img_obj["image"])
                    result.images.append(str(img_path))
            result.text = "\n".join(text_chunks).strip()
            result.structured = {
                "pages": result.pages_processed,
                "text_length": len(result.text),
                "image_count": len(result.images),
            }
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
