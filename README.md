# PDF Parser Benchmark Tool

Production-oriented Streamlit benchmark app for comparing multiple PDF parsing, OCR, table extraction, layout, and LLM-based document processors on the same file.

## What It Does

- Upload one PDF and run selected parsers against it.
- Captures execution time, memory delta, and pages processed.
- Stores parser outputs under `outputs/<parser_name>/...`.
- Shows extracted text, tables, images, and structured JSON where available.
- Produces an automatic recommendation: **"Recommended parser: X"** based on quality/speed heuristics.
- Flags restrictive licenses in UI with: `⚠️ Not suitable for commercial use`.

## Included Parsers

### Traditional / Core
- PyMuPDF (`fitz`)
- pdfplumber
- pdfminer.six

### OCR
- Tesseract OCR (`pytesseract`)
- EasyOCR
- PaddleOCR
- DocTR
- RapidOCR PDF
- Surya OCR

### Table Extraction
- Camelot
- Tabula-py

### Layout / Structure
- LayoutParser
- Unstructured (advanced settings)
- GROBID (requires local server)

### Modern / LLM-based
- MinerU (best-effort CLI integration)
- LiteParse (best-effort dynamic API integration)
- Docling
- LLMSherpa
- Marker

### Script-backed integrations
- `RapidOCR PDF`, `Surya OCR`, and `Marker` are run through local wrapper scripts.
- The app invokes `rapidocr.py`, `suryaocr.py`, and `marker.py` with `python` and captures their generated outputs.

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies **using the same interpreter** you will use to run Streamlit:

```bash
python -m pip install -r requirements.txt
```

Avoid bare `pip install` if your shell might point `pip` at a different Python than `python`.

3. System dependencies (important):
- Tesseract binary must be installed and available in `PATH`.
- Java is required for `tabula-py`.
- Ghostscript is commonly needed by `camelot`.
- For GROBID, run a GROBID server at `http://localhost:8070`.
- Some OCR/LLM parsers download large models on first run.
- Optional parser extras (if available in your environment):

```bash
pip install magic-pdf liteparse
```

4. Run the app **with that same interpreter** (recommended):

```bash
python -m streamlit run app.py
```

Or use the bundled launcher (always uses `.venv`):

```bash
chmod +x run_app.sh
./run_app.sh
```

## Test Recommendations (Document Coverage)

Run benchmarks across:

- Simple PDFs
- Complex hierarchical documents
- Table-heavy PDFs
- Multi-page tables
- Scanned PDFs

Use the summary table and side-by-side tabs to compare extraction quality and operational cost.

## License / Commercial Use Guidance

| Parser | Typical License | Commercial Suitability |
|---|---|---|
| PyMuPDF | AGPL-3.0 | ⚠️ Not suitable for commercial use (without commercial license) |
| pdfplumber | MIT | Suitable |
| pdfminer.six | MIT | Suitable |
| pytesseract / Tesseract | Apache-2.0 | Suitable |
| EasyOCR | Apache-2.0 | Suitable |
| PaddleOCR | Apache-2.0 | Suitable |
| DocTR | Apache-2.0 | Suitable |
| RapidOCR PDF | Apache-2.0 | Suitable |
| Surya OCR | Varies by package | Verify in your deployment |
| Camelot | MIT | Suitable |
| Tabula-py | MIT | Suitable |
| LayoutParser | Apache-2.0 | Suitable |
| Unstructured | Apache-2.0 | Suitable |
| GROBID | Apache-2.0 | Suitable |
| MinerU | Varies by distribution | Verify in your deployment |
| LiteParse | Varies by package | Verify in your deployment |
| Docling | MIT | Suitable |
| LLMSherpa | Apache-2.0 | Suitable |
| Marker | MIT | Suitable |

Always verify the exact installed package license/version before production rollout.

## When To Use Which Parser

- **Fast baseline text extraction:** PyMuPDF, pdfplumber
- **Noisy/scanned documents:** Tesseract, EasyOCR, PaddleOCR, DocTR
- **Modern OCR quality focus:** RapidOCR PDF, Surya OCR, Marker
- **Table-heavy financial/report docs:** Camelot, Tabula-py, Unstructured
- **Layout-aware parsing:** LayoutParser, Unstructured, GROBID
- **LLM/RAG pipeline-ready structure:** Docling, LLMSherpa, Unstructured, MinerU/LiteParse (if environment supports them)

For a fuller **comparison table**, **performance insights**, and **decision rules**, see [`docs/COMPARISON.md`](docs/COMPARISON.md).

## Project Structure

```
app.py
parsers/
  base.py
  common.py
  tesseract_parser.py
  pymupdf_parser.py
  pdfplumber_parser.py
  unstructured_parser.py
  doctr_parser.py
  script_parsers.py
  camelot_parser.py
  mineru_parser.py
  liteparse_parser.py
  docling_parser.py
  llmsherpa_parser.py
  registry.py
utils/
  timer.py
  memory.py
  evaluator.py
outputs/
```
