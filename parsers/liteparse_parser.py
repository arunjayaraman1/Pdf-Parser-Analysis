from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class LiteParseParser(BasePDFParser):
    name = "LiteParse (best-effort)"
    license_name = "Unknown (verify in your environment)"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            if importlib.util.find_spec("liteparse") is None:
                raise RuntimeError(
                    "liteparse is not installed. Install a supported liteparse package or remove LiteParse from the run set."
                )
            module = importlib.import_module("liteparse")

            # Flexible runtime adapter to avoid hard-failing on API variations.
            if hasattr(module, "parse_pdf"):
                payload = module.parse_pdf(str(path))
            elif hasattr(module, "parse"):
                payload = module.parse(str(path))
            else:
                raise RuntimeError("No supported LiteParse API found (expected parse_pdf or parse).")

            if isinstance(payload, dict):
                result.structured = payload
                result.text = str(payload.get("text", ""))[:200000]
            else:
                result.text = str(payload)[:200000]
                result.structured = {"raw": result.text[:5000]}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
