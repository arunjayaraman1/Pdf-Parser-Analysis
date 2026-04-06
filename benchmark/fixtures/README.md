# Benchmark PDF fixtures

Place PDFs here for **scenario-based verification** (see `scripts/benchmark_scenarios.py`). Filenames are conventional; you supply the files.

| File | Scenario | What to verify |
|------|----------|----------------|
| `complex_tables.pdf` | `complex_tables` | Merged cells, nested headers, non-grid layouts |
| `multipage_tables.pdf` | `multipage_tables` | Table continues across pages |
| `hierarchical_text.pdf` | `hierarchical_text` | Headings, lists, multi-column or nested sections |
| `scanned.pdf` | `scanned` | Image-only or low text layer; OCR required |

## Obtaining samples

- Use **internal** representative documents (recommended for production decisions).
- Or use **public-domain** PDFs that match each scenario (check license before redistribution).

Do not commit large proprietary PDFs to git unless policy allows.

## Run

From project root (with venv activated):

```bash
python scripts/benchmark_scenarios.py
```

Reports are written under `benchmark/reports/<timestamp>/` (`summary.json`, `summary.csv`, `ANALYSIS.md`, `REPORT.pdf`).

Missing fixture files are **skipped** with a note in the report.
