from __future__ import annotations

import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

# Avoid shadowing site-packages if this script name collides with imports.
THIS_DIR = str(Path(__file__).resolve().parent)
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)

try:
    import pytesseract  # type: ignore  # noqa: E402
    from PIL import Image  # type: ignore  # noqa: E402
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "pytesseract and Pillow are required. "
        "Install with: python -m pip install pytesseract Pillow"
    ) from exc

# Optional: set Tesseract binary (Windows: uncomment and set path, or set TESSERACT_CMD).
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_tess = os.environ.get("TESSERACT_CMD")
if _tess:
    pytesseract.pytesseract.tesseract_cmd = _tess


def _format_duration_sec(total_sec: float) -> tuple[int, float]:
    """Whole minutes and remaining seconds."""
    mins = int(total_sec // 60)
    secs = total_sec - 60 * mins
    return mins, secs


def _extract_embedded_images(pdf_path: Path, images_dir: Path) -> int:
    """
    Save embedded PDF images to ``images_dir``. Uses PyMuPDF if available.
    Returns number of image files written, or -1 if PyMuPDF is missing.
    """
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


def _render_pdf_pages_to_png(pdf_path: Path, ocr_pages_dir: Path, dpi: int = 200) -> int:
    """Rasterize each PDF page to PNG for OCR. Returns page count. Requires PyMuPDF."""
    import fitz  # PyMuPDF

    ocr_pages_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    try:
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi)
            pix.save(ocr_pages_dir / f"page-{i + 1}.png")
        return len(doc)
    finally:
        doc.close()


def main() -> None:
    pdf_path = Path("Holiday 2026.pdf")
    if not pdf_path.exists():
        matches = sorted(Path(".").glob("Meta-Harness*.pdf"))
        if not matches:
            raise FileNotFoundError("Could not find target PDF in the current directory.")
        pdf_path = matches[0]

    out_root = pdf_path.parent / f"{pdf_path.stem}_extracted_tesseract"
    out_root.mkdir(parents=True, exist_ok=True)
    extracted_txt = out_root / "extracted.txt"
    summary_txt = out_root / "summary.txt"
    images_dir = out_root / "images"
    images_zip = out_root / "images.zip"
    ocr_pages_dir = out_root / "ocr_pages"

    t0 = time.perf_counter()

    try:
        import fitz  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyMuPDF (fitz) is required to render PDF pages for OCR. "
            "Install with: python -m pip install PyMuPDF"
        ) from exc

    num_pages = _render_pdf_pages_to_png(pdf_path, ocr_pages_dir, dpi=200)

    text_blocks: list[str] = []

    for i in range(num_pages):
        page_no = i + 1
        img_path = ocr_pages_dir / f"page-{page_no}.png"
        img = Image.open(img_path)
        ptext = pytesseract.image_to_string(img) or ""
        text_blocks.append(f"--- Page {page_no} / {num_pages} ---\n{ptext.strip()}")

    full_text = "\n\n".join(text_blocks)
    total_tables = 0

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

    data_types: list[str] = []
    if full_text.strip():
        data_types.append("OCR plain text (per page from rendered page images)")
    data_types.append("tables: not extracted (OCR text only; use pdfplumber for table grids)")
    data_types.append(f"rendered page PNGs for OCR: {ocr_pages_dir.name}/")
    if img_count > 0:
        data_types.append("embedded raster images (files + zip)")
    elif img_count == 0:
        data_types.append("embedded images (none)")

    summary_lines = [
        "--- Extraction summary (Tesseract OCR + PyMuPDF render) ---",
        f"Source PDF: {pdf_path.name}",
        f"Output folder: {out_root}",
        f"Pages OCR'd: {num_pages}",
        f"Execution time: {mins} min {secs:.2f} sec (total {elapsed:.3f} s)",
        f"Data types: {', '.join(data_types)}",
        f"Text length: {len(full_text)} characters, ~{len(full_text.split())} words",
        f"Main text file: {extracted_txt.name}",
        f"Tables: {total_tables} total (OCR does not produce table grids)",
        f"OCR page images (input to Tesseract): {ocr_pages_dir.name}/",
        img_note,
        "",
        "Requires: Tesseract binary on PATH (or set TESSERACT_CMD / pytesseract.pytesseract.tesseract_cmd).",
    ]

    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote text: {extracted_txt}")
    print(f"Wrote summary: {summary_txt}")
    print(f"OCR page PNGs: {ocr_pages_dir}")
    if img_count > 0:
        print(f"Images: {images_dir} and {images_zip}")
    elif img_count == -1:
        print(img_note)


if __name__ == "__main__":
    main()
