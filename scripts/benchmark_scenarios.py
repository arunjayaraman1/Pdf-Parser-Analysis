#!/usr/bin/env python3
"""
Batch benchmark: run commercial-safe parsers against benchmark/fixtures PDFs.
Writes benchmark/reports/<timestamp>/summary.json, summary.csv, ANALYSIS.md, REPORT.pdf
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers.registry import get_commercial_parsers
from utils.commercial_guide import SCENARIOS, best_parser_for_scenario, suggested_parsers_for_scenario


def _safe_dir(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")


FIXTURES: list[tuple[str, Path]] = [
    ("complex_tables", ROOT / "benchmark" / "fixtures" / "complex_tables.pdf"),
    ("multipage_tables", ROOT / "benchmark" / "fixtures" / "multipage_tables.pdf"),
    ("hierarchical_text", ROOT / "benchmark" / "fixtures" / "hierarchical_text.pdf"),
    ("scanned", ROOT / "benchmark" / "fixtures" / "scanned.pdf"),
]


def _fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _hosting_and_setup(parser_name: str) -> tuple[str, str]:
    # High-level ops classification for commercial deployment planning.
    if parser_name == "GROBID":
        return ("Local service", "High")
    if parser_name == "LLMSherpa":
        return ("External API", "Low")
    if parser_name == "Tabula-py":
        return ("Local (Java runtime)", "Medium")
    if parser_name == "Camelot":
        return ("Local (Ghostscript often needed)", "Medium")
    if parser_name == "Tesseract OCR (pytesseract)":
        return ("Local (system binary)", "Medium")
    if parser_name in {"EasyOCR", "PaddleOCR", "DocTR", "Docling", "Unstructured (advanced)", "LayoutParser"}:
        return ("Local (ML models)", "High")
    return ("Local", "Low")


def _build_comparison_table(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row.get("skipped"):
            continue
        grouped[str(row["parser"])].append(row)

    table: list[dict[str, object]] = []
    for parser_name, prow in sorted(grouped.items(), key=lambda kv: kv[0].lower()):
        sec10 = [float(r["seconds_per_10_pages"]) for r in prow if r.get("seconds_per_10_pages") is not None]
        heap = [float(r["memory_heap_delta_mb"]) for r in prow if r.get("memory_heap_delta_mb") is not None]
        rss = [float(r["memory_rss_delta_mb"]) for r in prow if r.get("memory_rss_delta_mb") is not None]
        errors = sum(1 for r in prow if r.get("errors"))
        scenarios = sorted({str(r["scenario"]) for r in prow})
        hosting, setup = _hosting_and_setup(parser_name)
        table.append(
            {
                "parser": parser_name,
                "runs": len(prow),
                "error_runs": errors,
                "success_rate_pct": ((len(prow) - errors) / len(prow) * 100.0) if prow else 0.0,
                "avg_seconds_per_10_pages": _avg(sec10),
                "avg_heap_delta_mb": _avg(heap),
                "avg_rss_delta_mb": _avg(rss),
                "hosting": hosting,
                "setup_complexity": setup,
                "scenarios_covered": ", ".join(scenarios),
            }
        )
    return table


def _build_insights(comparison: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    if not comparison:
        return ["No benchmark rows available (fixtures missing or all runs skipped)."]

    by_speed = [r for r in comparison if r["avg_seconds_per_10_pages"] is not None]
    by_speed.sort(key=lambda r: float(r["avg_seconds_per_10_pages"]))  # faster first

    if by_speed:
        fastest = by_speed[:3]
        slowest = by_speed[-3:]
        lines.append(
            "Fastest avg sec/10 pages: "
            + ", ".join(f"{r['parser']} ({_fmt_num(float(r['avg_seconds_per_10_pages']))})" for r in fastest)
        )
        lines.append(
            "Slowest avg sec/10 pages: "
            + ", ".join(f"{r['parser']} ({_fmt_num(float(r['avg_seconds_per_10_pages']))})" for r in slowest)
        )

    by_rss = [r for r in comparison if r["avg_rss_delta_mb"] is not None]
    by_rss.sort(key=lambda r: float(r["avg_rss_delta_mb"]), reverse=True)  # heavier first
    if by_rss:
        heavy = by_rss[:3]
        lines.append(
            "Highest avg RSS delta: "
            + ", ".join(f"{r['parser']} ({_fmt_num(float(r['avg_rss_delta_mb']))} MB)" for r in heavy)
        )

    flaky = sorted(comparison, key=lambda r: float(r["success_rate_pct"]))
    if flaky:
        lines.append(
            "Lowest success rate: "
            + ", ".join(f"{r['parser']} ({_fmt_num(float(r['success_rate_pct']), 1)}%)" for r in flaky[:3])
        )

    return lines


def _build_decision_rules(
    scenario_results: dict[str, list], comparison: list[dict[str, object]]
) -> list[str]:
    lines: list[str] = []
    lines.append(
        "Use parser routing by scenario instead of one global parser. Select from the best-performing parser(s) below."
    )
    for sc in SCENARIOS:
        res = scenario_results.get(sc, [])
        static = suggested_parsers_for_scenario(sc)
        dynamic_best = best_parser_for_scenario(sc, res) if res else None
        if dynamic_best:
            lines.append(f"{sc}: prefer {dynamic_best}; fallback candidates: {', '.join(static[:3])}.")
        else:
            lines.append(f"{sc}: no fixture result yet; start with {', '.join(static[:3])}.")

    external = [r for r in comparison if r["hosting"] == "External API"]
    if external:
        lines.append(
            "For strict data-control or air-gapped environments, avoid external API parsers (for example LLMSherpa)."
        )
    lines.append(
        "If setup simplicity is required, start from Low/Medium setup parsers and add High setup parsers only for hard cases."
    )
    return lines


def _write_report_pdf(
    report_pdf: Path, comparison: list[dict[str, object]], insights: list[str], decision_rules: list[str]
) -> tuple[bool, str]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:  # pragma: no cover - depends on environment deps
        return False, f"REPORT.pdf skipped (reportlab unavailable: {exc})"

    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Commercial PDF Parser Benchmark Report", styles["Title"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Generated: {datetime.now().isoformat()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Comparison table", styles["Heading2"]))
    table_data = [
        [
            "Parser",
            "Runs",
            "Success %",
            "Avg sec/10p",
            "Avg heap MB",
            "Avg RSS MB",
            "Hosting",
            "Setup",
        ]
    ]
    for row in comparison:
        table_data.append(
            [
                str(row["parser"]),
                str(row["runs"]),
                _fmt_num(float(row["success_rate_pct"]), 1),
                _fmt_num(row["avg_seconds_per_10_pages"]),
                _fmt_num(row["avg_heap_delta_mb"]),
                _fmt_num(row["avg_rss_delta_mb"]),
                str(row["hosting"]),
                str(row["setup_complexity"]),
            ]
        )
    comp_table = Table(table_data, repeatRows=1)
    comp_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(comp_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Performance insights", styles["Heading2"]))
    for line in insights:
        story.append(Paragraph(f"- {line}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Decision rules", styles["Heading2"]))
    for line in decision_rules:
        story.append(Paragraph(f"- {line}", styles["Normal"]))

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Notes: sec/10 pages is normalized throughput. RSS delta is approximate and may vary with allocators/caches.",
            styles["Italic"],
        )
    )

    doc = SimpleDocTemplate(str(report_pdf), pagesize=A4)
    doc.build(story)
    return True, f"Wrote {report_pdf}"


def main() -> None:
    report_dir = ROOT / "benchmark" / "reports" / datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir.mkdir(parents=True, exist_ok=True)

    parsers = get_commercial_parsers()
    rows: list[dict[str, object]] = []
    scenario_results: dict[str, list] = {s: [] for s in SCENARIOS}

    for scenario, pdf_path in FIXTURES:
        if not pdf_path.is_file():
            rows.append(
                {
                    "scenario": scenario,
                    "pdf": str(pdf_path),
                    "parser": "_skipped_",
                    "skipped": True,
                    "message": "Fixture file not found",
                }
            )
            continue

        scenario_out = report_dir / scenario
        scenario_out.mkdir(parents=True, exist_ok=True)

        for parser in parsers:
            parser_out = scenario_out / _safe_dir(parser.name)
            parser_out.mkdir(parents=True, exist_ok=True)
            result = parser.parse(pdf_path, parser_out)
            sp = result.seconds_per_10_pages()
            row = {
                "scenario": scenario,
                "pdf": str(pdf_path),
                "parser": result.parser_name,
                "skipped": False,
                "execution_time_sec": result.execution_time_sec,
                "seconds_per_10_pages": sp,
                "memory_heap_delta_mb": result.memory_delta_mb,
                "memory_rss_delta_mb": result.memory_rss_delta_mb,
                "pages_processed": result.pages_processed,
                "table_count": len(result.tables),
                "text_len": len(result.text),
                "errors": result.errors,
                "output_dir": str(parser_out),
            }
            rows.append(row)
            scenario_results[scenario].append(result)

    summary_json = report_dir / "summary.json"
    summary_json.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    csv_path = report_dir / "summary.csv"
    if rows:
        fieldnames = sorted({k for r in rows for k in r.keys()})
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in fieldnames})

    analysis_lines = [
        "# Benchmark analysis (commercial parsers)",
        "",
        f"Generated: {datetime.now().isoformat()}",
        "",
        "## Static suggestions (no run required)",
        "",
    ]
    for sc in SCENARIOS:
        sug = suggested_parsers_for_scenario(sc)
        analysis_lines.append(f"- **{sc}**: try first → {', '.join(sug[:5]) if sug else 'n/a'}")
    analysis_lines.extend(["", "## Best parser by scenario (this run)", ""])

    for sc in SCENARIOS:
        res = scenario_results.get(sc, [])
        if not res:
            analysis_lines.append(f"- **{sc}**: no results (missing fixture or empty)")
            continue
        best = best_parser_for_scenario(sc, res)
        analysis_lines.append(f"- **{sc}**: {best or 'n/a'}")

    analysis_lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `seconds_per_10_pages` extrapolates from total time and page count.",
            "- RSS delta is approximate (native allocations may be under-reported).",
            "",
        ]
    )
    (report_dir / "ANALYSIS.md").write_text("\n".join(analysis_lines), encoding="utf-8")

    comparison = _build_comparison_table(rows)
    insights = _build_insights(comparison)
    decision_rules = _build_decision_rules(scenario_results, comparison)

    analysis_lines.extend(["", "## Comparison table (aggregated by parser)", ""])
    for row in comparison:
        analysis_lines.append(
            (
                f"- {row['parser']}: success={_fmt_num(float(row['success_rate_pct']), 1)}%, "
                f"sec/10p={_fmt_num(row['avg_seconds_per_10_pages'])}, "
                f"heapMB={_fmt_num(row['avg_heap_delta_mb'])}, "
                f"rssMB={_fmt_num(row['avg_rss_delta_mb'])}, "
                f"hosting={row['hosting']}, setup={row['setup_complexity']}"
            )
        )
    analysis_lines.extend(["", "## Performance insights", ""])
    analysis_lines.extend([f"- {line}" for line in insights])
    analysis_lines.extend(["", "## Decision rules", ""])
    analysis_lines.extend([f"- {line}" for line in decision_rules])
    (report_dir / "ANALYSIS.md").write_text("\n".join(analysis_lines), encoding="utf-8")

    report_pdf = report_dir / "REPORT.pdf"
    ok, pdf_status = _write_report_pdf(report_pdf, comparison, insights, decision_rules)

    print(f"Wrote {summary_json}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {report_dir / 'ANALYSIS.md'}")
    print(pdf_status)
    if not ok:
        print("Tip: install reportlab to enable PDF report generation.")


if __name__ == "__main__":
    main()
