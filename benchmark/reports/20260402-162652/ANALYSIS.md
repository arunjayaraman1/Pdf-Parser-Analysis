# Benchmark analysis (commercial parsers)

Generated: 2026-04-02T16:26:52.067339

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
