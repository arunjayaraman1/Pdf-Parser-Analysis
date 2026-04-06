from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class UnstructuredParser(BasePDFParser):
    name = "Unstructured (advanced)"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            from unstructured.partition.pdf import partition_pdf

            chunks = partition_pdf(
                filename=str(path),
                strategy="hi_res",
                infer_table_structure=True,
                extract_images_in_pdf=True,
            )
            text_parts: list[str] = []
            items: list[dict[str, str]] = []
            max_page = 0
            for c in chunks:
                metadata = getattr(c, "metadata", None)
                page_num = getattr(metadata, "page_number", None) if metadata else None
                if isinstance(page_num, int):
                    max_page = max(max_page, page_num)
                items.append({"type": c.category, "text": str(c)})
                text_parts.append(str(c))
                if c.category and "table" in c.category.lower():
                    result.tables.append({"page": page_num, "text": str(c)})
            result.pages_processed = max_page
            result.text = "\n".join(text_parts).strip()
            result.structured = {"elements": items[:200]}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)


class LayoutParserEngine(BasePDFParser):
    name = "LayoutParser"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            import cv2
            import layoutparser as lp
            import fitz

            if importlib.util.find_spec("detectron2") is None:
                raise RuntimeError(
                    "detectron2 is required by LayoutParser's Detectron2 backend. "
                    "Install detectron2 or skip LayoutParser in this environment."
                )

            model = lp.models.Detectron2LayoutModel(
                "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config",
                extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5],
            )
            doc = fitz.open(path)
            result.pages_processed = len(doc)
            regions: list[dict[str, object]] = []
            image_dir = out / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=150)
                img_path = image_dir / f"page-{i + 1}.png"
                pix.save(img_path)
                result.images.append(str(img_path))
                image = cv2.imread(str(img_path))
                layout = model.detect(image)
                for block in layout:
                    regions.append(
                        {"page": i + 1, "type": block.type, "score": float(block.score), "coords": list(block.coordinates)}
                    )
            result.structured = {"regions": regions}
            result.text = f"Detected {len(regions)} layout regions."
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)


class GrobidParser(BasePDFParser):
    name = "GROBID"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            import requests
            from requests import RequestException

            grobid_url = "http://localhost:8070/api/processFulltextDocument"
            try:
                with path.open("rb") as f:
                    response = requests.post(grobid_url, files={"input": f}, timeout=120)
                response.raise_for_status()
            except RequestException as exc:
                raise RuntimeError(
                    "Could not reach GROBID at http://localhost:8070. "
                    "Start the GROBID server or skip this parser."
                ) from exc
            xml = response.text
            result.text = xml
            result.structured = {"tei_xml": xml[:20000]}
            result.notes.append("Requires a running GROBID server at http://localhost:8070")
            (out / "result.xml").write_text(xml, encoding="utf-8")
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
