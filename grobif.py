"""
Batch GROBID full-text extraction via grobid-client-python.

Requires a running GROBID server (default http://localhost:8070), e.g.:
  docker run -t --rm -p 8070:8070 lfoppiano/grobid:0.8.2

Environment:
  GROBID_SERVER   — override base URL (default http://localhost:8070)
  GROBID_CONFIG   — optional path to a JSON config file for grobid_client
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from grobid_client.grobid_client import GrobidClient, ServerUnavailableException


def _thread_workers() -> int:
    raw = os.environ.get("GROBID_THREADS", "4")
    try:
        return max(1, int(raw))
    except ValueError:
        return 4


def _pick_pdf(cwd: Path) -> Path:
    pdf = cwd / "Holiday 2026.pdf"
    if pdf.exists():
        return pdf
    matches = sorted(cwd.glob("*.pdf"))
    if not matches:
        raise FileNotFoundError(
            "No PDF found. Place Holiday 2026.pdf in the project directory or add a .pdf file."
        )
    return matches[0]


def main() -> None:
    cwd = Path(__file__).resolve().parent
    pdf_path = _pick_pdf(cwd)

    out_root = cwd / f"{pdf_path.stem}_extracted_grobid"
    out_root.mkdir(parents=True, exist_ok=True)

    # grobid_client walks input_path for PDFs — use a folder that only contains our file
    input_dir = out_root / "grobid_input"
    if input_dir.exists():
        shutil.rmtree(input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_path, input_dir / pdf_path.name)

    server = os.environ.get("GROBID_SERVER", "http://localhost:8070")
    config_file = os.environ.get("GROBID_CONFIG")

    client_kwargs: dict = {"grobid_server": server, "verbose": True}
    if config_file:
        p = Path(config_file).expanduser()
        if p.is_file():
            client_kwargs["config_path"] = str(p)

    try:
        client = GrobidClient(**client_kwargs)
    except ServerUnavailableException as exc:
        print(f"GROBID server not reachable: {exc}", file=sys.stderr)
        print(
            f"Start GROBID (e.g. docker run -t --rm -p 8070:8070 lfoppiano/grobid:0.8.2) "
            f"or set GROBID_SERVER.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    # Note: API uses `output`, not `output_path`
    client.process(
        service="processFulltextDocument",
        input_path=str(input_dir),
        output=str(out_root),
        n=_thread_workers(),
        json_output=True,
    )

    print(f"Done. TEI/JSON under: {out_root}")


if __name__ == "__main__":
    main()
