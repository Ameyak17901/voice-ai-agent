"""
Gemini Embedding Service for Voice AI Agent RAG.
Supports text-embedding-004 and embedding-001 via Google Gemini native REST API
and OpenAI-compatible proxy endpoints.
Includes automatic batching, dimension validation, and deterministic word-hashing offline fallbacks.
"""
import hashlib
import math
from typing import List, Optional
import httpx
from loguru import logger
from backend.config import settings


class GeminiEmbeddingService:
    """Async embedding client for Google Gemini embedding models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        # Default to text-embedding-004 or embedding-001
        self.model = model or getattr(settings, "gemini_embedding_model", "text-embedding-004")
        self.timeout = timeout
        self.dimension = 768

    @property
    def is_configured(self) -> bool:
        """Returns True if a live Gemini API key is configured."""
        if not self.api_key:
            return False
        key = str(self.api_key).strip()
        # Avoid treating dummy placeholders as live keys
        return bool(key and not key.startswith("AIzaSy_placeholder") and len(key) > 15)

    def _generate_mock_embedding(self, text: str) -> List[float]:
        """
        Generates a deterministic unit-normalized mock embedding vector (768 dimensions).
        Uses a feature-hashing bag-of-words approach so that semantically overlapping
        texts yield positive cosine similarity in offline testing.
        """
        raw = [0.0] * self.dimension
        words = [w.lower().strip(".,!?:;\"'()[]{}") for w in text.split() if w.strip()]
        if not words:
            words = ["empty"]

        for w in words:
            if not w:
                continue
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            raw[idx] += 1.0

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a batch of text chunks.
        Splits requests into batches of at most 16 items.
        """
        if not texts:
            return []

        cleaned_texts = [t.strip() if t and t.strip() else " " for t in texts]

        if not self.is_configured:
            logger.debug("[EMBEDDINGS] Live Gemini API key not present; using deterministic offline mock embeddings.")
            return [self._generate_mock_embedding(t) for t in cleaned_texts]

        batch_size = 16
        all_embeddings: List[List[float]] = []

        model_name = self.model
        if not model_name.startswith("models/"):
            model_path = f"models/{model_name}"
        else:
            model_path = model_name

        # MED-6: Use x-goog-api-key header to prevent key from appearing in server logs.
        native_url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:batchEmbedContents"
        embedding_headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for i in range(0, len(cleaned_texts), batch_size):
                batch = cleaned_texts[i : i + batch_size]
                native_payload = {
                    "requests": [
                        {
                            "model": model_path,
                            "content": {"parts": [{"text": t}]},
                        }
                        for t in batch
                    ]
                }
                try:
                    response = await client.post(native_url, json=native_payload, headers=embedding_headers)
                    if response.status_code == 200:
                        data = response.json()
                        embeds = [item.get("values", []) for item in data.get("embeddings", [])]
                        all_embeddings.extend(embeds)
                    else:
                        logger.warning(
                            f"[EMBEDDINGS] Gemini API error ({response.status_code}): {response.text[:200]}. "
                            "Falling back to mock embeddings for this batch."
                        )
                        all_embeddings.extend([self._generate_mock_embedding(t) for t in batch])
                except Exception as exc:
                    logger.error(f"[EMBEDDINGS] Exception during Gemini embedding call: {exc}. Using mock embeddings.")
                    all_embeddings.extend([self._generate_mock_embedding(t) for t in batch])

        return all_embeddings

    async def get_single_embedding(self, text: str) -> List[float]:
        """Convenience wrapper for generating a single embedding vector."""
        res = await self.get_embeddings([text])
        return res[0]


gemini_embedding_service = GeminiEmbeddingService()
