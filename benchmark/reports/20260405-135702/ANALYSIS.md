# Benchmark analysis (commercial parsers)

Generated: 2026-04-05T13:57:02.480174

## Static suggestions (no run required)

- **complex_tables**: try first → Camelot, Tabula-py, Unstructured (advanced), pdfplumber, Docling
- **multipage_tables**: try first → Camelot, Tabula-py, Unstructured (advanced), pdfplumber
- **hierarchical_text**: try first → Unstructured (advanced), Docling, pdfplumber, pdfminer.six, GROBID
- **scanned**: try first → Tesseract OCR (pytesseract), EasyOCR, PaddleOCR, DocTR, Unstructured (advanced)

## Best parser by scenario (this run)

- **complex_tables**: no results (missing fixture or empty)
- **multipage_tables**: no results (missing fixture or empty)
- **hierarchical_text**: no results (missing fixture or empty)
- **scanned**: no results (missing fixture or empty)

## Notes

- `seconds_per_10_pages` extrapolates from total time and page count.
- RSS delta is approximate (native allocations may be under-reported).


## Comparison table (aggregated by parser)


## Performance insights

- No benchmark rows available (fixtures missing or all runs skipped).

## Decision rules

- Use parser routing by scenario instead of one global parser. Select from the best-performing parser(s) below.
- complex_tables: no fixture result yet; start with Camelot, Tabula-py, Unstructured (advanced).
- multipage_tables: no fixture result yet; start with Camelot, Tabula-py, Unstructured (advanced).
- hierarchical_text: no fixture result yet; start with Unstructured (advanced), Docling, pdfplumber.
- scanned: no fixture result yet; start with Tesseract OCR (pytesseract), EasyOCR, PaddleOCR.
- If setup simplicity is required, start from Low/Medium setup parsers and add High setup parsers only for hard cases.