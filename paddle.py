from __future__ import annotations

import os
import sys
import time
import json
import shutil
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Avoid local shadowing
THIS_DIR = str(Path(__file__).resolve().parent)
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)

try:
    from paddleocr import PaddleOCR
except ModuleNotFoundError:
    raise RuntimeError("Install paddleocr: pip install paddleocr paddlepaddle")

try:
    import fitz  # PyMuPDF
except ModuleNotFoundError:
    raise RuntimeError("Install PyMuPDF: pip install PyMuPDF")


# ---------------- CONFIG ----------------
PDF_PATH = Path("/Users/newpage/Documents/LLM-Parser/Meta-Harness_ End-to-End Optimization of Model Harnesses.pdf")
DPI = 150
MAX_WORKERS = 4
LANG = os.environ.get("PADDLEOCR_LANG", "en")
USE_GPU = os.environ.get("PADDLEOCR_USE_GPU", "0") == "1"


# ---------------- UTILS ----------------
def format_time(sec: float):
    m = int(sec // 60)
    s = sec - 60 * m
    return m, s


def build_ocr():
    return PaddleOCR(
        lang=LANG,
        use_gpu=USE_GPU,
        use_textline_orientation=True
    )


def extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()


def render_pages(pdf_path: Path, out_dir: Path, dpi=150):
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    for i in range(len(doc)):
        pix = doc[i].get_pixmap(dpi=dpi)
        pix.save(out_dir / f"page-{i+1}.png")
    doc.close()
    return len(list(out_dir.glob("*.png")))


def extract_images(pdf_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    count = 0

    for i, page in enumerate(doc):
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
                ext = base.get("ext", "png")
                img_bytes = base["image"]
                file_path = out_dir / f"page{i+1}_img{img_index+1}.{ext}"
                file_path.write_bytes(img_bytes)
                count += 1
            except:
                continue

    doc.close()
    return count


def ocr_page(ocr, img_path: Path, page_no: int):
    results = ocr.predict(str(img_path))
    lines = []

    for res in results:
        if isinstance(res, dict) and "rec_texts" in res:
            lines.extend(res["rec_texts"])
        elif isinstance(res, list):
            for item in res:
                if len(item) >= 2:
                    lines.append(item[1][0])

    text = "\n".join(lines).strip()
    return {
        "page": page_no,
        "text": text
    }


# ---------------- MAIN ----------------
def main():
    if not PDF_PATH.exists():
        raise FileNotFoundError("PDF not found")

    out_dir = PDF_PATH.parent / f"{PDF_PATH.stem}_output"
    ocr_img_dir = out_dir / "ocr_pages"
    img_dir = out_dir / "images"

    out_dir.mkdir(exist_ok=True)

    start = time.perf_counter()

    print("🔍 Checking if PDF has text layer...")
    text_layer = extract_pdf_text(PDF_PATH)

    # ---------- CASE 1: TEXT PDF ----------
    if text_layer:
        print("✅ Text-based PDF detected → skipping OCR")

        data = [{
            "page": i+1,
            "text": page.get_text()
        } for i, page in enumerate(fitz.open(PDF_PATH))]

    # ---------- CASE 2: SCANNED PDF ----------
    else:
        print("🧠 Scanned PDF → running OCR...")

        ocr = build_ocr()
        num_pages = render_pages(PDF_PATH, ocr_img_dir, DPI)

        def process(i):
            return ocr_page(ocr, ocr_img_dir / f"page-{i+1}.png", i+1)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            data = list(executor.map(process, range(num_pages)))

    # ---------- SAVE TEXT ----------
    full_text = "\n\n".join([d["text"] for d in data])

    (out_dir / "output.txt").write_text(full_text, encoding="utf-8")
    (out_dir / "output.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ---------- EXTRACT IMAGES ----------
    img_count = extract_images(PDF_PATH, img_dir)

    if img_count > 0:
        with zipfile.ZipFile(out_dir / "images.zip", "w") as z:
            for f in img_dir.iterdir():
                z.write(f, f.name)
    else:
        shutil.rmtree(img_dir, ignore_errors=True)

    # ---------- SUMMARY ----------
    elapsed = time.perf_counter() - start
    m, s = format_time(elapsed)

    summary = f"""
--- SUMMARY ---
PDF: {PDF_PATH.name}
Pages: {len(data)}
Mode: {"Text" if text_layer else "OCR"}
Language: {LANG}
GPU: {USE_GPU}
Time: {m} min {s:.2f} sec
Text length: {len(full_text)} chars
Images extracted: {img_count}
"""

    (out_dir / "summary.txt").write_text(summary)

    print(summary)
    print("✅ Done! Output folder:", out_dir)


if __name__ == "__main__":
    main()