"""
Parse a PDF with LLMSherpa (remote layout API) and save text, sections, and tables.

Uses the same default endpoint as parsers/llmsherpa_parser.py. Override with LLMSHERPA_API_URL.

Environment:
  LLMSHERPA_API_URL       — parse endpoint (default: readers.llmsherpa.com … parseDocument)
  LLMSHERPA_SOURCE        — optional path or https URL to a PDF (default: Holiday 2026.pdf or first *.pdf)
  LLMSHERPA_INSECURE_SSL  — set to 1 to disable TLS certificate verification (debug only; fixes some SSL errors)
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
from pathlib import Path

import urllib3


def _pick_local_pdf(cwd: Path) -> Path:
    pdf = cwd / "Holiday 2026.pdf"
    if pdf.exists():
        return pdf
    matches = sorted(cwd.glob("*.pdf"))
    if not matches:
        raise FileNotFoundError(
            "No PDF found. Set LLMSHERPA_SOURCE or add a .pdf in the project directory."
        )
    return matches[0]


def _resolve_source(cwd: Path) -> str:
    raw = os.environ.get("LLMSHERPA_SOURCE", "").strip()
    if raw:
        return raw
    return str(_pick_local_pdf(cwd))


def _api_url() -> str:
    return os.environ.get(
        "LLMSHERPA_API_URL",
        "https://readers.llmsherpa.com/api/document/developer/parseDocument",
    )


def _insecure_ssl() -> bool:
    return os.environ.get("LLMSHERPA_INSECURE_SSL", "").lower() in (
        "1",
        "true",
        "yes",
    )


def _pool_manager() -> urllib3.PoolManager:
    """urllib3 pools for HTTPS; optional insecure mode for broken TLS / SNI issues."""
    if _insecure_ssl():
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return urllib3.PoolManager(ssl_context=ctx)
    return urllib3.PoolManager()


def _make_reader():
    from llmsherpa.readers.file_reader import LayoutPDFReader as _BaseReader

    url = _api_url()

    class _Reader(_BaseReader):
        def __init__(self, parser_api_url: str) -> None:
            self.parser_api_url = parser_api_url
            pool = _pool_manager()
            self.download_connection = pool
            self.api_connection = pool

    return _Reader(url)


def _stem(source: str) -> str:
    if source.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        name = Path(urlparse(source).path).name
        return name.rsplit(".", 1)[0] if "." in name else (name or "remote")
    return Path(source).resolve().stem


def main() -> None:
    cwd = Path(__file__).resolve().parent
    source = _resolve_source(cwd)
    stem = _stem(source)
    out_root = cwd / f"{stem}_extracted_llmsherpa"
    out_root.mkdir(parents=True, exist_ok=True)

    reader = _make_reader()
    insecure = _insecure_ssl()
    print(
        f"LLMSherpa: parsing {source!r} via {_api_url()!r} "
        f"(TLS verify={'off' if insecure else 'on'}) …",
        file=sys.stderr,
    )

    t0 = time.perf_counter()
    try:
        doc = reader.read_pdf(source)
    except Exception as exc:
        print(f"LLMSherpa request failed: {exc}", file=sys.stderr)
        err = str(exc).lower()
        if "ssl" in err or "tls" in err:
            print(
                "TLS hints: upgrade packages (pip install -U certifi urllib3), check VPN/proxy, "
                "or try LLMSHERPA_INSECURE_SSL=1 once to see if verification is the issue (not for production).",
                file=sys.stderr,
            )
        raise SystemExit(1) from exc
    elapsed = time.perf_counter() - t0

    # Full text from layout chunks (paragraphs, lists, tables as text)
    chunk_lines: list[str] = []
    for node in doc.chunks():
        chunk_lines.append(node.to_text())

    sections = list(doc.sections())
    section_lines: list[str] = []
    for section in sections:
        title = getattr(section, "title", "") or ""
        section_lines.append(f"## {title}\n{section.to_text(include_children=True, recurse=True)}")

    tables = list(doc.tables())
    tables_dir = out_root / "tables"
    tables_dir.mkdir(exist_ok=True)
    for i, table in enumerate(tables, start=1):
        (tables_dir / f"table_{i:02d}.txt").write_text(table.to_text(), encoding="utf-8")

    extracted = out_root / "extracted.txt"
    extracted.write_text(
        "\n\n".join(
            [
                "=" * 72,
                "LLMSherpa — chunks (paragraphs / list items / tables as text)",
                "=" * 72,
                "",
                "\n\n".join(chunk_lines),
                "",
                "=" * 72,
                "Sections",
                "=" * 72,
                "",
                "\n\n".join(section_lines) if section_lines else "(no section headers)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    blocks_path = out_root / "blocks.json"
    try:
        blocks_path.write_text(json.dumps(doc.json, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        blocks_path.write_text(json.dumps({"error": str(exc)}, indent=2), encoding="utf-8")

    summary = out_root / "summary.txt"
    summary.write_text(
        "\n".join(
            [
                "--- LLMSherpa extraction summary ---",
                f"Source: {source}",
                f"API: {_api_url()}",
                f"TLS verify: {'off (LLMSHERPA_INSECURE_SSL)' if insecure else 'on'}",
                f"Output: {out_root}",
                f"Chunks: {len(chunk_lines)}",
                f"Sections: {len(sections)}",
                f"Tables: {len(tables)}",
                f"Time: {elapsed:.2f} s",
                f"Text: {extracted.name}",
                f"Blocks JSON: {blocks_path.name}",
                f"Tables dir: {tables_dir.name}/",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Wrote: {extracted}")
    print(f"Wrote: {blocks_path}")
    print(f"Wrote: {tables_dir}/")
    print(f"Wrote: {summary}")


if __name__ == "__main__":
    main()
