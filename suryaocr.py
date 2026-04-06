"""
Run Surya OCR on a PDF or image and write text + JSON.

Documentation source: Context7 library ``/datalab-to/surya`` (Datalab Surya — OCR, detection,
layout). API pattern matches upstream: ``FoundationPredictor``, ``DetectionPredictor``,
``RecognitionPredictor([images], det_predictor=..., highres_images=..., math_mode=...)``, and
``load_from_file`` / ``load_pdf`` (see surya.input.load).

Environment:
  SURYA_SOURCE             — path to PDF or image (default: Holiday 2026.pdf or first *.pdf / image)
  SURYA_PAGE_RANGE         — optional, e.g. 0,1-2 (0-based page indices for PDFs)
  SURYA_MATH               — set to 0 to disable math recognition in OCR
  SURYA_WORDS              — set to 1 to include word-level results in JSON
  SURYA_DPI                — render DPI for detection/layout images (default: settings.IMAGE_DPI, often 96)
  SURYA_DPI_HIGHRES        — DPI for recognition crops (default: settings.IMAGE_DPI_HIGHRES, often 192)
  SURYA_DISABLE_TQDM       — set to 1 to disable progress bars
  SURYA_DROP_REPEATED      — set to 1 to pass drop_repeated_text=True to RecognitionPredictor
  SURYA_DET_BATCH          — optional int: detection_batch_size for RecognitionPredictor
  SURYA_REC_BATCH          — optional int: recognition_batch_size for RecognitionPredictor
  TORCH_DEVICE             — optional (Surya settings): e.g. cpu, cuda, mps

Requires ``transformers`` 4.x (e.g. ``>=4.56.1,<5``). Version 5.x breaks Surya’s Qwen2 rope
(``KeyError: 'default'`` in ``ROPE_INIT_FUNCTIONS``). If you still see
``SuryaDecoderConfig`` / ``pad_token_id`` errors, upgrade or pin ``transformers`` as above.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Honor device before Surya imports read settings (optional).
_raw_dev = os.environ.get("TORCH_DEVICE", "").strip()
if _raw_dev:
    os.environ["TORCH_DEVICE"] = _raw_dev

from surya.detection import DetectionPredictor
from surya.foundation import FoundationPredictor
from surya.input.load import load_from_file
from surya.recognition import RecognitionPredictor
from surya.settings import settings


def _dpi() -> int:
    raw = os.environ.get("SURYA_DPI", "").strip()
    if not raw:
        return int(settings.IMAGE_DPI)
    try:
        return max(72, min(int(raw), 600))
    except ValueError:
        return int(settings.IMAGE_DPI)


def _dpi_highres() -> int:
    raw = os.environ.get("SURYA_DPI_HIGHRES", "").strip()
    if not raw:
        return int(settings.IMAGE_DPI_HIGHRES)
    try:
        return max(72, min(int(raw), 600))
    except ValueError:
        return int(settings.IMAGE_DPI_HIGHRES)


def _pick_default_path(cwd: Path) -> Path:
    pdf = cwd / "Holiday 2026.pdf"
    if pdf.exists():
        return pdf
    for ext in ("*.pdf", "*.png", "*.jpg", "*.jpeg", "*.webp"):
        matches = sorted(cwd.glob(ext))
        if matches:
            return matches[0]
    raise FileNotFoundError(
        "No PDF or image found. Set SURYA_SOURCE or add a file in the project directory."
    )


def _resolve_source(cwd: Path) -> Path:
    raw = os.environ.get("SURYA_SOURCE", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"SURYA_SOURCE not found: {p}")
        return p
    return _pick_default_path(cwd)


def _parse_page_range() -> list[int] | None:
    raw = os.environ.get("SURYA_PAGE_RANGE", "").strip()
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


def _math_mode() -> bool:
    return os.environ.get("SURYA_MATH", "1").lower() not in ("0", "false", "no")


def _return_words() -> bool:
    return os.environ.get("SURYA_WORDS", "").lower() in ("1", "true", "yes")


def _drop_repeated() -> bool:
    return os.environ.get("SURYA_DROP_REPEATED", "").lower() in ("1", "true", "yes")


def _optional_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def _page_display_labels(source: Path, names: list[str], page_range: list[int] | None) -> list[str]:
    """load_pdf repeats the same basename for every page — make labels unique for output."""
    if source.suffix.lower() != ".pdf" or not names:
        return names
    base = names[0]
    if page_range is not None:
        return [f"{base}_page{p}" for p in page_range]
    return [f"{base}_page{i}" for i in range(len(names))]


def _configure_settings() -> None:
    if os.environ.get("SURYA_DISABLE_TQDM", "").lower() in ("1", "true", "yes"):
        settings.DISABLE_TQDM = True


def main() -> None:
    _configure_settings()
    cwd = Path(__file__).resolve().parent
    source = _resolve_source(cwd)
    stem = source.stem
    out_root = cwd / f"{stem}_extracted_surya"
    out_root.mkdir(parents=True, exist_ok=True)

    page_range = _parse_page_range()
    dpi = _dpi()
    dpi_hi = _dpi_highres()
    det_bs = _optional_int("SURYA_DET_BATCH")
    rec_bs = _optional_int("SURYA_REC_BATCH")

    try:
        images, names = load_from_file(str(source), page_range, dpi=dpi)
        highres_images, _ = load_from_file(str(source), page_range, dpi=dpi_hi)
    except AssertionError as exc:
        print(f"Surya: invalid page range or PDF error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Surya: failed to load file: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not images:
        print("Surya: no page images loaded (empty PDF?).", file=sys.stderr)
        raise SystemExit(1)

    labels = _page_display_labels(source, names, page_range)

    foundation = FoundationPredictor()
    det = DetectionPredictor()
    rec = RecognitionPredictor(foundation)

    print(
        f"Surya: {len(images)} page image(s) from {source.name} "
        f"(dpi={dpi}, highres_dpi={dpi_hi}) → {out_root.name}/ …",
        file=sys.stderr,
    )
    t0 = time.perf_counter()
    try:
        rec_kw: dict = {
            "det_predictor": det,
            "highres_images": highres_images,
            "math_mode": _math_mode(),
            "return_words": _return_words(),
            "sort_lines": True,
            "drop_repeated_text": _drop_repeated(),
        }
        if det_bs is not None:
            rec_kw["detection_batch_size"] = det_bs
        if rec_bs is not None:
            rec_kw["recognition_batch_size"] = rec_bs
        predictions = rec(images, **rec_kw)
    except Exception as exc:
        print(f"Surya: OCR failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    elapsed = time.perf_counter() - t0

    lines_out: list[str] = []
    plain_lines: list[str] = []
    json_pages: list[dict] = []
    for page_idx, (pred, label) in enumerate(zip(predictions, labels), start=1):
        lines_out.append(f"--- Page {page_idx} ({label}) ---")
        for line in pred.text_lines:
            plain_lines.append(line.text)
            poly = getattr(line, "bbox", None) or getattr(line, "polygon", None)
            conf = getattr(line, "confidence", None)
            extra = f" conf={conf:.3f}" if isinstance(conf, (int, float)) else ""
            lines_out.append(f"{line.text}\t{poly!r}{extra}")
        try:
            json_pages.append(pred.model_dump(mode="json"))
        except Exception:
            json_pages.append({"text_lines": [tl.text for tl in pred.text_lines]})

    extracted = out_root / "extracted.txt"
    extracted.write_text(
        "\n".join(
            [
                "=" * 72,
                "Surya OCR — lines (text + bbox/polygon + confidence when present)",
                f"Source: {source}",
                f"DPI: {dpi} (SURYA_DPI) | highres: {dpi_hi} (SURYA_DPI_HIGHRES)",
                f"Docs: Context7 /datalab-to/surya",
                "=" * 72,
                "",
                "\n".join(lines_out),
                "",
            ]
        ),
        encoding="utf-8",
    )

    doc_text = out_root / "document_text.txt"
    doc_text.write_text("\n".join(plain_lines), encoding="utf-8")

    results_path = out_root / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "source": str(source),
                "dpi": dpi,
                "dpi_highres": dpi_hi,
                "context7_docs": "/datalab-to/surya",
                "pages": json_pages,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    summary = out_root / "summary.txt"
    n_lines = sum(len(p.text_lines) for p in predictions)
    summary.write_text(
        "\n".join(
            [
                "--- Surya OCR summary ---",
                f"Source: {source}",
                f"Output: {out_root}",
                f"Pages (images): {len(predictions)}",
                f"Text lines: {n_lines}",
                f"DPI / highres DPI: {dpi} / {dpi_hi}",
                f"math_mode: {_math_mode()} (SURYA_MATH)",
                f"return_words: {_return_words()} (SURYA_WORDS)",
                f"drop_repeated_text: {_drop_repeated()} (SURYA_DROP_REPEATED)",
                f"detection_batch_size: {det_bs} (SURYA_DET_BATCH)",
                f"recognition_batch_size: {rec_bs} (SURYA_REC_BATCH)",
                f"DISABLE_TQDM: {getattr(settings, 'DISABLE_TQDM', False)}",
                f"TORCH_DEVICE (env): {os.environ.get('TORCH_DEVICE', '(default)')}",
                f"Time: {elapsed:.2f} s",
                f"Lines + layout: {extracted.name}",
                f"Plain text: {doc_text.name}",
                f"JSON: {results_path.name}",
                "",
                "Documentation (Context7): /datalab-to/surya — RecognitionPredictor, load_from_file, load_pdf.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Wrote: {extracted}")
    print(f"Wrote: {doc_text}")
    print(f"Wrote: {results_path}")
    print(f"Wrote: {summary}")


if __name__ == "__main__":
    main()
