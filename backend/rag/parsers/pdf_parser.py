"""
PDF Parser for Voice AI Agent RAG using pypdf.
Extracts text stream page-by-page and chunks content with page attribution metadata.
"""
import io
from typing import Any, Dict, List, Union
from pypdf import PdfReader
from loguru import logger
from .text_parser import TextParser


class PDFParser:
    """Extracts text from PDF documents and generates page-tagged chunks."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 60):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_parser = TextParser(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def parse_pdf(
        self,
        pdf_source: Union[str, bytes, io.BytesIO],
        base_metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Parses a PDF file path or byte stream into chunks.
        Attaches page_number to each chunk's metadata.
        """
        if isinstance(pdf_source, bytes):
            stream = io.BytesIO(pdf_source)
        elif isinstance(pdf_source, io.BytesIO):
            stream = pdf_source
        else:
            with open(pdf_source, "rb") as f:
                stream = io.BytesIO(f.read())

        try:
            reader = PdfReader(stream)
        except Exception as exc:
            logger.error(f"[PDF_PARSER] Failed to read PDF stream: {exc}")
            raise ValueError(f"Invalid or corrupted PDF file: {exc}") from exc

        results = []
        global_chunk_idx = 0

        for page_num, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                logger.warning(f"[PDF_PARSER] Failed to extract text from page {page_num}: {exc}")
                continue

            cleaned_page = page_text.strip()
            if not cleaned_page:
                continue

            page_meta = dict(base_metadata)
            page_meta["page_number"] = page_num
            page_meta["doc_type"] = "pdf"
            page_meta["is_mcq"] = False

            page_chunks = self.text_parser.chunk_text(cleaned_page, page_meta)
            for ch in page_chunks:
                ch["metadata"]["chunk_index"] = global_chunk_idx
                results.append(ch)
                global_chunk_idx += 1

        logger.info(f"[PDF_PARSER] Extracted {len(results)} chunks across {len(reader.pages)} pages")
        return results
