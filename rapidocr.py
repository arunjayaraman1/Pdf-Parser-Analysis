"""
Extract text from a PDF with RapidOCR (rapidocr_pdf + rapidocr).

Local file ``rapidocr.py`` shadows the installed ``rapidocr`` package — this directory is
removed from ``sys.path`` before importing (``rapidocr_pdf`` does ``from rapidocr import RapidOCR``).

Uses ``RapidOCRPDF`` (``dpi``, ``ocr_params``) and writes under ``{stem}_extracted_rapidocr/``.

Environment:
  RAPIDOCR_SOURCE         — path to PDF (default: Holiday 2026.pdf or first *.pdf in cwd)
  RAPIDOCR_DPI            — render DPI for OCR pages (default: 200)
  RAPIDOCR_PAGE_RANGE     — optional, e.g. 0,1-2 (0-based page indices, same as CLI --page_num_list)
  RAPIDOCR_FORCE_OCR      — set to 1 to OCR every page (ignore embedded text)
  RAPIDOCR_MODEL_TYPE     — mobile | server — maps to Det/Cls/Rec ``model_type`` (default: mobile)
  RAPIDOCR_OCR_PARAMS_JSON — optional JSON object merged into RapidOCR ``params`` (advanced)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Local file ``rapidocr.py`` shadows the ``rapidocr`` package.
_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR in sys.path:
    sys.path.remove(_THIS_DIR)

from rapidocr.utils.typings import ModelType  # noqa: E402
from rapidocr_pdf import RapidOCRPDF  # noqa: E402
from rapidocr_pdf.main import RapidOCRPDFError  # noqa: E402


def _pick_pdf(cwd: Path) -> Path:
    pdf = cwd / "Holiday 2026.pdf"
    if pdf.exists():
        return pdf
    matches = sorted(cwd.glob("*.pdf"))
    if not matches:
        raise FileNotFoundError(
            "No PDF found. Set RAPIDOCR_SOURCE or add a .pdf in the project directory."
        )
    return matches[0]


def _resolve_source(cwd: Path) -> Path:
    raw = os.environ.get("RAPIDOCR_SOURCE", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"RAPIDOCR_SOURCE not found: {p}")
        return p
    return _pick_pdf(cwd)


def _parse_page_range() -> list[int] | None:
    raw = os.environ.get("RAPIDOCR_PAGE_RANGE", "").strip()
    if not raw:
        return None
    page_lst: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            page_lst.extend(range(int(start_s), int(end_s) + 1))
        else:
            page_lst.append(int(part))
    return sorted(set(page_lst))


def _dpi() -> int:
    raw = os.environ.get("RAPIDOCR_DPI", "").strip()
    if not raw:
        return 200
    try:
        return max(72, min(int(raw), 600))
    except ValueError:
        return 200


def _force_ocr() -> bool:
    return os.environ.get("RAPIDOCR_FORCE_OCR", "").lower() in ("1", "true", "yes")


def _model_type_enum() -> ModelType:
    raw = os.environ.get("RAPIDOCR_MODEL_TYPE", "mobile").strip().lower()
    if raw == "server":
        return ModelType.SERVER
    return ModelType.MOBILE


def _ocr_params() -> dict:
    mt = _model_type_enum()
    params: dict = {
        "Det.model_type": mt,
        "Cls.model_type": mt,
        "Rec.model_type": mt,
    }
    extra = os.environ.get("RAPIDOCR_OCR_PARAMS_JSON", "").strip()
    if extra:
        loaded = json.loads(extra)
        if not isinstance(loaded, dict):
            raise ValueError("RAPIDOCR_OCR_PARAMS_JSON must be a JSON object")
        params.update(loaded)
    return params


def main() -> None:
    cwd = Path(__file__).resolve().parent
    source = _resolve_source(cwd)
    stem = source.stem
    out_root = cwd / f"{stem}_extracted_rapidocr"
    out_root.mkdir(parents=True, exist_ok=True)

    dpi = _dpi()
    page_num_list = _parse_page_range()
    force = _force_ocr()

    try:
        ocr_params = _ocr_params()
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"RapidOCR: invalid RAPIDOCR_OCR_PARAMS_JSON: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    extractor = RapidOCRPDF(dpi=dpi, ocr_params=ocr_params)

    print(
        f"RapidOCR: {source.name} → {out_root.name}/ "
        f"(dpi={dpi}, force_ocr={force}, pages={page_num_list or 'all'}) …",
        file=sys.stderr,
    )
    t0 = time.perf_counter()
    try:
        rows = extractor(str(source), force_ocr=force, page_num_list=page_num_list)
    except RapidOCRPDFError as exc:
        print(f"RapidOCR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    elapsed = time.perf_counter() - t0

    pages_json: list[dict] = []
    blocks: list[str] = []
    plain_chunks: list[str] = []

    for page_idx, text, conf in rows:
        c = conf
        if isinstance(conf, (int, float)):
            c = float(conf)
        elif conf == "N/A":
            c = None
        pages_json.append({"page_index": int(page_idx), "text": text, "avg_confidence": c})
        blocks.append(f"--- Page {int(page_idx) + 1} (index {page_idx}, score: {conf}) ---")
        blocks.append(text)
        blocks.append("")
        plain_chunks.append(text)

    extracted = out_root / "extracted.txt"
    extracted.write_text(
        "\n".join(
            [
                "=" * 72,
                "RapidOCR PDF — per-page text (embedded text or OCR)",
                f"Source: {source}",
                f"DPI: {dpi} (RAPIDOCR_DPI)",
                "=" * 72,
                "",
                "\n".join(blocks).rstrip(),
                "",
            ]
        ),
        encoding="utf-8",
    )

    doc_text = out_root / "document_text.txt"
    doc_text.write_text("\n\n".join(plain_chunks), encoding="utf-8")

    results_path = out_root / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "source": str(source),
                "dpi": dpi,
                "force_ocr": force,
                "page_num_list": page_num_list,
                "model_type": _model_type_enum().value,
                "pages": pages_json,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    summary = out_root / "summary.txt"
    summary.write_text(
        "\n".join(
            [
                "--- RapidOCR PDF summary ---",
                f"Source: {source}",
                f"Output: {out_root}",
                f"Pages in output: {len(rows)}",
                f"DPI: {dpi} (RAPIDOCR_DPI)",
                f"force_ocr: {force} (RAPIDOCR_FORCE_OCR)",
                f"page_num_list: {page_num_list}",
                f"model_type: {_model_type_enum().value} (RAPIDOCR_MODEL_TYPE)",
                f"Time: {elapsed:.2f} s",
                f"Per-page dump: {extracted.name}",
                f"Plain text: {doc_text.name}",
                f"JSON: {results_path.name}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Wrote: {extracted}")
    print(f"Wrote: {doc_text}")
    print(f"Wrote: {results_path}")
    print(f"Wrote: {summary}")


if __name__ == "__main__":
    main()
