"""
Markdown Parser for Voice AI Agent RAG.
Maintains heading hierarchy (#, ##, ###) and attaches breadcrumb context to chunks.
"""
import re
from typing import Any, Dict, List
from .text_parser import TextParser


class MarkdownParser:
    """Chunks Markdown documents while respecting heading boundaries and hierarchy."""

    HEADING_REGEX = re.compile(r"^\s*(#{1,6})\s+(.+)$", re.MULTILINE)

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 60):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_parser = TextParser(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def parse_markdown(self, markdown_text: str, base_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parses Markdown text into heading-aware semantic chunks."""
        if not markdown_text or not markdown_text.strip():
            return []

        # Split into sections based on headings
        matches = list(self.HEADING_REGEX.finditer(markdown_text))
        if not matches:
            # Fall back to recursive text splitting if no headings are found
            meta = dict(base_metadata)
            meta["doc_type"] = "markdown"
            return self.text_parser.chunk_text(markdown_text, meta)

        sections: List[Dict[str, Any]] = []
        heading_stack: List[str] = []

        # Preamble before first heading
        if matches[0].start() > 0:
            preamble = markdown_text[: matches[0].start()].strip()
            if preamble:
                sections.append({"header": "Overview", "content": preamble})

        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
            content = markdown_text[start:end].strip()

            # Maintain breadcrumb stack
            while len(heading_stack) >= level:
                heading_stack.pop()
            heading_stack.append(title)
            breadcrumb = " > ".join(heading_stack)

            if content:
                sections.append({"header": breadcrumb, "content": content})

        results = []
        chunk_idx = 0
        for sec in sections:
            header_prefix = f"[{sec['header']}]\n"
            full_section_text = f"{header_prefix}{sec['content']}"

            if len(full_section_text) <= self.chunk_size:
                meta = dict(base_metadata)
                meta["chunk_index"] = chunk_idx
                meta["doc_type"] = "markdown"
                meta["section_header"] = sec["header"][:120]
                meta["is_mcq"] = False
                results.append({
                    "text": full_section_text,
                    "metadata": meta,
                })
                chunk_idx += 1
            else:
                # Sub-split long section
                sub_meta = dict(base_metadata)
                sub_meta["section_header"] = sec["header"][:120]
                sub_chunks = self.text_parser.chunk_text(sec["content"], sub_meta)
                for sc in sub_chunks:
                    sc["text"] = f"{header_prefix}{sc['text']}"
                    sc["metadata"]["chunk_index"] = chunk_idx
                    sc["metadata"]["doc_type"] = "markdown"
                    results.append(sc)
                    chunk_idx += 1

        return results
