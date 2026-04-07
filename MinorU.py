"""
Run MinerU (OpenDataLab ``mineru``) on a PDF and collect Markdown output under an output folder.

MinerU 3.x does **not** expose ``mineru.partition``; parsing is done via the ``mineru`` CLI
(``python -m mineru.cli.client``), same as ``mineru -p … -o …``.

Environment:
  MINERU_SOURCE           — path to PDF (or image dir); default: Holiday 2026.pdf or first *.pdf in cwd
  MINERU_OUTPUT_DIR       — optional output parent directory; default: ``{stem}_extracted_mineru`` next to this script
  MINERU_BACKEND          — pipeline | vlm-http-client | hybrid-http-client | vlm-auto-engine | hybrid-auto-engine
                            (default: hybrid-auto-engine)
  MINERU_METHOD           — auto | txt | ocr (default: auto)
  MINERU_LANG             — e.g. ch, en (default: ch)
  MINERU_START            — start page index (0-based), passed as -s
  MINERU_END              — end page index (0-based), passed as -e
  MINERU_API_URL          — optional MinerU FastAPI base URL (else CLI may start a local API)
  MINERU_SERVER_URL       — for *-http-client backends, passed as -u
  MINERU_FORMULA          — 0 to disable formula parsing (-f false)
  MINERU_TABLE            — 0 to disable table parsing (-t false)
  MINERU_EXTRA_ARGS       — extra CLI tokens (space-separated, quoted carefully in shell)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_BACKENDS = frozenset(
    {
        "pipeline",
        "vlm-http-client",
        "hybrid-http-client",
        "vlm-auto-engine",
        "hybrid-auto-engine",
    }
)
_METHODS = frozenset({"auto", "txt", "ocr"})


def _pick_pdf(cwd: Path) -> Path:
    pdf = cwd / "Holiday 2026.pdf"
    if pdf.exists():
        return pdf
    matches = sorted(cwd.glob("*.pdf"))
    if not matches:
        raise FileNotFoundError(
            "No PDF found. Set MINERU_SOURCE or add a .pdf in the project directory."
        )
    return matches[0]


def _resolve_source(cwd: Path) -> Path:
    raw = os.environ.get("MINERU_SOURCE", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"MINERU_SOURCE not found: {p}")
        return p
    return _pick_pdf(cwd)


def _env_choice(name: str, default: str, allowed: frozenset[str]) -> str:
    raw = os.environ.get(name, default).strip()
    if raw not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}; got {raw!r}")
    return raw


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no")


def _extra_cli_args() -> list[str]:
    raw = os.environ.get("MINERU_EXTRA_ARGS", "").strip()
    if not raw:
        return []
    return re.split(r"\s+", raw)


def _find_markdown_files(root: Path) -> list[Path]:
    return sorted(root.glob("**/*.md"))


def main() -> None:
    cwd = Path(__file__).resolve().parent
    source = _resolve_source(cwd)
    stem = source.stem

    out_raw = os.environ.get("MINERU_OUTPUT_DIR", "").strip()
    out_root = Path(out_raw).expanduser() if out_raw else (cwd / f"{stem}_extracted_mineru")
    out_root.mkdir(parents=True, exist_ok=True)

    backend = _env_choice("MINERU_BACKEND", "hybrid-auto-engine", _BACKENDS)
    method = _env_choice("MINERU_METHOD", "auto", _METHODS)
    lang = os.environ.get("MINERU_LANG", "ch").strip() or "ch"

    cmd: list[str] = [
        sys.executable,
        "-m",
        "mineru.cli.client",
        "-p",
        str(source),
        "-o",
        str(out_root),
        "-b",
        backend,
        "-m",
        method,
        "-l",
        lang,
        "-f",
        str(_env_bool("MINERU_FORMULA", True)),
        "-t",
        str(_env_bool("MINERU_TABLE", True)),
    ]

    start_s = os.environ.get("MINERU_START", "").strip()
    if start_s:
        cmd.extend(["-s", start_s])
    end_s = os.environ.get("MINERU_END", "").strip()
    if end_s:
        cmd.extend(["-e", end_s])

    api_url = os.environ.get("MINERU_API_URL", "").strip()
    if api_url:
        cmd.extend(["--api-url", api_url])
    server_url = os.environ.get("MINERU_SERVER_URL", "").strip()
    if server_url:
        cmd.extend(["-u", server_url])

    cmd.extend(_extra_cli_args())

    print(
        f"MinerU: {source.name} → {out_root} (backend={backend}, method={method}) …",
        file=sys.stderr,
    )
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0

    md_files = _find_markdown_files(out_root)
    combined = "\n\n".join(
        f"<!-- {p.relative_to(out_root)} -->\n\n{p.read_text(encoding='utf-8', errors='replace')}"
        for p in md_files
    )
    extracted = out_root / "extracted.md"
    if combined.strip():
        extracted.write_text(combined, encoding="utf-8")
    else:
        extracted.write_text(
            "(No .md files found under output tree; see mineru stderr.)\n",
            encoding="utf-8",
        )

    result_json = out_root / "result.json"
    payload = {
        "source": str(source),
        "output_dir": str(out_root),
        "command": cmd,
        "returncode": proc.returncode,
        "seconds": round(elapsed, 3),
        "markdown_files": [str(p.relative_to(out_root)) for p in md_files],
        "stdout_tail": (proc.stdout or "")[-8000:],
        "stderr_tail": (proc.stderr or "")[-8000:],
    }
    result_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = out_root / "summary.txt"
    summary.write_text(
        "\n".join(
            [
                "--- MinerU (mineru CLI) summary ---",
                f"Source: {source}",
                f"Output: {out_root}",
                f"Backend: {backend} (MINERU_BACKEND)",
                f"Method: {method} | Lang: {lang}",
                f"Return code: {proc.returncode}",
                f"Time: {elapsed:.2f} s",
                f"Markdown files found: {len(md_files)}",
                f"Aggregated MD: {extracted.name}",
                f"Run metadata: {result_json.name}",
                "",
                "CLI: python -m mineru.cli.client (see `mineru --help`).",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Wrote: {extracted}")
    print(f"Wrote: {result_json}")
    print(f"Wrote: {summary}")

    if proc.returncode != 0:
        print(proc.stderr or proc.stdout or "(no output)", file=sys.stderr)
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
