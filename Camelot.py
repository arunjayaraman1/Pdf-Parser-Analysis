from __future__ import annotations

import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

# Avoid shadowing the ``camelot`` package on case-insensitive filesystems.
THIS_DIR = str(Path(__file__).resolve().parent)
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)

try:
    import camelot  # type: ignore  # noqa: E402
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "camelot-py is not installed. Install with: python -m pip install camelot-py[cv]"
    ) from exc


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


def _camelot_flavor() -> str:
    f = os.environ.get("CAMELOT_FLAVOR", "lattice").strip().lower()
    return f if f in ("lattice", "stream") else "lattice"


def _extract_body_text_per_page(pdf_path: Path) -> tuple[str, int, str]:
    """
    Full PDF text layer (non-Camelot). Returns (text, num_pages, source_label).
    Tries pdfplumber first, then pdfminer.six.
    """
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


def main() -> None:
    pdf_path = Path("Holiday 2026.pdf")
    if not pdf_path.exists():
        matches = sorted(Path(".").glob("Meta-Harness*.pdf"))
        if not matches:
            raise FileNotFoundError("Could not find target PDF in the current directory.")
        pdf_path = matches[0]

    out_root = pdf_path.parent / f"{pdf_path.stem}_extracted_camelot"
    out_root.mkdir(parents=True, exist_ok=True)
    extracted_txt = out_root / "extracted.txt"
    summary_txt = out_root / "summary.txt"
    tables_dir = out_root / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_root / "images"
    images_zip = out_root / "images.zip"

    flavor = _camelot_flavor()
    t0 = time.perf_counter()

    body_text, num_pages, text_source = _extract_body_text_per_page(pdf_path)
    if num_pages == 0:
        import fitz  # PyMuPDF

        _doc = fitz.open(pdf_path)
        num_pages = len(_doc)
        _doc.close()

    tables = camelot.read_pdf(
        str(pdf_path),
        pages="all",
        flavor=flavor,
    )

    text_parts: list[str] = []
    table_meta: list[tuple[int, int, int, int]] = []

    for i in range(tables.n):
        t = tables[i]
        df = t.df
        rows, cols = df.shape
        page_raw = getattr(t, "page", None)
        page_label = str(page_raw) if page_raw is not None else str(i + 1)
        try:
            page_int = int(page_raw)
        except (TypeError, ValueError):
            page_int = i + 1
        table_meta.append((i + 1, page_int, rows, cols))
        csv_path = tables_dir / f"table-{i + 1}.csv"
        t.to_csv(str(csv_path))
        text_parts.append(
            f"--- Table {i + 1} / {tables.n} (page {page_label}, {rows}×{cols}) ---\n"
            + df.to_string(index=False, header=True)
        )

    table_section = (
        "\n\n".join(text_parts)
        if text_parts
        else "No tables detected by Camelot for this PDF (try CAMELOT_FLAVOR=stream or check Ghostscript)."
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
            "PART 2 — Tables (Camelot)",
            f"Flavor: {flavor}",
            "=" * 80,
            "",
            table_section,
        ]
    )

    (out_root / "document_text.txt").write_text(
        body_text if text_source != "none" else "",
        encoding="utf-8",
    )

    if tables.n > 0:
        try:
            tables.export(str(out_root / "camelot_export.csv"), f="csv")
        except Exception:
            pass

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
        f"tables (Camelot {flavor}, pages=all)",
        "per-table CSV under tables/",
        "optional camelot_export*.csv via tables.export",
        f"PDF pages: {num_pages}",
        "document_text.txt = part 1 only",
    ]
    if img_count > 0:
        data_types.append("embedded raster images (files + zip)")
    elif img_count == 0:
        data_types.append("embedded images (none)")

    summary_lines = [
        "--- Extraction summary (Camelot + full text) ---",
        f"Source PDF: {pdf_path.name}",
        f"Output folder: {out_root}",
        f"Flavor: {flavor} (set CAMELOT_FLAVOR=lattice or stream)",
        f"PDF pages: {num_pages}",
        f"Tables detected: {tables.n}",
        f"Execution time: {mins} min {secs:.2f} sec (total {elapsed:.3f} s)",
        f"Data types: {', '.join(data_types)}",
        f"Combined dump: {extracted_txt.name} (part 1 = body, part 2 = tables)",
        f"Body text only: document_text.txt (source: {text_source})",
        f"Per-table CSV: {tables_dir.name}/table-*.csv",
        f"Bulk export (if supported): {out_root.name}/camelot_export*.csv",
        img_note,
        "",
        "Requires Ghostscript for many PDFs: https://camelot-py.readthedocs.io/",
    ]
    for idx, pg, r, c in table_meta:
        summary_lines.append(f"  Table {idx}: page {pg}, ~{r} rows × {c} cols")

    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote text: {extracted_txt}")
    print(f"Wrote summary: {summary_txt}")
    print(f"Tables CSV dir: {tables_dir}")
    if img_count > 0:
        print(f"Images: {images_dir} and {images_zip}")
    elif img_count == -1:
        print(img_note)


if __name__ == "__main__":
    main()
