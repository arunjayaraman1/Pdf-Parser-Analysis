from __future__ import annotations

import json
from pathlib import Path

from parsers.base import BasePDFParser, ParseResult
from parsers.common import profiled_parse


class CamelotParser(BasePDFParser):
    name = "Camelot"
    license_name = "MIT"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            import camelot
            import fitz

            doc = fitz.open(path)
            result.pages_processed = len(doc)
            tables = camelot.read_pdf(str(path), pages="all")
            table_dir = out / "tables"
            table_dir.mkdir(parents=True, exist_ok=True)
            for i, table in enumerate(tables):
                csv_path = table_dir / f"table-{i + 1}.csv"
                table.to_csv(csv_path)
                result.tables.append({"index": i + 1, "shape": table.shape, "csv_path": str(csv_path)})
            result.structured = {"tables_found": len(result.tables)}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)


class TabulaParser(BasePDFParser):
    name = "Tabula-py"
    license_name = "MIT"
    commercial_use_ok = True

    def parse(self, pdf_path: Path, output_dir: Path) -> ParseResult:
        def _parse(path: Path, out: Path, result: ParseResult) -> None:
            import fitz
            import tabula

            doc = fitz.open(path)
            result.pages_processed = len(doc)
            tables = tabula.read_pdf(str(path), pages="all", multiple_tables=True)
            table_dir = out / "tables"
            table_dir.mkdir(parents=True, exist_ok=True)
            for i, df in enumerate(tables or []):
                csv_path = table_dir / f"table-{i + 1}.csv"
                df.to_csv(csv_path, index=False)
                result.tables.append({"index": i + 1, "rows": len(df), "cols": len(df.columns), "csv_path": str(csv_path)})
            result.structured = {"tables_found": len(result.tables)}
            (out / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")

        return profiled_parse(self.name, self.license_name, self.commercial_use_ok, _parse, pdf_path, output_dir)
