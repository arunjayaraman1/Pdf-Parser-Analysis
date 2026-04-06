from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from parsers.base import ParseResult
from parsers.registry import get_all_parsers, get_commercial_parsers, get_commercial_parsers_local_only
from utils.evaluator import recommend_parser

OUTPUT_ROOT = Path("outputs")


def save_uploaded_pdf(data: bytes, filename: str) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="pdf-benchmark-"))
    file_path = tmp_dir / filename
    file_path.write_bytes(data)
    return file_path


def parser_notes(result: ParseResult) -> str:
    notes = list(result.notes)
    if not result.commercial_use_ok:
        notes.append("⚠️ Not suitable for commercial use")
    if result.errors:
        notes.append("Failed or partial extraction")
    return " | ".join(notes) if notes else "-"


def write_outputs(parser_name: str, result: ParseResult) -> Path:
    safe_name = "".join(c.lower() if c.isalnum() else "-" for c in parser_name).strip("-")
    out_dir = OUTPUT_ROOT / safe_name / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")
    (out_dir / "text.txt").write_text(result.text or "", encoding="utf-8")
    if result.tables:
        for idx, table in enumerate(result.tables, start=1):
            (out_dir / f"table-{idx}.json").write_text(json.dumps(table, indent=2), encoding="utf-8")
    return out_dir


def run_parser(parser, pdf_path: Path) -> ParseResult:
    parser_dir = OUTPUT_ROOT / "".join(c.lower() if c.isalnum() else "-" for c in parser.name).strip("-")
    parser_dir.mkdir(parents=True, exist_ok=True)
    return parser.parse(pdf_path, parser_dir)


def main() -> None:
    st.set_page_config(page_title="PDF Parser Benchmark", layout="wide")
    with st.sidebar:
        st.caption("Interpreter (must match `pip install` target)")
        st.code(sys.executable, language="text")
    st.title("PDF Parser Benchmark Tool")
    st.caption("Compare classic parsers, OCR stacks, table extractors, layout engines, and LLM-based processors.")

    st.subheader("Parser Selection")
    profile = st.radio(
        "Parser set",
        [
            "Commercial-safe (default)",
            "Commercial + local only (no hosted API)",
            "All parsers (incl. AGPL PyMuPDF)",
        ],
        index=0,
        help="Commercial-safe excludes AGPL PyMuPDF. Local-only also excludes LLMSherpa (hosted HTTP).",
    )
    if profile == "Commercial-safe (default)":
        parser_instances = get_commercial_parsers()
    elif profile == "Commercial + local only (no hosted API)":
        parser_instances = get_commercial_parsers_local_only()
    else:
        parser_instances = get_all_parsers()

    mode = st.radio(
        "Benchmark mode",
        ["Manual selection", "Run all parsers sequentially"],
        index=1,
        horizontal=True,
    )
    if mode == "Manual selection":
        selected_names = st.multiselect(
            "Select parsers to run",
            options=[p.name for p in parser_instances],
            default=[p.name for p in parser_instances],
        )
        selected = [p for p in parser_instances if p.name in selected_names]
    else:
        st.info("Running all parsers in the selected set sequentially (best-effort).")
        selected = parser_instances

    uploaded = st.file_uploader("Upload a PDF", type=["pdf"])
    if uploaded is None:
        st.info("Upload a PDF to start benchmarking.")
        return

    if st.button("Run Benchmark", type="primary"):
        if not selected:
            st.warning("Please select at least one parser.")
            return

        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        pdf_path = save_uploaded_pdf(uploaded.getvalue(), uploaded.name)
        results: list[ParseResult] = []
        progress = st.progress(0.0)

        for idx, parser in enumerate(selected, start=1):
            with st.spinner(f"Running {parser.name}..."):
                result = run_parser(parser, pdf_path)
                out_dir = write_outputs(parser.name, result)
                result.notes.append(f"Saved output: {out_dir}")
                results.append(result)
            progress.progress(idx / len(selected))

        st.success("Benchmark run completed.")

        recommendation = recommend_parser(results)
        st.subheader("Recommendation")
        st.markdown(f"**Recommended parser: {recommendation.parser_name}**")
        st.write(recommendation.reason)

        rows = []
        for r in results:
            sp = r.seconds_per_10_pages()
            rows.append(
                {
                    "Parser": r.parser_name,
                    "Time (sec)": round(r.execution_time_sec, 3),
                    "Sec/10 pages": round(sp, 3) if sp is not None else None,
                    "Memory (heap MB)": round(r.memory_delta_mb, 3),
                    "Memory RSS Δ (MB)": round(r.memory_rss_delta_mb, 3),
                    "Pages": r.pages_processed,
                    "OCR": "Yes" if "ocr" in r.parser_name.lower() or r.parser_name in {"DocTR"} else "Maybe",
                    "Tables": len(r.tables),
                    "Multi-page Tables": "Potential" if len(r.tables) > 1 else "No/Unknown",
                    "Structure": "Yes" if bool(r.structured) else "No",
                    "License": r.license_name,
                    "Notes": parser_notes(r),
                }
            )
        summary_df = pd.DataFrame(rows)
        st.subheader("Summary Table")
        st.dataframe(summary_df, width="stretch")

        st.subheader("Side-by-side Comparison")
        tabs = st.tabs([r.parser_name for r in results])
        for idx, (tab, r) in enumerate(zip(tabs, results), start=1):
            with tab:
                if not r.commercial_use_ok:
                    st.warning("⚠️ Not suitable for commercial use")
                if r.errors:
                    st.error("\n".join(r.errors))
                st.metric("Execution Time (sec)", f"{r.execution_time_sec:.3f}")
                sp = r.seconds_per_10_pages()
                st.metric("Sec/10 pages (est.)", f"{sp:.3f}" if sp is not None else "N/A")
                st.metric("Memory heap Δ (MB)", f"{r.memory_delta_mb:.3f}")
                st.metric("Memory RSS Δ (MB)", f"{r.memory_rss_delta_mb:.3f}")
                st.metric("Pages Processed", r.pages_processed)
                st.text_area("Extracted Text", r.text[:50000], height=250, key=f"extracted-text-{idx}")
                st.write("Tables")
                st.json(r.tables[:20] if r.tables else [])
                st.write("Structured Output (JSON)")
                st.json(r.structured if r.structured else {})
                if r.images:
                    st.write("Extracted Images")
                    for img in r.images[:12]:
                        st.image(img, caption=img, width="stretch")


if __name__ == "__main__":
    main()
