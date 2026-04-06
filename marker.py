"""
Convert a PDF with Marker (datalab-to/marker) and write Markdown/JSON/HTML + images.

Local file ``marker.py`` shadows the installed ``marker`` package — this directory is
removed from ``sys.path`` before importing.

Uses the same flow as ``marker.scripts.convert_single``: ``create_model_dict``,
``PdfConverter``, ``ConfigParser``, then ``text_from_rendered`` + files under
``{stem}_extracted_marker/``.

Environment:
  MARKER_SOURCE          — path to PDF (default: Holiday 2026.pdf or first *.pdf in cwd)
  MARKER_FORMAT          — markdown | json | html | chunks (default: markdown)
  MARKER_PAGE_RANGE      — e.g. 0,5-10 (page indices, same as Marker CLI)
  MARKER_USE_LLM         — set to 1 to enable LLM processors (needs API keys / service)
  MARKER_NO_IMAGES       — set to 1 for --disable_image_extraction
  TORCH_DEVICE / MARKER_DEVICE — optional torch device for Surya models inside Marker
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Local file ``marker.py`` shadows the ``marker`` package.
_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR in sys.path:
    sys.path.remove(_THIS_DIR)

os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault(
    "PYTORCH_ENABLE_MPS_FALLBACK",
    "1",
)

from marker.config.parser import ConfigParser  # noqa: E402
from marker.converters.pdf import PdfConverter  # noqa: E402
from marker.logger import configure_logging  # noqa: E402
from marker.models import create_model_dict  # noqa: E402
from marker.output import convert_if_not_rgb, text_from_rendered  # noqa: E402
from marker.settings import settings as marker_settings  # noqa: E402


def _pick_pdf(cwd: Path) -> Path:
    pdf = cwd / "Holiday 2026.pdf"
    if pdf.exists():
        return pdf
    matches = sorted(cwd.glob("*.pdf"))
    if not matches:
        raise FileNotFoundError(
            "No PDF found. Set MARKER_SOURCE or add a .pdf in the project directory."
        )
    return matches[0]


def _resolve_source(cwd: Path) -> Path:
    raw = os.environ.get("MARKER_SOURCE", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"MARKER_SOURCE not found: {p}")
        return p
    return _pick_pdf(cwd)


def _device_kwargs() -> dict:
    dev = os.environ.get("MARKER_DEVICE", os.environ.get("TORCH_DEVICE", "")).strip()
    if not dev:
        return {}
    return {"device": dev}


def _cli_options() -> dict:
    fmt = os.environ.get("MARKER_FORMAT", "markdown").strip().lower()
    if fmt not in ("markdown", "json", "html", "chunks"):
        fmt = "markdown"
    opts: dict = {
        "output_format": fmt,
        "use_llm": os.environ.get("MARKER_USE_LLM", "").lower()
        in ("1", "true", "yes"),
        "output_dir": marker_settings.OUTPUT_DIR,
    }
    pr = os.environ.get("MARKER_PAGE_RANGE", "").strip()
    if pr:
        opts["page_range"] = pr
    if os.environ.get("MARKER_NO_IMAGES", "").lower() in ("1", "true", "yes"):
        opts["disable_image_extraction"] = True
    return opts


def main() -> None:
    configure_logging()
    cwd = Path(__file__).resolve().parent
    source = _resolve_source(cwd)
    stem = source.stem
    out_root = cwd / f"{stem}_extracted_marker"
    out_root.mkdir(parents=True, exist_ok=True)

    cli_options = _cli_options()
    config_parser = ConfigParser(cli_options)

    print(
        f"Marker: converting {source.name} → {out_root.name}/ "
        f"(format={cli_options['output_format']}, use_llm={cli_options['use_llm']}) …",
        file=sys.stderr,
    )

    t0 = time.perf_counter()
    models = create_model_dict(**_device_kwargs())
    converter = PdfConverter(
        config=config_parser.generate_config_dict(),
        artifact_dict=models,
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
        llm_service=config_parser.get_llm_service(),
    )
    rendered = converter(str(source))
    elapsed = time.perf_counter() - t0

    text, ext, images = text_from_rendered(rendered)
    text = text.encode(marker_settings.OUTPUT_ENCODING, errors="replace").decode(
        marker_settings.OUTPUT_ENCODING
    )

    main_file = out_root / f"extracted.{ext}"
    main_file.write_text(text, encoding=marker_settings.OUTPUT_ENCODING)

    meta_path = out_root / "metadata.json"
    meta_path.write_text(
        json.dumps(rendered.metadata, indent=2, ensure_ascii=False, default=str),
        encoding=marker_settings.OUTPUT_ENCODING,
    )

    n_img = 0
    for img_name, img in images.items():
        img = convert_if_not_rgb(img)
        img.save(
            str(out_root / img_name),
            format=marker_settings.OUTPUT_IMAGE_FORMAT,
        )
        n_img += 1

    summary = out_root / "summary.txt"
    summary.write_text(
        "\n".join(
            [
                "--- Marker extraction summary ---",
                f"Source: {source}",
                f"Output: {out_root}",
                f"Format: {cli_options['output_format']}",
                f"use_llm: {cli_options['use_llm']}",
                f"Images written: {n_img}",
                f"Time: {elapsed:.2f} s",
                f"Main file: {main_file.name}",
                f"Metadata: {meta_path.name}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Wrote: {main_file}")
    print(f"Wrote: {meta_path}")
    if n_img:
        print(f"Wrote: {n_img} image(s) under {out_root}")
    print(f"Wrote: {summary}")


if __name__ == "__main__":
    main()
