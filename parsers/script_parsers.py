from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_script(script_name: str, source_env_key: str, pdf_path: Path) -> subprocess.CompletedProcess[str]:
    root = _repo_root()
    env = os.environ.copy()
    env[source_env_key] = str(pdf_path)
    return subprocess.run(
        [sys.executable, str(root / script_name)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _copy_generated_dir(src: Path, out: Path) -> None:
    if not src.exists():
        return
    dst = out / "script_output"
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _pdf_page_count(path: Path) -> int:
    try:
        import fitz

        with fitz.open(path) as doc:
            return len(doc)
    except Exception:  # noqa: BLE001
        return 0


class RapidOCRParser(BasePDFParser):
    name = "RapidOCR PDF"
    license_name = "Apache-2.0"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            proc = _run_script("rapidocr.py", "RAPIDOCR_SOURCE", path)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "rapidocr.py failed")

            generated = _repo_root() / f"{path.stem}_extracted_rapidocr"
            _copy_generated_dir(generated, out)

            doc_text = generated / "document_text.txt"
            extracted = generated / "extracted.txt"
            if doc_text.exists():
                result.text = doc_text.read_text(encoding="utf-8")
            elif extracted.exists():
                result.text = extracted.read_text(encoding="utf-8")

            payload = _load_json(generated / "results.json")
            result.structured = payload
            pages = payload.get("pages")
            if isinstance(pages, list):
                result.pages_processed = len(pages)
            else:
                result.pages_processed = _pdf_page_count(path)

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)


class MarkerParser(BasePDFParser):
    name = "Marker"
    license_name = "MIT"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            proc = _run_script("marker.py", "MARKER_SOURCE", path)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "marker.py failed")

            generated = _repo_root() / f"{path.stem}_extracted_marker"
            _copy_generated_dir(generated, out)

            extracted_candidates = sorted(generated.glob("extracted.*"))
            if extracted_candidates:
                result.text = extracted_candidates[0].read_text(encoding="utf-8")

            metadata = _load_json(generated / "metadata.json")
            result.structured = metadata
            result.pages_processed = _pdf_page_count(path)

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)


class SuryaOCRParser(BasePDFParser):
    name = "Surya OCR"
    license_name = "Unknown"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            proc = _run_script("suryaocr.py", "SURYA_SOURCE", path)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "suryaocr.py failed")

            generated = _repo_root() / f"{path.stem}_extracted_surya"
            _copy_generated_dir(generated, out)

            doc_text = generated / "document_text.txt"
            extracted = generated / "extracted.txt"
            if doc_text.exists():
                result.text = doc_text.read_text(encoding="utf-8")
            elif extracted.exists():
                result.text = extracted.read_text(encoding="utf-8")

            payload = _load_json(generated / "results.json")
            result.structured = payload
            pages = payload.get("pages")
            if isinstance(pages, list):
                result.pages_processed = len(pages)
            else:
                result.pages_processed = _pdf_page_count(path)

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
