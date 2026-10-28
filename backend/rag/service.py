"""
RAG Service Orchestrator for Voice AI Agent.
Coordinates document parsing, chunking, Gemini embeddings, and ChromaDB vector persistence.
Provides speech-distilled context retrieval for real-time voice calls.
"""
import time
import uuid
from typing import Any, Dict, List, Optional, Union
from loguru import logger

from backend.config import settings
from .embeddings import gemini_embedding_service, GeminiEmbeddingService
from .vector_store import chroma_vector_store, ChromaVectorStore
from .parsers import TextParser, MCQParser, MarkdownParser, PDFParser


class RAGService:
    """Core RAG service coordinating parsing, indexing, and speech-optimized retrieval."""

    def __init__(
        self,
        vector_store: Optional[ChromaVectorStore] = None,
        embedding_service: Optional[GeminiEmbeddingService] = None,
    ):
        self.vector_store = vector_store or chroma_vector_store
        self.embedding_service = embedding_service or gemini_embedding_service

        chunk_size = getattr(settings, "rag_chunk_size", 500)
        chunk_overlap = getattr(settings, "rag_chunk_overlap", 60)

        self.text_parser = TextParser(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.mcq_parser = MCQParser()
        self.markdown_parser = MarkdownParser(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.pdf_parser = PDFParser(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    async def ingest_raw_text(
        self,
        text: str,
        title: str,
        user_id: int,
        persona_id: str,
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingests plain text document."""
        document_id = doc_id or f"doc_{uuid.uuid4().hex[:12]}"
        base_meta = {
            "document_id": document_id,
            "document_title": title,
            "user_id": int(user_id),
            "persona_id": str(persona_id),
            "created_at": time.time(),
        }
        chunks = self.text_parser.chunk_text(text, base_meta)
        return await self._index_chunks(document_id, title, chunks)

    async def ingest_mcqs(
        self,
        mcqs: Union[str, List[Dict[str, Any]]],
        title: str,
        user_id: int,
        persona_id: str,
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingests MCQs either from raw formatted text or structured dicts."""
        document_id = doc_id or f"mcq_{uuid.uuid4().hex[:12]}"
        base_meta = {
            "document_id": document_id,
            "document_title": title,
            "user_id": int(user_id),
            "persona_id": str(persona_id),
            "created_at": time.time(),
        }
        if isinstance(mcqs, str):
            chunks = self.mcq_parser.parse_mcq_text(mcqs, base_meta)
        else:
            chunks = self.mcq_parser.parse_mcq_items(mcqs, base_meta)

        return await self._index_chunks(document_id, title, chunks)

    async def ingest_markdown(
        self,
        markdown_text: str,
        title: str,
        user_id: int,
        persona_id: str,
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingests Markdown text with heading hierarchy preservation."""
        document_id = doc_id or f"md_{uuid.uuid4().hex[:12]}"
        base_meta = {
            "document_id": document_id,
            "document_title": title,
            "user_id": int(user_id),
            "persona_id": str(persona_id),
            "created_at": time.time(),
        }
        chunks = self.markdown_parser.parse_markdown(markdown_text, base_meta)
        return await self._index_chunks(document_id, title, chunks)

    async def ingest_pdf(
        self,
        pdf_source: Union[str, bytes],
        title: str,
        user_id: int,
        persona_id: str,
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingests PDF file or raw bytes."""
        document_id = doc_id or f"pdf_{uuid.uuid4().hex[:12]}"
        base_meta = {
            "document_id": document_id,
            "document_title": title,
            "user_id": int(user_id),
            "persona_id": str(persona_id),
            "created_at": time.time(),
        }
        chunks = self.pdf_parser.parse_pdf(pdf_source, base_meta)
        return await self._index_chunks(document_id, title, chunks)

    async def _index_chunks(
        self,
        document_id: str,
        title: str,
        chunks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generates embeddings and saves chunks into ChromaDB."""
        if not chunks:
            return {
                "document_id": document_id,
                "title": title,
                "chunks_indexed": 0,
                "status": "empty",
            }

        texts = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]
        ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]

        # Generate embeddings via Gemini / mock fallback
        embeddings = await self.embedding_service.get_embeddings(texts)

        # Check if vector store engine is available
        if hasattr(self.vector_store, "is_available") and not self.vector_store.is_available:
            logger.warning("[RAG_SERVICE] Vector store engine is unavailable. Bypassing storage.")
            return {
                "document_id": document_id,
                "title": title,
                "chunks_indexed": 0,
                "status": "unavailable",
                "error": "ChromaDB vector store engine is not installed or available.",
            }

        # Upsert into ChromaDB
        indexed_count = self.vector_store.add_chunks(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        return {
            "document_id": document_id,
            "title": title,
            "chunks_indexed": indexed_count,
            "status": "indexed",
        }

    async def query_knowledge(
        self,
        query: str,
        user_id: Optional[int] = None,
        persona_id: Optional[str] = None,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Executes semantic search against ChromaDB using Gemini embedding for query.
        Returns matched chunks filtered by user_id and persona_id.
        """
        if hasattr(self.vector_store, "is_available") and not self.vector_store.is_available:
            logger.warning("[RAG_SERVICE] Vector store engine is unavailable for querying.")
            return {
                "query": query,
                "matched_chunks": [],
                "context": "",
                "retrieved": False,
                "error": "ChromaDB vector store engine is not installed or available.",
            }

        k = top_k if top_k is not None else getattr(settings, "rag_max_retrieval_chunks", 3)
        thresh = threshold if threshold is not None else getattr(settings, "rag_similarity_threshold", 0.5)

        start_time = time.time()
        query_embedding = await self.embedding_service.get_single_embedding(query)
        matches = self.vector_store.query(
            query_embedding=query_embedding,
            user_id=user_id,
            persona_id=persona_id,
            top_k=k,
            threshold=thresh,
        )
        latency_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "query": query,
            "matches": matches,
            "count": len(matches),
            "latency_ms": latency_ms,
        }

    async def get_acoustic_distilled_context(
        self,
        query: str,
        user_id: Optional[int] = None,
        persona_id: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> str:
        """
        Retrieves knowledge context formatted specifically for spoken voice responses.
        Advises the LLM to synthesize the retrieved knowledge into 1-2 spoken sentences
        without bullet points, URLs, or markdown citations.
        """
        search_res = await self.query_knowledge(
            query=query,
            user_id=user_id,
            persona_id=persona_id,
            threshold=threshold,
        )
        matches = search_res.get("matches", [])

        if not matches:
            return "No specific internal knowledge document matched this inquiry."

        context_snippets = []
        for i, m in enumerate(matches, 1):
            title = m.get("metadata", {}).get("document_title", "Document")
            text = m.get("text", "").strip()
            context_snippets.append(f"[Snippet {i} from {title}]:\n{text}")

        joined_context = "\n\n".join(context_snippets)

        return (
            f"Retrieved Company / Persona Knowledge:\n{joined_context}\n\n"
            "Acoustic Formatting Protocol:\n"
            "- Synthesize the above information into 1 to 2 spoken sentences maximum.\n"
            "- Do NOT mention citation brackets, document titles, bullet points, or URLs.\n"
            "- Speak naturally and directly to the caller."
        )

    def list_documents(
        self,
        user_id: Optional[int] = None,
        persona_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists all ingested documents with chunk counts."""
        return self.vector_store.list_documents(user_id=user_id, persona_id=persona_id)

    def delete_document(self, document_id: str, user_id: Optional[int] = None) -> bool:
        """Removes a document and its vector embeddings."""
        deleted = self.vector_store.delete_document(document_id, user_id=user_id)
        return deleted > 0


rag_service = RAGService()
