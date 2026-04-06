from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

# Local file ``layoutparser.py`` shadows the ``layoutparser`` package.
THIS_DIR = str(Path(__file__).resolve().parent)
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)

try:
    import layoutparser as lp  # type: ignore  # noqa: E402
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "layoutparser is not installed. Install with: python -m pip install layoutparser"
    ) from exc


def _format_duration_sec(total_sec: float) -> tuple[int, float]:
    mins = int(total_sec // 60)
    secs = total_sec - 60 * mins
    return mins, secs


def _render_dpi() -> int:
    raw = os.environ.get("LAYOUTPARSER_RENDER_DPI", "150")
    try:
        d = int(raw)
        return max(72, min(d, 300))
    except ValueError:
        return 150


# LayoutParser’s built-in lp:// PubLayNet URLs point at Dropbox; several configs are gone (HTML cached as YAML).
# Official mirror on Hugging Face (same files as the model zoo catalog intended).
_HF_PUBLAYNET_FASTER_R50_CONFIG = (
    "https://huggingface.co/layoutparser/detectron2/resolve/main/"
    "PubLayNet/faster_rcnn_R_50_FPN_3x/config.yml"
)
_HF_PUBLAYNET_FASTER_R50_WEIGHTS = (
    "https://huggingface.co/layoutparser/detectron2/resolve/main/"
    "PubLayNet/faster_rcnn_R_50_FPN_3x/model_final.pth"
)


def _normalize_url_base(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/")


def _resolve_layout_model_paths() -> tuple[str, str | None, str]:
    """
    Returns (config_path, model_path_or_none, label_for_json).

    - Default: Hugging Face PubLayNet faster_rcnn_R_50_FPN_3x (config + weights).
    - LAYOUTPARSER_MODEL=lp://... : legacy single-URI mode (may hit broken Dropbox links).
    - LAYOUTPARSER_MODEL=https://... : needs LAYOUTPARSER_MODEL_WEIGHTS unless it is the default HF config URL.
    """
    raw = os.environ.get("LAYOUTPARSER_MODEL")
    w_env = os.environ.get("LAYOUTPARSER_MODEL_WEIGHTS")
    if not raw:
        return (
            _HF_PUBLAYNET_FASTER_R50_CONFIG,
            _HF_PUBLAYNET_FASTER_R50_WEIGHTS,
            "PubLayNet/faster_rcnn_R_50_FPN_3x (Hugging Face: layoutparser/detectron2)",
        )
    if raw.startswith("lp://"):
        return raw, None, raw
    if raw.startswith(("http://", "https://")):
        if w_env:
            return raw, w_env, f"{raw} | weights: {w_env}"
        if _normalize_url_base(raw) == _normalize_url_base(_HF_PUBLAYNET_FASTER_R50_CONFIG):
            return raw, _HF_PUBLAYNET_FASTER_R50_WEIGHTS, raw
        raise ValueError(
            "LAYOUTPARSER_MODEL is an HTTP(S) URL but LAYOUTPARSER_MODEL_WEIGHTS is not set. "
            "Set LAYOUTPARSER_MODEL_WEIGHTS to the matching model_final.pth, or unset "
            "LAYOUTPARSER_MODEL to use the default Hugging Face PubLayNet model."
        )
    # Local filesystem path or other scheme — LayoutParser may accept it with explicit weights
    if w_env:
        return raw, w_env, f"{raw} | weights: {w_env}"
    return raw, None, raw


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


def _run_layout_detection(
    pdf_path: Path, layout_pages_dir: Path, dpi: int
) -> tuple[list[dict[str, object]], str, str]:
    """
    PubLayNet Detectron2 layout on each rendered page.
    Returns (regions, human-readable section, model label). Empty regions if detectron2 missing.
    """
    if importlib.util.find_spec("detectron2") is None:
        return [], (
            "Layout detection skipped: detectron2 is not installed.\n\n"
            "Install PyTorch in this venv first, then Detectron2. Pip’s isolated build often "
            "cannot see torch (ModuleNotFoundError: torch) unless you disable build isolation:\n"
            "  python -m pip install torch\n"
            "  python -m pip install 'git+https://github.com/facebookresearch/detectron2.git' "
            "--no-build-isolation\n\n"
            "Python 3.13 may still fail (no official wheels); prefer a 3.11 or 3.12 venv:\n"
            "  https://github.com/facebookresearch/detectron2/blob/main/INSTALL.md\n\n"
            "PART 1 (full text above) still works without detectron2."
        ), "none"

    import cv2  # type: ignore
    import fitz  # PyMuPDF

    try:
        config_path, weights_path, model_label = _resolve_layout_model_paths()
    except ValueError as exc:
        return [], _layout_failure_message(exc, "(invalid LAYOUTPARSER_MODEL)"), "(error)"

    try:
        extra = ["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5]
        if weights_path is None:
            model = lp.models.Detectron2LayoutModel(config_path, extra_config=extra)
        else:
            model = lp.models.Detectron2LayoutModel(
                config_path, weights_path, extra_config=extra
            )
    except Exception as exc:
        return [], _layout_failure_message(exc, model_label), model_label

    layout_pages_dir.mkdir(parents=True, exist_ok=True)
    regions: list[dict[str, object]] = []
    page_blocks: list[str] = []

    try:
        doc = fitz.open(pdf_path)
        try:
            num_pages = len(doc)
            for i in range(num_pages):
                page = doc[i]
                pix = page.get_pixmap(dpi=dpi)
                img_path = layout_pages_dir / f"page-{i + 1}.png"
                pix.save(str(img_path))
                image = cv2.imread(str(img_path))
                if image is None:
                    page_blocks.append(
                        f"--- Page {i + 1} / {num_pages} ---\n(could not load rendered image)"
                    )
                    continue
                layout = model.detect(image)
                lines = [f"--- Page {i + 1} / {num_pages} (layout regions) ---"]
                for j, block in enumerate(layout):
                    coords = list(block.coordinates)
                    lines.append(
                        f"  Region {j + 1}: type={block.type} score={float(block.score):.4f} coords={coords}"
                    )
                    regions.append(
                        {
                            "page": i + 1,
                            "type": str(block.type),
                            "score": float(block.score),
                            "coords": coords,
                        }
                    )
                page_blocks.append("\n".join(lines))
        finally:
            doc.close()
    except Exception as exc:
        return [], _layout_failure_message(exc, model_label), model_label

    return regions, "\n\n".join(page_blocks), model_label


def _layout_failure_message(exc: Exception, model_name: str) -> str:
    """User-facing hint when model load or inference fails."""
    name = type(exc).__name__
    msg = str(exc)
    lines = [
        f"Layout detection failed: {name}: {msg}",
        "",
        f"Model: {model_name}",
    ]
    if "ScannerError" in name or "yaml" in msg.lower() or "mapping values" in msg.lower():
        lines.extend(
            [
                "",
                "YAML load error on the layout config usually means the downloaded file is not YAML "
                "(often Dropbox returned an HTML “file deleted” page; LayoutParser’s lp:// PubLayNet "
                "URLs still point at Dropbox).",
                "This script defaults to the Hugging Face mirror (layoutparser/detectron2) when "
                "LAYOUTPARSER_MODEL is unset.",
                "If you use lp://..., clear bad cache and retry, e.g.:",
                "  rm -rf ~/.torch/iopath_cache/s/f3b12qc4hc0yh4m",
                "Or set LAYOUTPARSER_MODEL / LAYOUTPARSER_MODEL_WEIGHTS to local or HTTPS paths.",
            ]
        )
    lines.append("")
    lines.append("PART 1 (full text above) is unchanged.")
    return "\n".join(lines)


def main() -> None:
    pdf_path = Path("Holiday 2026.pdf")
    if not pdf_path.exists():
        matches = sorted(Path(".").glob("Meta-Harness*.pdf"))
        if not matches:
            raise FileNotFoundError("Could not find target PDF in the current directory.")
        pdf_path = matches[0]

    out_root = pdf_path.parent / f"{pdf_path.stem}_extracted_layoutparser"
    out_root.mkdir(parents=True, exist_ok=True)
    extracted_txt = out_root / "extracted.txt"
    summary_txt = out_root / "summary.txt"
    regions_json = out_root / "layout_regions.json"
    layout_pages_dir = out_root / "layout_pages"
    images_dir = out_root / "images"
    images_zip = out_root / "images.zip"

    dpi = _render_dpi()
    t0 = time.perf_counter()

    body_text, num_pages, text_source = _extract_body_text_per_page(pdf_path)
    if num_pages == 0:
        import fitz  # PyMuPDF

        _doc = fitz.open(pdf_path)
        num_pages = len(_doc)
        _doc.close()

    regions, layout_section, model_label = _run_layout_detection(pdf_path, layout_pages_dir, dpi)

    rj: dict = {"regions": regions, "model": model_label}
    if layout_section.strip().startswith("Layout detection failed"):
        rj["layout_error"] = layout_section[:4000]
    regions_json.write_text(json.dumps(rj, indent=2, ensure_ascii=False), encoding="utf-8")

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
            "PART 2 — Layout detection (LayoutParser + Detectron2 / PubLayNet)",
            f"Render DPI: {dpi} (LAYOUTPARSER_RENDER_DPI)",
            "=" * 80,
            "",
            layout_section,
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

    det_ok = importlib.util.find_spec("detectron2") is not None
    if not det_ok:
        layout_note = "layout (skipped — no detectron2)"
    elif layout_section.strip().startswith("Layout detection failed"):
        layout_note = "layout (error — see PART 2; often bad YAML cache under ~/.torch/iopath_cache)"
    else:
        layout_note = f"layout regions ({len(regions)} detected)"

    data_types = [
        f"full text layer ({text_source})",
        layout_note,
        f"page renders: {layout_pages_dir.name}/",
        f"structured JSON: {regions_json.name}",
        f"PDF pages: {num_pages}",
        "document_text.txt = part 1 only",
    ]
    if img_count > 0:
        data_types.append("embedded raster images (files + zip)")
    elif img_count == 0:
        data_types.append("embedded images (none)")

    summary_lines = [
        "--- Extraction summary (LayoutParser + full text) ---",
        f"Source PDF: {pdf_path.name}",
        f"Output folder: {out_root}",
        f"Layout render DPI: {dpi}",
        f"detectron2 available: {det_ok}",
        f"Regions detected: {len(regions)}",
        f"PDF pages: {num_pages}",
        f"Execution time: {mins} min {secs:.2f} sec (total {elapsed:.3f} s)",
        f"Data types: {', '.join(data_types)}",
        f"Combined: {extracted_txt.name}",
        f"Body only: document_text.txt",
        f"Layout JSON: {regions_json.name}",
        img_note,
        "",
        "Heavy models download on first run. Optional: LAYOUTPARSER_MODEL / LAYOUTPARSER_MODEL_WEIGHTS "
        "(default: Hugging Face PubLayNet mirror).",
    ]

    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote text: {extracted_txt}")
    print(f"Wrote summary: {summary_txt}")
    print(f"Wrote regions: {regions_json}")
    print(f"Layout page PNGs: {layout_pages_dir}")
    if img_count > 0:
        print(f"Images: {images_dir} and {images_zip}")
    elif img_count == -1:
        print(img_note)
    if not det_ok:
        print(
            "Note: PART 2 needs torch + detectron2. After: pip install torch, use "
            "pip install 'git+https://github.com/facebookresearch/detectron2.git' "
            "--no-build-isolation (pip’s isolated build hides torch). 3.13 may need 3.11/3.12 venv."
        )
    elif layout_section.strip().startswith("Layout detection failed"):
        print(
            "Note: PART 2 layout failed (see extracted.txt PART 2). "
            "If YAML/ScannerError on lp:// models: Dropbox may have deleted the file — "
            "unset LAYOUTPARSER_MODEL to use the Hugging Face default, or clear "
            "~/.torch/iopath_cache for that URL."
        )


if __name__ == "__main__":
    main()
