from __future__ import annotations

import json
import inspect
from pathlib import Path
from typing import Iterable

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


def _paddleocr_page_text(ocr: object, page_path: Path) -> str:
    """PaddleOCR 3.x: ``predict`` + ``rec_texts``; legacy 2.x: nested box lists."""
    lines: list[str] = []
    predict = getattr(ocr, "predict", None)
    if not callable(predict):
        return ""
    for res in predict(str(page_path)) or []:
        if isinstance(res, dict) and "rec_texts" in res:
            for x in res["rec_texts"]:
                lines.append(str(x[0]) if isinstance(x, tuple) and len(x) >= 1 else str(x))
            continue
        j = getattr(res, "json", None)
        if isinstance(j, dict):
            inner = j.get("res")
            if isinstance(inner, dict) and "rec_texts" in inner:
                for x in inner["rec_texts"]:
                    lines.append(str(x[0]) if isinstance(x, tuple) and len(x) >= 1 else str(x))
                continue
        if isinstance(res, list):
            for item in res or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    tp = item[1]
                    if isinstance(tp, (list, tuple)) and len(tp) >= 1:
                        lines.append(str(tp[0]))
                    elif isinstance(tp, str):
                        lines.append(tp)
    return "\n".join(lines)


def _render_pages_to_images(pdf_path: Path, out_dir: Path) -> Iterable[Path]:
    import fitz

    image_dir = out_dir / "ocr_pages"
    image_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    for idx, page in enumerate(doc):
        pix = page.get_pixmap(dpi=200)
        path = image_dir / f"page-{idx + 1}.png"
        pix.save(path)
        yield path


class TesseractOCRParser(BasePDFParser):
    name = "Tesseract OCR (pytesseract)"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            from PIL import Image
            import pytesseract

            pages = list(_render_pages_to_images(path, out))
            result.pages_processed = len(pages)
            text_parts: list[str] = []
            for p in pages:
                text_parts.append(pytesseract.image_to_string(Image.open(p)))
            result.text = "\n".join(text_parts).strip()
            result.structured = {"pages": result.pages_processed, "engine": "tesseract"}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)


class EasyOCRParser(BasePDFParser):
    name = "EasyOCR"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            import easyocr

            pages = list(_render_pages_to_images(path, out))
            result.pages_processed = len(pages)
            reader = easyocr.Reader(["en"], gpu=False)
            text_parts: list[str] = []
            for p in pages:
                chunks = reader.readtext(str(p), detail=0)
                text_parts.append("\n".join(chunks))
            result.text = "\n".join(text_parts).strip()
            result.structured = {"pages": result.pages_processed, "engine": "easyocr"}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)


class PaddleOCRParser(BasePDFParser):
    name = "PaddleOCR"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            from paddleocr import PaddleOCR

            pages = list(_render_pages_to_images(path, out))
            result.pages_processed = len(pages)
            sig = inspect.signature(PaddleOCR.__init__)
            kwargs: dict = {"lang": "en"}
            if "use_textline_orientation" in sig.parameters:
                kwargs["use_textline_orientation"] = True
            elif "use_angle_cls" in sig.parameters:
                kwargs["use_angle_cls"] = True
            if "use_gpu" in sig.parameters:
                kwargs["use_gpu"] = False
            if "use_doc_orientation_classify" in sig.parameters:
                kwargs["use_doc_orientation_classify"] = False
            if "use_doc_unwarping" in sig.parameters:
                kwargs["use_doc_unwarping"] = False
            ocr = PaddleOCR(**kwargs)
            text_parts: list[str] = []
            for p in pages:
                text_parts.append(_paddleocr_page_text(ocr, p))
            result.text = "\n".join(text_parts).strip()
            result.structured = {"pages": result.pages_processed, "engine": "paddleocr"}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
