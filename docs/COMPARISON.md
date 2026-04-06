# Parser comparison, performance insights, and decision rules

This document summarizes how parsers in this benchmark differ, what to expect in practice, and how to choose one for production. It is derived from the tool’s parser implementations and typical runtime behavior—not from a single fixed benchmark run.

---

## 1. Comparison table

Legend: **Speed** = typical relative cost (fast / medium / slow / very slow). **OCR** = optical character recognition. **Tables** = table extraction. **Structure** = layout/elements/metadata beyond plain text. **LLM** = whether this wrapper typically uses a remote LLM API (vs local ML/OCR only).

| Parser | Category | Speed | OCR | Tables | Structure | LLM / remote API | Commercial OK* |
|--------|----------|-------|-----|--------|-----------|------------------|----------------|
| PyMuPDF (fitz) | Core | Fast | No | No | No | No | ⚠️ AGPL (commercial needs license) |
| pdfplumber | Core | Fast | No | Basic (page tables) | Light | No | Yes |
| pdfminer.six | Core | Fast | No | No | No | No | Yes |
| Tesseract (pytesseract) | OCR | Medium–slow | Yes | No | No | No | Yes |
| EasyOCR | OCR | Slow | Yes | No | No | No | Yes |
| PaddleOCR | OCR | Slow | Yes | No | No | No | Yes |
| DocTR | OCR | Slow | Yes | No | Export JSON | No | Yes |
| Camelot | Tables | Medium | No | Yes | No | No | Yes |
| Tabula-py | Tables | Medium | No | Yes | No | No | Yes |
| LayoutParser | Layout | Slow | No | No | Regions/boxes | No | Yes |
| Unstructured (advanced) | Layout + ML | Very slow | Via hi_res | Often | Elements | No | Yes |
| GROBID | Scholarly | Medium | No | Limited | TEI/XML | No (local server) | Yes |
| MinerU (best-effort) | Modern | Varies | Varies | Varies | Markdown/CLI | Depends on package | Verify |
| LiteParse (best-effort) | Modern | Varies | Varies | Varies | Dict | Depends on package | Verify |
| Docling | Modern | Slow | Often | Sometimes | Yes (markdown/dict) | No (local) | Yes |
| LLMSherpa | LLM API | Network-bound | **Via service** | **Via service** | Chunks | **Yes (HTTP API)** | Yes |

\*Always confirm the exact wheel/package license in your environment.

### Commercial-only parsers (default in the Streamlit app)

Use **Parser set → Commercial-safe (default)** to exclude **PyMuPDF (AGPL)**. Use **Commercial + local only (no hosted API)** to also exclude **LLMSherpa** (no outbound HTTP to a document API).

| Parser | Hosting / runtime | Setup complexity | Scenario hints |
|--------|-------------------|------------------|----------------|
| pdfplumber | Local | Low | Text PDFs, simple tables |
| pdfminer.six | Local | Low | Text extraction, layout-agnostic |
| Tesseract | Local + **system binary** | Medium | Scanned PDFs |
| EasyOCR | Local + **downloads models** | Medium–high | Scanned PDFs |
| PaddleOCR | Local + **downloads models** | Medium–high | Scanned PDFs |
| DocTR | Local + **downloads models** | Medium–high | Scanned PDFs, JSON export |
| Camelot | Local + often **Ghostscript** | Medium | Complex / lattice tables |
| Tabula-py | Local + **Java** | Medium | Tables (Java stack) |
| LayoutParser | Local + **heavy ML** | High | Layout regions |
| Unstructured (advanced) | Local + **models** | Very high | Tables + hierarchy + structure |
| GROBID | **Local server** `localhost:8070` | High | Scholarly / TEI |
| MinerU | Local CLI (if installed) | Varies | Verify license of your build |
| LiteParse | Local (if installed) | Varies | Verify package license |
| Docling | Local + **models** | High | Markdown / structured export |
| LLMSherpa | **Hosted HTTP API** (configurable URL) | Low client, policy on vendor | Chunked text via service |

### Scenario verification (fixtures)

Place PDFs under `benchmark/fixtures/` (see `benchmark/fixtures/README.md`) and run:

```bash
python scripts/benchmark_scenarios.py
```

Reports: `benchmark/reports/<timestamp>/summary.json`, `summary.csv`, `ANALYSIS.md`.

Executable ranking helpers live in `utils/commercial_guide.py` (`suggested_parsers_for_scenario`, `best_parser_for_scenario`).

---

## 2. Performance insights

### Throughput and cold start

- **First run** of OCR-heavy parsers (EasyOCR, PaddleOCR, DocTR) and **layout hi_res** (Unstructured) often **downloads large models** and can take many minutes; subsequent runs are faster if caches are warm.
- **PyMuPDF** and **pdfminer/pdfplumber** are usually the **fastest** for born-digital text PDFs.
- **Tesseract** time scales roughly with **page count × DPI** (this app renders pages to images for OCR).

### Memory and CPU

- **torch**-based stacks (EasyOCR, PaddleOCR, DocTR, parts of Docling/Unstructured) use **significant RAM** and may spike CPU.
- **tracemalloc** “memory heap Δ” in the app is a **Python heap** estimate; native allocations (GPU, large libs) may not fully show.
- **Memory RSS Δ (MB)** uses `psutil` process RSS before/after each parser run; it is closer to ops reality but still **approximate** (GC, allocator caching).

### Normalized speed

- **Sec/10 pages** = `(execution_time_sec / pages_processed) * 10` when `pages_processed > 0`; use it to compare runs on PDFs with different page counts.

### Reliability by PDF type

- **Born-digital text PDFs:** Core parsers (PyMuPDF, pdfplumber, pdfminer) usually give the best **text fidelity** and speed.
- **Scanned PDFs:** OCR parsers (Tesseract, EasyOCR, PaddleOCR, DocTR) are required; quality varies by scan resolution and fonts.
- **Tables:** Camelot/Tabula are specialized; **Unstructured** can help when tables are visually complex but is heavier.
- **Academic / structured citations:** **GROBID** shines when a **local GROBID server** is available; otherwise it will fail or error.

### External dependencies

- **Tesseract:** needs **system** `tesseract` on `PATH`.
- **Tabula:** needs **Java**; optional **jpype** for in-process path.
- **GROBID:** needs **server** at `http://localhost:8070` (as in this project).
- **LLMSherpa:** needs **network** to `LLMSHERPA_API_URL` (and any API key your provider requires—**not** wired in the default wrapper).

### Recommendation heuristic in the app

The built-in “Recommended parser” uses **scores** from text length, structured output, tables, speed, and **penalizes errors**—it is **not** a human quality judgment. Use it as a **starting point**, then validate on your documents.

---

## 3. Decision rules

Use these **if/then** rules after you run the benchmark on **representative PDFs** (same mix as production: text, scan, tables, multi-page).

### Licensing & compliance

1. **If** you cannot use AGPL in your product **→** avoid **PyMuPDF** unless you have a commercial PyMuPDF license, or treat it as dev-only.
2. **If** you must avoid external data **→** avoid **LLMSherpa** (or host your own endpoint with your policy).

### Document type

3. **If** the PDF is **mostly selectable text** and you need **speed** **→** prefer **pdfplumber** or **pdfminer.six**; **PyMuPDF** if speed is critical and license is acceptable.
4. **If** the PDF is **scanned** or **image-only** **→** use at least one OCR parser (**Tesseract**, **EasyOCR**, **PaddleOCR**, or **DocTR**); compare outputs on your scans.
5. **If** tables are **critical** and PDFs are **lattice/stream** style **→** run **Camelot** and **Tabula-py**; add **Unstructured (hi_res)** if you need layout + structure and can pay the cost.
6. **If** you need **semantic scholarly XML** (TEI) **→** **GROBID** with a running server.
7. **If** you need **RAG-ready markdown / structured export** for downstream LLMs **→** **Docling** and/or **Unstructured** (and **LLMSherpa** if you accept a hosted LLM API).

### Operations

8. **If** you need **predictable cold starts** in production **→** pre-download models and bake them into images, or restrict parsers to core + one OCR stack.
9. **If** a parser fails **→** record `errors` in `outputs/.../result.json`; do not auto-promote that parser for that document class.

### Final selection workflow

10. **Benchmark** each document class with **Run all parsers sequentially** (or your chosen subset).
11. **Rank** by: (a) extraction correctness on your spot checks, (b) **p95 latency** and cost, (c) license and ops constraints.
12. **Lock** the choice per **document class** (route: text vs scan vs table-heavy), not one global “best parser” for all PDFs.

---

## See also

- `README.md` — setup, system dependencies, and license table.
- `outputs/<parser_name>/.../result.json` — per-run metrics and errors for your own evidence.
- `scripts/benchmark_scenarios.py` — batch commercial benchmark + `ANALYSIS.md`.
