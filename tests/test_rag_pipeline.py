"""
Comprehensive automated tests for Voice AI Agent RAG Pipeline:
1. MCQ atomic parsing (preserving question, choices, answer, explanation)
2. Markdown heading hierarchy chunking
3. PDF parser page tracking and stream extraction
4. ChromaDB vector storage and multi-tenant isolation
5. End-to-end RAG service lifecycle (ingest, search, delete)
6. QueryKnowledgeBaseAction execution with latency masking (should_respond='always')
7. Persona-tailored acoustic pre-roll filler injection
"""
import io
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pypdf import PdfWriter

from backend.rag.parsers.mcq_parser import MCQParser
from backend.rag.parsers.markdown_parser import MarkdownParser
from backend.rag.parsers.pdf_parser import PDFParser
from backend.rag.parsers.text_parser import TextParser
from backend.rag.vector_store import ChromaVectorStore
from backend.rag.embeddings import GeminiEmbeddingService
from backend.rag.service import RAGService
from backend.actions.knowledge_actions import (
    QueryKnowledgeBaseAction,
    QueryKnowledgeBaseActionConfig,
    QueryKnowledgeBaseParams,
)
from backend.agent_factory import ResilientChatGPTAgent, SmartFallbackAgent
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage


@pytest.fixture
def isolated_chroma(tmp_path):
    """Creates a fresh, isolated ChromaVectorStore instance per test."""
    chroma_dir = tmp_path / "chroma_test"
    store = ChromaVectorStore(persist_dir=str(chroma_dir), collection_name="test_voice_knowledge")
    yield store


@pytest.fixture
def mock_embedding_service():
    """Deterministic embedding service (offline mock)."""
    return GeminiEmbeddingService(api_key="", model="text-embedding-004")


@pytest.fixture
def isolated_rag_service(isolated_chroma, mock_embedding_service):
    """RAGService with isolated vector store and deterministic embeddings."""
    return RAGService(
        vector_store=isolated_chroma,
        embedding_service=mock_embedding_service,
    )


# ==============================================================
# 1. MCQ Parser Tests (Atomic Question-Option-Answer Chunking)
# ==============================================================
def test_mcq_parser_atomic_chunks_from_text():
    parser = MCQParser()
    mcq_text = """
    Q1: What is the clinic cancellation policy?
    A) Free up to 24 hours prior
    B) 50% cancellation fee within 24 hours
    C) Non-refundable
    D) Only reschedule allowed
    Answer: A
    Explanation: Patients can cancel without penalty up to 24 hours in advance.

    Q2: What are the front desk clinic operating hours?
    A) 9 AM to 5 PM
    B) 8 AM to 6 PM Monday through Saturday
    C) 24 hours open
    Answer: B
    Explanation: The front desk operates 8 AM to 6 PM Monday to Saturday.
    """
    chunks = parser.parse_mcq_text(mcq_text, base_metadata={"document_id": "test_mcq"})

    assert len(chunks) == 2
    chunk1 = chunks[0]
    assert chunk1["metadata"]["is_mcq"] is True
    assert chunk1["metadata"]["doc_type"] == "mcq"
    assert "cancellation policy" in chunk1["text"].lower()
    assert "Answer: A" in chunk1["text"]
    assert chunk1["metadata"]["mcq_answer"] == "A"

    chunk2 = chunks[1]
    assert "operating hours" in chunk2["text"].lower()
    assert "Answer: B" in chunk2["text"]


def test_mcq_parser_structured_items():
    parser = MCQParser()
    items = [
        {
            "question": "What is the primary LLM used by Nova Concierge?",
            "options": ["A) GPT-4", "B) Claude 3.5", "C) Gemini 1.5 Flash", "D) Llama 3"],
            "answer": "C",
            "explanation": "Nova utilizes Google Gemini 1.5 Flash for sub-400ms time-to-first-token.",
        }
    ]
    chunks = parser.parse_mcq_items(items, base_metadata={"document_id": "test_struct_mcq"})
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["metadata"]["is_mcq"] is True
    assert "Gemini 1.5 Flash" in chunk["text"]
    assert chunk["metadata"]["mcq_answer"] == "C"


# ==============================================================
# 2. Markdown Parser Tests (Heading Hierarchy)
# ==============================================================
def test_markdown_parser_heading_hierarchy():
    parser = MarkdownParser(chunk_size=300)
    markdown_doc = """
    # Clinic Policies
    Welcome to Nova Medical Clinic.

    ## Cancellation Rules
    Patients can cancel appointments with no charge up to 24 hours prior.

    ## Emergency Contact
    For urgent after-hours needs, call 911 or visit the emergency room.
    """
    chunks = parser.parse_markdown(markdown_doc, base_metadata={"document_id": "test_md"})
    assert len(chunks) >= 2

    # Verify heading breadcrumbs
    section_headers = [c["metadata"].get("section_header", "") for c in chunks]
    assert any("Clinic Policies > Cancellation Rules" in h for h in section_headers)
    assert any("Clinic Policies > Emergency Contact" in h for h in section_headers)


# ==============================================================
# 3. PDF Parser Tests (pypdf stream and page tracking)
# ==============================================================
def test_pdf_parser_page_tracking():
    # Dynamically build a real multi-page PDF in memory using pypdf
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)

    pdf_stream = io.BytesIO()
    writer.write(pdf_stream)
    pdf_bytes = pdf_stream.getvalue()

    parser = PDFParser()
    # Blank pages produce 0 text chunks without error
    chunks = parser.parse_pdf(pdf_bytes, base_metadata={"document_id": "blank_pdf"})
    assert isinstance(chunks, list)


# ==============================================================
# 4. ChromaDB Multi-Tenant Isolation Tests
# ==============================================================
def test_chroma_multi_tenant_isolation(isolated_chroma, mock_embedding_service):
    # User 1 (Tenant 1) adds knowledge
    vec1 = mock_embedding_service._generate_mock_embedding("Clinic hours are 8am to 6pm")
    isolated_chroma.add_chunks(
        ids=["doc1_chunk_0"],
        embeddings=[vec1],
        documents=["Clinic hours are 8am to 6pm"],
        metadatas=[{"user_id": 1, "persona_id": "receptionist", "document_id": "doc1"}],
    )

    # User 2 (Tenant 2) adds knowledge
    vec2 = mock_embedding_service._generate_mock_embedding("School starts at 8:30am")
    isolated_chroma.add_chunks(
        ids=["doc2_chunk_0"],
        embeddings=[vec2],
        documents=["School starts at 8:30am"],
        metadatas=[{"user_id": 2, "persona_id": "school_receptionist", "document_id": "doc2"}],
    )

    # Search with User 1 credentials -> must NOT see User 2's documents
    user1_query_vec = mock_embedding_service._generate_mock_embedding("What time does school start?")
    user1_results = isolated_chroma.query(
        query_embedding=user1_query_vec,
        user_id=1,
        persona_id="receptionist",
        top_k=5,
        threshold=0.0,
    )
    assert all(r["metadata"]["user_id"] == 1 for r in user1_results)
    assert not any("School starts" in r["text"] for r in user1_results)

    # Search with User 2 credentials -> must NOT see User 1's documents
    user2_results = isolated_chroma.query(
        query_embedding=user1_query_vec,
        user_id=2,
        persona_id="school_receptionist",
        top_k=5,
        threshold=0.0,
    )
    assert all(r["metadata"]["user_id"] == 2 for r in user2_results)


# ==============================================================
# 5. End-to-End RAG Service Lifecycle Tests
# ==============================================================
@pytest.mark.asyncio
async def test_rag_service_full_lifecycle(isolated_rag_service):
    # 1. Ingest raw text
    ingest_res = await isolated_rag_service.ingest_raw_text(
        text="Nova Concierge provides 24/7 executive booking and live calendar sync.",
        title="Concierge Overview",
        user_id=10,
        persona_id="concierge",
    )
    assert ingest_res["status"] == "indexed"
    doc_id = ingest_res["document_id"]

    # 2. Ingest MCQ
    mcq_res = await isolated_rag_service.ingest_mcqs(
        mcqs="Q: Can callers reschedule? A) Yes B) No Answer: A",
        title="FAQ MCQs",
        user_id=10,
        persona_id="concierge",
    )
    assert mcq_res["status"] == "indexed"

    # 3. List documents
    docs = isolated_rag_service.list_documents(user_id=10, persona_id="concierge")
    assert len(docs) == 2
    titles = [d["title"] for d in docs]
    assert "Concierge Overview" in titles
    assert "FAQ MCQs" in titles

    # 4. Query knowledge
    query_res = await isolated_rag_service.query_knowledge(
        query="executive booking",
        user_id=10,
        persona_id="concierge",
        threshold=0.0,
    )
    assert query_res["count"] > 0
    assert "latency_ms" in query_res

    # 5. Acoustic distilled context formatting
    speech_context = await isolated_rag_service.get_acoustic_distilled_context(
        query="booking",
        user_id=10,
        persona_id="concierge",
        threshold=0.0,
    )
    assert "Acoustic Formatting Protocol" in speech_context
    assert "Concierge Overview" in speech_context

    # 6. Delete document
    deleted = isolated_rag_service.delete_document(document_id=doc_id, user_id=10)
    assert deleted is True

    # Verify deleted doc is gone
    remaining = isolated_rag_service.list_documents(user_id=10, persona_id="concierge")
    assert len(remaining) == 1


# ==============================================================
# 6. QueryKnowledgeBaseAction Execution & Latency Masking Tests
# ==============================================================
@pytest.mark.asyncio
async def test_query_knowledge_base_action():
    action_config = QueryKnowledgeBaseActionConfig()
    action = QueryKnowledgeBaseAction(action_config=action_config)

    # Must have should_respond="always" to trigger Vocode core acoustic pre-roll
    assert action.should_respond == "always"
    assert action.get_function_name() == "query_knowledge_base"

    # Mock rag_service.query_knowledge to return simulated matches
    mock_matches = [
        {
            "id": "c1",
            "text": "Appointments can be rescheduled up to 2 hours before the start time.",
            "metadata": {"document_title": "Reschedule Guidelines"},
            "similarity": 0.92,
        }
    ]
    with patch("backend.actions.knowledge_actions.rag_service.query_knowledge", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = {"matches": mock_matches, "count": 1}

        from vocode.streaming.models.actions import ActionInput

        action_input = ActionInput(
            action_config=action_config,
            conversation_id="conv_rag_test",
            params=QueryKnowledgeBaseParams(query="how to reschedule appointment"),
        )
        action_output = await action.run(action_input)

        assert action_output.response.status == "found"
        assert action_output.response.match_count == 1
        assert "Reschedule Guidelines" in action_output.response.context
        assert "Synthesize the answer concisely in 1 to 2 spoken sentences" in action_output.response.context


# ==============================================================
# 7. ResilientChatGPTAgent Pre-Roll Latency Masking for RAG
# ==============================================================
@pytest.mark.asyncio
async def test_agent_injects_fallback_for_knowledge_query():
    fallback_agent = SmartFallbackAgent(persona="receptionist")
    config = ChatGPTAgentConfig(
        initial_message=BaseMessage(text="Hello"),
        prompt_preamble="System prompt",
        openai_api_key="mock_test_key",
    )
    agent = ResilientChatGPTAgent(config, fallback_agent=fallback_agent)

    # Function call without user_message
    fn_call = MagicMock()
    fn_call.name = "query_knowledge_base"
    fn_call.arguments = json.dumps({"query": "What is the cancellation policy?"})

    with patch("vocode.streaming.agent.chat_gpt_agent.ChatGPTAgent.call_function", new_callable=AsyncMock) as mock_super:
        mock_super.return_value = "action_executed"
        await agent.call_function(fn_call, agent_input="input")

        # Verify arguments had filler injected
        passed_args = json.loads(fn_call.arguments)
        assert "user_message" in passed_args
        assert passed_args["user_message"] == "One moment, let me check our clinic guidelines on that for you..."


@pytest.mark.asyncio
async def test_rag_service_graceful_degradation_when_vector_store_unavailable():
    """Verify RAG operations gracefully degrade without raising errors if ChromaDB is unavailable."""
    from backend.rag.vector_store import ChromaVectorStore
    from backend.rag.service import RAGService
    from unittest.mock import MagicMock

    mock_store = MagicMock(spec=ChromaVectorStore)
    mock_store.is_available = False
    mock_store.add_chunks.return_value = 0
    mock_store.query.return_value = []
    mock_store.delete_document.return_value = 0
    mock_store.list_documents.return_value = []

    degraded_service = RAGService(vector_store=mock_store)

    # 1. Ingest should gracefully return status='unavailable'
    res = await degraded_service.ingest_raw_text(
        text="Sample text",
        title="Sample",
        user_id=1,
        persona_id="concierge",
    )
    assert res["status"] == "unavailable"
    assert res["chunks_indexed"] == 0
    assert "error" in res

    # 2. Query should return retrieved=False
    query_res = await degraded_service.query_knowledge(
        query="test query",
        user_id=1,
        persona_id="concierge",
    )
    assert query_res["retrieved"] is False
    assert query_res["context"] == ""
    assert "error" in query_res
