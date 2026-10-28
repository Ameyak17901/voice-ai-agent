"""
ChromaDB Vector Store wrapper with strict multi-tenant isolation.
Supports partitioned collections, metadata filtering by user_id and persona_id,
and cosine similarity matching.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _CHROMA_AVAILABLE = True
    _CHROMA_ERROR = None
except ImportError as _err:
    chromadb = None
    ChromaSettings = None
    _CHROMA_AVAILABLE = False
    _CHROMA_ERROR = str(_err)

from loguru import logger
from backend.config import settings


class ChromaVectorStore:
    """Multi-tenant vector storage engine backed by ChromaDB."""

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: str = "voice_ai_knowledge",
    ):
        base_dir = persist_dir or getattr(settings, "chroma_persist_directory", "backend/data/chroma")
        self.persist_dir = Path(base_dir).resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name

        self.is_available = _CHROMA_AVAILABLE
        self._client = None
        self._collection = None

        if not _CHROMA_AVAILABLE:
            logger.warning(
                f"[CHROMA] chromadb is not installed or unavailable: {_CHROMA_ERROR}. "
                "RAG vector storage will operate in graceful fallback mode without crashing server."
            )
            return

        try:
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"[CHROMA] Initialized PersistentClient at '{self.persist_dir}', collection: '{collection_name}'")
        except Exception as exc:
            logger.error(f"[CHROMA] Failed to initialize ChromaDB PersistentClient: {exc}")
            self.is_available = False
            self._client = None
            self._collection = None

    def _build_where_filter(
        self,
        user_id: Optional[int] = None,
        persona_id: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Constructs safe ChromaDB metadata filter conditions."""
        clauses = []
        if user_id is not None:
            clauses.append({"user_id": {"$eq": int(user_id)}})
        if persona_id:
            clauses.append({"persona_id": {"$eq": str(persona_id)}})
        if document_id:
            clauses.append({"document_id": {"$eq": str(document_id)}})

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def add_chunks(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> int:
        """
        Inserts or updates document chunks in ChromaDB.
        Sanitizes metadatas to ensure only primitive types (str, int, float, bool) are stored.
        """
        if not getattr(self, "is_available", True) or self._collection is None:
            logger.warning("[CHROMA] Vector store unavailable. Skipping chunk addition.")
            return 0
        if not ids:
            return 0

        clean_metadatas = []
        for m in metadatas:
            clean_m = {}
            for k, v in m.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_m[k] = v
                elif v is None:
                    clean_m[k] = ""
                else:
                    clean_m[k] = str(v)
            clean_metadatas.append(clean_m)

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=clean_metadatas,
        )
        logger.info(f"[CHROMA] Upserted {len(ids)} chunks into collection '{self.collection_name}'")
        return len(ids)

    def query(
        self,
        query_embedding: List[float],
        user_id: Optional[int] = None,
        persona_id: Optional[str] = None,
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic similarity search with tenant filtering and distance thresholding.
        Returns ordered list of matches with content, metadata, and score.
        """
        if not getattr(self, "is_available", True) or self._collection is None:
            logger.warning("[CHROMA] Vector store unavailable. Skipping query.")
            return []

        where_filter = self._build_where_filter(user_id=user_id, persona_id=persona_id)

        count = self._collection.count()
        if count == 0:
            return []

        n_results = min(top_k, count)

        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where_filter:
            query_params["where"] = where_filter

        try:
            results = self._collection.query(**query_params)
        except Exception as exc:
            logger.error(f"[CHROMA] Query execution error: {exc}")
            return []

        matched_chunks = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        for chunk_id, text, meta, dist in zip(ids, docs, metas, distances):
            # Chroma with cosine distance: distance = 1 - similarity
            similarity = 1.0 - float(dist)
            if similarity >= threshold:
                matched_chunks.append({
                    "id": chunk_id,
                    "text": text,
                    "metadata": meta,
                    "similarity": round(similarity, 4),
                    "distance": round(float(dist), 4),
                })

        # Rank by highest similarity first
        matched_chunks.sort(key=lambda x: x["similarity"], reverse=True)
        return matched_chunks

    def delete_document(self, document_id: str, user_id: Optional[int] = None) -> int:
        """Deletes all chunks associated with a specific document ID."""
        if not getattr(self, "is_available", True) or self._collection is None:
            logger.warning("[CHROMA] Vector store unavailable. Skipping document deletion.")
            return 0

        where_filter = self._build_where_filter(user_id=user_id, document_id=document_id)
        if not where_filter:
            return 0

        existing = self._collection.get(where=where_filter, include=["metadatas"])
        ids_to_delete = existing.get("ids", [])
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
            logger.info(f"[CHROMA] Deleted {len(ids_to_delete)} chunks for document '{document_id}'")
            return len(ids_to_delete)
        return 0

    def list_documents(
        self,
        user_id: Optional[int] = None,
        persona_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists ingested documents and their chunk counts filtered by user and persona."""
        if not getattr(self, "is_available", True) or self._collection is None:
            logger.warning("[CHROMA] Vector store unavailable. Skipping list documents.")
            return []

        where_filter = self._build_where_filter(user_id=user_id, persona_id=persona_id)
        get_params = {"include": ["metadatas"]}
        if where_filter:
            get_params["where"] = where_filter

        records = self._collection.get(**get_params)
        metadatas = records.get("metadatas", [])

        docs_map: Dict[str, Dict[str, Any]] = {}
        for m in metadatas:
            doc_id = m.get("document_id")
            if not doc_id:
                continue
            if doc_id not in docs_map:
                docs_map[doc_id] = {
                    "document_id": doc_id,
                    "title": m.get("document_title", doc_id),
                    "doc_type": m.get("doc_type", "unknown"),
                    "persona_id": m.get("persona_id", ""),
                    "user_id": m.get("user_id"),
                    "created_at": m.get("created_at"),
                    "chunk_count": 0,
                    "is_mcq": m.get("is_mcq", False),
                }
            docs_map[doc_id]["chunk_count"] += 1

        return list(docs_map.values())

    def reset_collection(self) -> None:
        """Empties collection (used for test isolation)."""
        if not getattr(self, "is_available", True) or self._client is None:
            return
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )


chroma_vector_store = ChromaVectorStore()
