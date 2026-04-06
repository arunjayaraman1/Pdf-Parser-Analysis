from __future__ import annotations

import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

# Avoid any import shadowing from this script's directory.
THIS_DIR = str(Path(__file__).resolve().parent)
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)


def _format_duration_sec(total_sec: float) -> tuple[int, float]:
    mins = int(total_sec // 60)
    secs = total_sec - 60 * mins
    return mins, secs


def _extract_embedded_images(pdf_path: Path, images_dir: Path) -> int:
    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError:
        return -1

    images_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    written = 0
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            for img_index, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                try:
                    base = doc.extract_image(xref)
                except Exception:
                    continue
                raw = base["image"]
                ext = (base.get("ext") or "png").lower()
                if ext not in ("png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"):
                    ext = "png"
                name = f"page{page_index + 1}_img{img_index + 1}_xref{xref}.{ext}"
                (images_dir / name).write_bytes(raw)
                written += 1
    finally:
        doc.close()
    return written


def _extract_body_text_per_page(pdf_path: Path) -> tuple[str, int, str]:
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(pdf_path)) as pdf:
            n = len(pdf.pages)
            blocks: list[str] = []
            for i, page in enumerate(pdf.pages):
                raw = (page.extract_text() or "").strip()
                blocks.append(f"--- Page {i + 1} / {n} ---\n{raw}")
        return "\n\n".join(blocks), n, "pdfplumber"
    except ModuleNotFoundError:
        pass
    except Exception:
        pass

    try:
        from pdfminer.high_level import extract_text  # type: ignore

        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        n = len(doc)
        doc.close()
        blocks: list[str] = []
        for i in range(n):
            raw = (extract_text(str(pdf_path), page_numbers=[i]) or "").strip()
            blocks.append(f"--- Page {i + 1} / {n} ---\n{raw}")
        return "\n\n".join(blocks), n, "pdfminer.six"
    except ModuleNotFoundError:
        pass

    return (
        "(No full-text extractor: install pdfplumber or pdfminer.six — "
        "pip install pdfplumber pdfminer.six)",
        0,
        "none",
    )


def _partition_strategy() -> str:
    s = os.environ.get("UNSTRUCTURED_STRATEGY", "hi_res").strip().lower()
    if s in ("hi_res", "fast", "ocr_only"):
        return s
    return "hi_res"


def main() -> None:
    try:
        from unstructured.partition.pdf import partition_pdf  # type: ignore  # noqa: E402
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "unstructured is not installed. Install with: python -m pip install 'unstructured[all-docs]'"
        ) from exc

    pdf_path = Path("Holiday 2026.pdf")
    if not pdf_path.exists():
        matches = sorted(Path(".").glob("Meta-Harness*.pdf"))
        if not matches:
            raise FileNotFoundError("Could not find target PDF in the current directory.")
        pdf_path = matches[0]

    out_root = pdf_path.parent / f"{pdf_path.stem}_extracted_unstructured"
    out_root.mkdir(parents=True, exist_ok=True)
    extracted_txt = out_root / "extracted.txt"
    summary_txt = out_root / "summary.txt"
    elements_json = out_root / "elements.json"
    images_dir = out_root / "images"
    images_zip = out_root / "images.zip"

    strategy = _partition_strategy()
    t0 = time.perf_counter()

    body_text, num_pages, text_source = _extract_body_text_per_page(pdf_path)
    if num_pages == 0:
        import fitz  # PyMuPDF

        _doc = fitz.open(pdf_path)
        num_pages = len(_doc)
        _doc.close()

    part2_lines: list[str] = []
    items: list[dict[str, object]] = []
    table_count = 0
    max_page = 0
    total_elements = 0

    try:
        chunks = partition_pdf(
            filename=str(pdf_path),
            strategy=strategy,
            infer_table_structure=True,
            extract_images_in_pdf=True,
        )
        total_elements = len(chunks)
        max_json = int(os.environ.get("UNSTRUCTURED_JSON_MAX_ELEMENTS", "500"))
        for idx, c in enumerate(chunks):
            metadata = getattr(c, "metadata", None)
            page_num = getattr(metadata, "page_number", None) if metadata else None
            if isinstance(page_num, int):
                max_page = max(max_page, page_num)
            cat = getattr(c, "category", type(c).__name__)
            text = str(c)
            if cat and "table" in str(cat).lower():
                table_count += 1
            part2_lines.append(f"--- Element {idx + 1} [{cat}] page={page_num} ---\n{text}")
            if len(items) < max_json:
                items.append(
                    {
                        "index": idx + 1,
                        "category": str(cat),
                        "page_number": page_num,
                        "text": text[:100000],
                    }
                )
        unstructured_section = "\n\n".join(part2_lines) if part2_lines else "(no elements returned)"
    except Exception as exc:
        unstructured_section = f"Unstructured partition_pdf failed: {type(exc).__name__}: {exc}"
        chunks = []
        total_elements = 0
        items = []

    elements_json.write_text(
        json.dumps(
            {
                "strategy": strategy,
                "element_count_total": total_elements,
                "elements_in_json": len(items),
                "tables_detected_as_elements": table_count,
                "max_page_from_metadata": max_page,
                "elements": items,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    full_text = "\n".join(
        [
            "=" * 80,
            "PART 1 — Full document text (text layer)",
            f"Source: {text_source}",
            "=" * 80,
            "",
            body_text,
            "",
            "=" * 80,
            "PART 2 — Unstructured partition_pdf",
            f"Strategy: {strategy} (set UNSTRUCTURED_STRATEGY=hi_res|fast|ocr_only)",
            "=" * 80,
            "",
            unstructured_section,
        ]
    )

    (out_root / "document_text.txt").write_text(
        body_text if text_source != "none" else "",
        encoding="utf-8",
    )

    elapsed = time.perf_counter() - t0
    mins, secs = _format_duration_sec(elapsed)

    extracted_txt.write_text(full_text, encoding="utf-8")

    img_count = _extract_embedded_images(pdf_path, images_dir)
    if img_count == -1:
        img_note = "Embedded images: skipped (install PyMuPDF: python -m pip install PyMuPDF)"
        images_zip.unlink(missing_ok=True)
    elif img_count == 0:
        if images_dir.exists():
            shutil.rmtree(images_dir, ignore_errors=True)
        images_zip.unlink(missing_ok=True)
        img_note = "Embedded images: none found in PDF"
    else:
        img_note = f"Embedded images: {img_count} file(s) in {images_dir.name}/"
        if images_zip.exists():
            images_zip.unlink()
        with zipfile.ZipFile(images_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(images_dir.iterdir()):
                if f.is_file():
                    zf.write(f, arcname=f.name)
        img_note += f" and {images_zip.name}"

    data_types = [
        f"full text layer ({text_source})",
        f"Unstructured elements (strategy={strategy})",
        f"elements JSON (cap {os.environ.get('UNSTRUCTURED_JSON_MAX_ELEMENTS', '500')}): {elements_json.name}",
        f"approx. table-like elements: {table_count}",
        f"PDF pages (text layer): {num_pages}",
        "document_text.txt = part 1 only",
    ]
    if img_count > 0:
        data_types.append("embedded raster images (files + zip)")
    elif img_count == 0:
        data_types.append("embedded images (none)")

    summary_lines = [
        "--- Extraction summary (Unstructured + full text) ---",
        f"Source PDF: {pdf_path.name}",
        f"Output folder: {out_root}",
        f"partition_pdf strategy: {strategy}",
        f"Elements parsed: {total_elements} (JSON stores up to UNSTRUCTURED_JSON_MAX_ELEMENTS)",
        f"Max page (metadata): {max_page or 'n/a'}",
        f"PDF pages (fitz/pdfplumber): {num_pages}",
        f"Execution time: {mins} min {secs:.2f} sec (total {elapsed:.3f} s)",
        f"Data types: {', '.join(data_types)}",
        f"Combined: {extracted_txt.name}",
        f"Body only: document_text.txt",
        f"Structured: {elements_json.name}",
        img_note,
        "",
        "hi_res is slow and may download models on first run. Use UNSTRUCTURED_STRATEGY=fast for lighter runs.",
    ]

    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote text: {extracted_txt}")
    print(f"Wrote summary: {summary_txt}")
    print(f"Wrote elements: {elements_json}")
    if img_count > 0:
        print(f"Images: {images_dir} and {images_zip}")
    elif img_count == -1:
        print(img_note)


if __name__ == "__main__":
    main()
