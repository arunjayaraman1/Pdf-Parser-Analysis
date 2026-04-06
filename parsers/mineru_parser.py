from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class MinerUParser(BasePDFParser):
    name = "MinerU (best-effort)"
    license_name = "Apache-2.0 (check installed package)"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            # Best-effort CLI integration: falls back gracefully if command is unavailable.
            if shutil.which("magic-pdf") is None:
                raise RuntimeError(
                    "magic-pdf CLI was not found on PATH. Install MinerU CLI and ensure `magic-pdf` is executable."
                )
            cmd = ["magic-pdf", "-p", str(path), "-o", str(out)]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise RuntimeError(f"MinerU command failed: {proc.stderr.strip() or proc.stdout.strip()}")
            md_files = list(out.glob("**/*.md"))
            if md_files:
                result.text = "\n\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in md_files)
            result.structured = {"stdout": proc.stdout[-4000:]}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
