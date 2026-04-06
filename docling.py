"""
Convert a PDF (local path or URL) with Docling and write Markdown + JSON under an output folder.

Local file ``docling.py`` shadows the installed ``docling`` package — we strip this directory
from sys.path before importing.

Why images were missing before: the default PDF pipeline leaves ``generate_page_images`` and
``generate_picture_images`` off, and plain ``export_to_markdown()`` does not write PNG files.
With DOCLING_IMAGES=1 (default), we enable those flags and use ``save_as_markdown(..., REFERENCED)``
so figures/page images are saved under docling_media/ (see Docling CLI).

Environment (optional):
  DOCLING_SOURCE          — path or https URL (default: Holiday 2026.pdf or first *.pdf in cwd)
  DOCLING_MAX_PAGES       — max pages per document (passed to DocumentConverter.convert)
  DOCLING_PAGE_RANGE      — e.g. 1-5 or 3 (single page) — 1-based inclusive range
  DOCLING_SKIP_JSON       — set to 1 to skip writing document.json (large files)
  DOCLING_IMAGES          — set to 0 to skip image rasterization/export (faster; md/json text-only)
  DOCLING_IMAGES_SCALE    — pipeline images_scale when DOCLING_IMAGES=1 (default 2, like docling CLI)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Local file ``docling.py`` shadows the ``docling`` package.
_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR in sys.path:
    sys.path.remove(_THIS_DIR)

from docling.datamodel.base_models import ConversionStatus, InputFormat  # noqa: E402
from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: E402
from docling.datamodel.settings import DEFAULT_PAGE_RANGE  # noqa: E402
from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: E402
from docling_core.types.doc.base import ImageRefMode  # noqa: E402


def _pick_local_pdf(cwd: Path) -> Path:
    pdf = cwd / "Holiday 2026.pdf"
    if pdf.exists():
        return pdf
    matches = sorted(cwd.glob("*.pdf"))
    if not matches:
        raise FileNotFoundError(
            "No PDF found. Set DOCLING_SOURCE to a file or URL, or add a .pdf in the project directory."
        )
    return matches[0]


def _resolve_source(cwd: Path) -> str:
    raw = os.environ.get("DOCLING_SOURCE", "").strip()
    if raw:
        return raw
    return str(_pick_local_pdf(cwd))


def _stem_for_output(source: str) -> str:
    if source.startswith(("http://", "https://")):
        path = urlparse(source).path
        name = Path(path).name
        if name and "." in name:
            return name.rsplit(".", 1)[0]
        return name or "remote_document"
    return Path(source).resolve().stem


def _max_num_pages() -> int:
    raw = os.environ.get("DOCLING_MAX_PAGES", "").strip()
    if not raw:
        return sys.maxsize
    try:
        return max(1, int(raw))
    except ValueError:
        return sys.maxsize


def _page_range() -> tuple[int, int]:
    raw = os.environ.get("DOCLING_PAGE_RANGE", "").strip()
    if not raw:
        return DEFAULT_PAGE_RANGE
    if "-" in raw:
        a, b = raw.split("-", 1)
        return (int(a.strip()), int(b.strip()))
    n = int(raw)
    return (n, n)


def _export_images() -> bool:
    return os.environ.get("DOCLING_IMAGES", "1").lower() not in ("0", "false", "no")


def _images_scale() -> float:
    raw = os.environ.get("DOCLING_IMAGES_SCALE", "2").strip()
    try:
        return max(0.25, float(raw))
    except ValueError:
        return 2.0


def _make_converter() -> DocumentConverter:
    if not _export_images():
        return DocumentConverter()
    opts = PdfPipelineOptions(
        generate_page_images=True,
        generate_picture_images=True,
        images_scale=_images_scale(),
    )
    pdf_opt = PdfFormatOption(pipeline_options=opts)
    return DocumentConverter(format_options={InputFormat.PDF: pdf_opt})


def main() -> None:
    cwd = Path(__file__).resolve().parent
    source = _resolve_source(cwd)
    stem = _stem_for_output(source)
    out_root = cwd / f"{stem}_extracted_docling"
    out_root.mkdir(parents=True, exist_ok=True)

    converter = _make_converter()
    max_pages = _max_num_pages()
    page_range = _page_range()
    want_images = _export_images()

    print(
        f"Docling: converting {source!r} (max_num_pages={max_pages}, page_range={page_range}, "
        f"images={'on' if want_images else 'off'}) …",
        file=sys.stderr,
    )
    t0 = time.perf_counter()
    result = converter.convert(
        source,
        max_num_pages=max_pages,
        page_range=page_range,
    )
    elapsed = time.perf_counter() - t0

    if result.status not in (
        ConversionStatus.SUCCESS,
        ConversionStatus.PARTIAL_SUCCESS,
    ):
        err_txt = json.dumps(
            [e.model_dump(mode="json") if hasattr(e, "model_dump") else str(e) for e in result.errors],
            indent=2,
            default=str,
        )
        print(
            f"Conversion status: {result.status}. Errors:\n{err_txt}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    extracted_md = out_root / "extracted.md"
    json_path = out_root / "document.json"
    skip_json = os.environ.get("DOCLING_SKIP_JSON", "").lower() in ("1", "true", "yes")
    media_dir = out_root / "docling_media"

    if want_images:
        media_dir.mkdir(parents=True, exist_ok=True)
        result.document.save_as_markdown(
            filename=extracted_md,
            artifacts_dir=media_dir,
            image_mode=ImageRefMode.REFERENCED,
        )
        if not skip_json:
            try:
                result.document.save_as_json(
                    filename=json_path,
                    artifacts_dir=media_dir,
                    image_mode=ImageRefMode.REFERENCED,
                )
            except Exception as exc:
                json_path.write_text(
                    json.dumps({"error": str(exc), "hint": "Try DOCLING_SKIP_JSON=1"}, indent=2),
                    encoding="utf-8",
                )
    else:
        extracted_md.write_text(result.document.export_to_markdown(), encoding="utf-8")
        if not skip_json:
            try:
                doc_dict = result.document.export_to_dict()
                json_path.write_text(
                    json.dumps(doc_dict, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8",
                )
            except Exception as exc:
                json_path.write_text(
                    json.dumps({"error": str(exc), "hint": "Try DOCLING_SKIP_JSON=1"}, indent=2),
                    encoding="utf-8",
                )

    summary_txt = out_root / "summary.txt"
    summary_lines = [
        "--- Docling extraction summary ---",
        f"Source: {source}",
        f"Output folder: {out_root}",
        f"Status: {result.status.value}",
        f"Image export: {'enabled (pipeline + referenced PNGs in docling_media/)' if want_images else 'disabled (DOCLING_IMAGES=0)'}",
        f"max_num_pages: {max_pages}",
        f"page_range: {page_range}",
        f"Time: {elapsed:.2f} s",
        f"Markdown: {extracted_md.name}",
    ]
    if want_images:
        summary_lines.append(f"Images / media: {media_dir.name}/")
    if not skip_json:
        summary_lines.append(f"JSON: {json_path.name}")
    else:
        summary_lines.append("JSON: skipped (DOCLING_SKIP_JSON)")
    summary_lines.append("")
    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote: {extracted_md}")
    if want_images:
        print(f"Wrote: {media_dir}/ (referenced images)")
    if not skip_json:
        print(f"Wrote: {json_path}")
    print(f"Wrote: {summary_txt}")


if __name__ == "__main__":
    main()
