from __future__ import annotations

from parsers.base import BasePDFParser
from parsers.camelot_parser import CamelotParser, TabulaParser
from parsers.docling_parser import DoclingParser
from parsers.doctr_parser import DocTRParser
from parsers.liteparse_parser import LiteParseParser
from parsers.llmsherpa_parser import LLMSherpaParser
from parsers.mineru_parser import MinerUParser
from parsers.pdfplumber_parser import PDFMinerParser, PDFPlumberParser
from parsers.pymupdf_parser import PyMuPDFParser
from parsers.script_parsers import MarkerParser, RapidOCRParser, SuryaOCRParser
from parsers.tesseract_parser import EasyOCRParser, PaddleOCRParser, TesseractOCRParser
from parsers.unstructured_parser import GrobidParser, LayoutParserEngine, UnstructuredParser


def get_all_parsers() -> list[BasePDFParser]:
    return [
        PyMuPDFParser(),
        PDFPlumberParser(),
        PDFMinerParser(),
        TesseractOCRParser(),
        EasyOCRParser(),
        PaddleOCRParser(),
        DocTRParser(),
        RapidOCRParser(),
        SuryaOCRParser(),
        CamelotParser(),
        TabulaParser(),
        LayoutParserEngine(),
        UnstructuredParser(),
        GrobidParser(),
        MarkerParser(),
        MinerUParser(),
        LiteParseParser(),
        DoclingParser(),
        LLMSherpaParser(),
    ]


def get_commercial_parsers() -> list[BasePDFParser]:
    """Parsers suitable for typical commercial use (excludes AGPL PyMuPDF, etc.)."""
    return [p for p in get_all_parsers() if p.commercial_use_ok]


def get_commercial_parsers_local_only() -> list[BasePDFParser]:
    """Commercial parsers that do not call a hosted HTTP API (excludes LLMSherpa)."""
    return [p for p in get_commercial_parsers() if p.name != "LLMSherpa"]
