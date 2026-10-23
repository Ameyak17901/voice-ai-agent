"""
MCQ (Multiple Choice Question) Parser.
Ensures Question, Options, Correct Answer, and Explanation are preserved
as an indivisible atomic chunk to prevent LLM hallucinations during voice calls.
"""
import re
from typing import Any, Dict, List, Union


class MCQParser:
    """Parses raw text or structured collections of Multiple Choice Questions."""

    # Matches question starts like "Q: ...", "Q1: ...", "Question 1: ...", "1. ..."
    QUESTION_PATTERN = re.compile(
        r"(?:^|\n)(?:Q(?:uestion)?\s*(?:\d+)?[:.]|\b\d+[\.\)])\s+",
        re.IGNORECASE,
    )

    def parse_mcq_text(self, text: str, base_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parses unformatted or delimited MCQ text into atomic chunks.
        Splits by question stems, preserving options and answers together.
        """
        if not text or not text.strip():
            return []

        # Find all question match positions
        matches = list(self.QUESTION_PATTERN.finditer(text))
        if not matches:
            # If no standard prefixes, check if double-newline separated
            blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        else:
            blocks = []
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                blocks.append(text[start:end].strip())

        results = []
        for idx, block in enumerate(blocks):
            if not block:
                continue

            # Extract question, options, answer if identifiable
            extracted = self._extract_mcq_fields(block)

            meta = dict(base_metadata)
            meta["chunk_index"] = idx
            meta["doc_type"] = "mcq"
            meta["is_mcq"] = True
            if extracted.get("question"):
                meta["mcq_question"] = extracted["question"][:150]
            if extracted.get("answer"):
                meta["mcq_answer"] = extracted["answer"][:100]

            results.append({
                "text": block,
                "metadata": meta,
            })

        return results

    def parse_mcq_items(
        self,
        items: List[Dict[str, Any]],
        base_metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Parses structured list of MCQ dicts:
        [{'question': '...', 'options': ['A) ...', 'B) ...'], 'answer': 'A', 'explanation': '...'}]
        """
        results = []
        for idx, item in enumerate(items):
            q = item.get("question", "").strip()
            opts = item.get("options", [])
            ans = item.get("answer", "").strip()
            exp = item.get("explanation", "").strip()

            lines = [f"Question: {q}"]
            if isinstance(opts, list):
                for opt in opts:
                    lines.append(f"  {opt}")
            elif isinstance(opts, dict):
                for k, v in opts.items():
                    lines.append(f"  {k}: {v}")

            if ans:
                lines.append(f"Correct Answer: {ans}")
            if exp:
                lines.append(f"Explanation: {exp}")

            chunk_text = "\n".join(lines)
            meta = dict(base_metadata)
            meta["chunk_index"] = idx
            meta["doc_type"] = "mcq"
            meta["is_mcq"] = True
            meta["mcq_question"] = q[:150]
            if ans:
                meta["mcq_answer"] = ans[:100]

            results.append({
                "text": chunk_text,
                "metadata": meta,
            })

        return results

    def _extract_mcq_fields(self, block: str) -> Dict[str, str]:
        """Heuristic extractor for question stem and answer label."""
        fields: Dict[str, str] = {}
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if lines:
            fields["question"] = lines[0]

        for line in lines:
            ans_match = re.search(r"(?:answer|ans|correct)\s*[:=-]\s*([^\n]+)", line, re.IGNORECASE)
            if ans_match:
                fields["answer"] = ans_match.group(1).strip()
                break

        return fields
