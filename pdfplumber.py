from __future__ import annotations

import shutil
import sys
import time
import zipfile
from pathlib import Path

# Avoid importing this local file as the third-party package.
THIS_DIR = str(Path(__file__).resolve().parent)
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)

try:
    import pdfplumber  # type: ignore  # noqa: E402
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "pdfplumber is not installed in the current environment. "
        "Install it with: python -m pip install pdfplumber"
    ) from exc


def _format_duration_sec(total_sec: float) -> tuple[int, float]:
    """Whole minutes and remaining seconds."""
    mins = int(total_sec // 60)
    secs = total_sec - 60 * mins
    return mins, secs


def _extract_embedded_images(pdf_path: Path, images_dir: Path) -> int:
    """
    Save embedded PDF images to ``images_dir``. Uses PyMuPDF if available.
    Returns number of image files written.
    """
    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError:
        return -1  # signal: dependency missing

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


def main() -> None:
    pdf_path = Path("Holiday 2026.pdf")
    if not pdf_path.exists():
        matches = sorted(Path(".").glob("Meta-Harness*.pdf"))
        if not matches:
            raise FileNotFoundError("Could not find target PDF in the current directory.")
        pdf_path = matches[0]

    out_root = pdf_path.parent / f"{pdf_path.stem}_extracted"
    out_root.mkdir(parents=True, exist_ok=True)
    extracted_txt = out_root / "extracted.txt"
    summary_txt = out_root / "summary.txt"
    images_dir = out_root / "images"
    images_zip = out_root / "images.zip"

    t0 = time.perf_counter()

    text_blocks: list[str] = []
    table_dims: list[tuple[int, int, int, int]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        num_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            page_no = i + 1
            ptext = page.extract_text() or ""
            text_blocks.append(f"--- Page {page_no} / {num_pages} ---\n{ptext}")
            for j, tbl in enumerate(page.extract_tables() or []):
                rows = len(tbl) if tbl else 0
                cols = len(tbl[0]) if tbl and tbl[0] else 0
                table_dims.append((page_no, j + 1, rows, cols))

    full_text = "\n\n".join(text_blocks)
    total_tables = len(table_dims)

    elapsed = time.perf_counter() - t0
    mins, secs = _format_duration_sec(elapsed)

    extracted_txt.write_text(full_text, encoding="utf-8")

    # Embedded images: folder + zip (if any)
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

    data_types: list[str] = []
    if full_text.strip():
        data_types.append("plain text (per page, characters / words)")
    if total_tables:
        data_types.append(f"tables ({total_tables} across all pages)")
    else:
        data_types.append("tables (none detected)")
    if img_count > 0:
        data_types.append("embedded raster images (files + zip)")
    elif img_count == 0:
        data_types.append("embedded images (none)")

    summary_lines = [
        "--- Extraction summary ---",
        f"Source PDF: {pdf_path.name}",
        f"Output folder: {out_root}",
        f"Pages extracted: {num_pages}",
        f"Execution time: {mins} min {secs:.2f} sec (total {elapsed:.3f} s)",
        f"Data types: {', '.join(data_types)}",
        f"Text length: {len(full_text)} characters, ~{len(full_text.split())} words",
        f"Main text file: {extracted_txt.name}",
        f"Tables: {total_tables} total",
        img_note,
        "",
        "Per-table dimensions (rows × columns):",
    ]
    for page_no, tidx, rows, cols in table_dims:
        summary_lines.append(f"  Page {page_no}, table {tidx}: ~{rows} rows × {cols} columns")
    if not table_dims:
        summary_lines.append("  (none)")

    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote text: {extracted_txt}")
    print(f"Wrote summary: {summary_txt}")
    if img_count > 0:
        print(f"Images: {images_dir} and {images_zip}")
    elif img_count == -1:
        print(img_note)


if __name__ == "__main__":
    main()
