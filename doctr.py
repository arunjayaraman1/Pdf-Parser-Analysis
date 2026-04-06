from __future__ import annotations

import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

# Local file name ``doctr.py`` can shadow the ``doctr`` package.
THIS_DIR = str(Path(__file__).resolve().parent)
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)

try:
    from doctr.io import DocumentFile  # type: ignore  # noqa: E402
    from doctr.models import ocr_predictor  # type: ignore  # noqa: E402
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "python-doctr is not installed. Install with: python -m pip install python-doctr[torch]"
    ) from exc


def _format_duration_sec(total_sec: float) -> tuple[int, float]:
    mins = int(total_sec // 60)
    secs = total_sec - 60 * mins
    return mins, secs


def _render_dpi() -> int:
    raw = os.environ.get("DOCTR_RENDER_DPI", "200")
    try:
        d = int(raw)
        return max(72, min(d, 400))
    except ValueError:
        return 200


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


def _render_pdf_pages_to_png(pdf_path: Path, ocr_pages_dir: Path, dpi: int) -> int:
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


def _page_texts_from_export(exp: dict) -> list[str]:
    """One string per page from DocTR export JSON."""
    out: list[str] = []
    for page in exp.get("pages", []):
        text_chunks: list[str] = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [w.get("value", "") for w in line.get("words", [])]
                line_s = " ".join(w for w in words if w)
                if line_s:
                    text_chunks.append(line_s)
        out.append("\n".join(text_chunks).strip())
    return out


def _build_predictor():
    """Optional env: DOCTR_DET_ARCH, DOCTR_RECO_ARCH (defaults: pretrained bundle)."""
    det = os.environ.get("DOCTR_DET_ARCH")
    reco = os.environ.get("DOCTR_RECO_ARCH")
    if det and reco:
        return ocr_predictor(det_arch=det, reco_arch=reco, pretrained=True)
    return ocr_predictor(pretrained=True)


def main() -> None:
    pdf_path = Path("Holiday 2026.pdf")
    if not pdf_path.exists():
        matches = sorted(Path(".").glob("Meta-Harness*.pdf"))
        if not matches:
            raise FileNotFoundError("Could not find target PDF in the current directory.")
        pdf_path = matches[0]

    out_root = pdf_path.parent / f"{pdf_path.stem}_extracted_doctr"
    out_root.mkdir(parents=True, exist_ok=True)
    extracted_txt = out_root / "extracted.txt"
    summary_txt = out_root / "summary.txt"
    export_json = out_root / "ocr_export.json"
    images_dir = out_root / "images"
    images_zip = out_root / "images.zip"
    ocr_pages_dir = out_root / "ocr_pages"

    dpi = _render_dpi()
    t0 = time.perf_counter()

    try:
        import fitz  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyMuPDF (fitz) is required to render PDF pages. "
            "Install with: python -m pip install PyMuPDF"
        ) from exc

    num_pages = _render_pdf_pages_to_png(pdf_path, ocr_pages_dir, dpi=dpi)

    img_paths = [str(ocr_pages_dir / f"page-{i + 1}.png") for i in range(num_pages)]
    doc_tensor = DocumentFile.from_images(img_paths)

    predictor = _build_predictor()
    parsed = predictor(doc_tensor)
    exp = parsed.export()

    page_texts = _page_texts_from_export(exp)
    text_blocks = [
        f"--- Page {i + 1} / {num_pages} ---\n{page_texts[i] if i < len(page_texts) else ''}"
        for i in range(num_pages)
    ]
    full_text = "\n\n".join(text_blocks)
    total_tables = 0

    elapsed = time.perf_counter() - t0
    mins, secs = _format_duration_sec(elapsed)

    extracted_txt.write_text(full_text, encoding="utf-8")
    try:
        export_json.write_text(
            json.dumps(exp, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception:
        export_json.write_text("{}", encoding="utf-8")

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
        data_types.append("OCR plain text (DocTR export, per page)")
    data_types.append("structured OCR JSON: ocr_export.json")
    data_types.append("tables: not as grid (OCR lines/words; use pdfplumber for tables)")
    data_types.append(f"rendered page PNGs: {ocr_pages_dir.name}/ (DOCTR_RENDER_DPI={dpi})")
    if img_count > 0:
        data_types.append("embedded raster images (files + zip)")
    elif img_count == 0:
        data_types.append("embedded images (none)")

    summary_lines = [
        "--- Extraction summary (DocTR + PyMuPDF render) ---",
        f"Source PDF: {pdf_path.name}",
        f"Output folder: {out_root}",
        f"Pages OCR'd: {num_pages}",
        f"Render DPI: {dpi} (set DOCTR_RENDER_DPI, default 200)",
        f"Execution time: {mins} min {secs:.2f} sec (total {elapsed:.3f} s)",
        f"Data types: {', '.join(data_types)}",
        f"Text length: {len(full_text)} characters, ~{len(full_text.split())} words",
        f"Main text file: {extracted_txt.name}",
        f"Full DocTR export: {export_json.name}",
        f"Tables: {total_tables} total (OCR does not produce table grids)",
        f"OCR page images: {ocr_pages_dir.name}/",
        img_note,
        "",
        "Note: first DocTR run may download weights (slow). Optional: DOCTR_DET_ARCH / DOCTR_RECO_ARCH.",
    ]

    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote text: {extracted_txt}")
    print(f"Wrote summary: {summary_txt}")
    print(f"Wrote export: {export_json}")
    print(f"OCR page PNGs: {ocr_pages_dir}")
    if img_count > 0:
        print(f"Images: {images_dir} and {images_zip}")
    elif img_count == -1:
        print(img_note)


if __name__ == "__main__":
    main()
