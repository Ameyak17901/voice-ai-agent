"""
Recursive character text parser and chunker for plain text.
Splits text on natural semantic boundaries (paragraphs, sentences, words)
with configurable window size and overlap.
"""
from typing import List, Dict, Any


class TextParser:
    """Chunks plain text documents recursively."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 60):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

    def chunk_text(self, text: str, base_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Splits raw text into overlapping chunks, attaching metadata."""
        if not text or not text.strip():
            return []

        raw_chunks = self._recursive_split(text.strip(), self.separators)
        results = []

        for idx, chunk_str in enumerate(raw_chunks):
            chunk_cleaned = chunk_str.strip()
            if not chunk_cleaned:
                continue

            meta = dict(base_metadata)
            meta["chunk_index"] = idx
            meta["doc_type"] = "text"
            meta["is_mcq"] = False

            results.append({
                "text": chunk_cleaned,
                "metadata": meta,
            })

        return results

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        """Splits text recursively using the first matching separator."""
        final_chunks: List[str] = []

        # Find best separator
        separator = separators[-1]
        new_separators = []
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator else list(text)

        current_doc: List[str] = []
        current_len = 0

        for s in splits:
            s_len = len(s)
            if current_len + s_len + len(separator) > self.chunk_size:
                if current_doc:
                    doc_str = separator.join(current_doc)
                    if len(doc_str) > self.chunk_size and new_separators:
                        final_chunks.extend(self._recursive_split(doc_str, new_separators))
                    else:
                        final_chunks.append(doc_str)

                    # Overlap handling: retain end of current_doc for overlap
                    overlap_docs = []
                    overlap_len = 0
                    for prev_s in reversed(current_doc):
                        if overlap_len + len(prev_s) <= self.chunk_overlap:
                            overlap_docs.insert(0, prev_s)
                            overlap_len += len(prev_s)
                        else:
                            break
                    current_doc = overlap_docs
                    current_len = overlap_len

                current_doc.append(s)
                current_len += s_len
            else:
                current_doc.append(s)
                current_len += s_len + len(separator)

        if current_doc:
            doc_str = separator.join(current_doc)
            if len(doc_str) > self.chunk_size and new_separators:
                final_chunks.extend(self._recursive_split(doc_str, new_separators))
            else:
                final_chunks.append(doc_str)

        return [c for c in final_chunks if c.strip()]
