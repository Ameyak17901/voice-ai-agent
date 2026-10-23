"""
Real-time Voice RAG Knowledge Base Action for Voice AI Agent.
Retrieves semantic knowledge from ChromaDB with zero-dead-air latency masking.
"""
from typing import Optional, Type
from loguru import logger
from pydantic.v1 import BaseModel, Field

from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.models.actions import ActionConfig, ActionInput, ActionOutput
from backend.rag.service import rag_service


class QueryKnowledgeBaseActionConfig(ActionConfig, type="query_knowledge_base"):  # type: ignore
    pass


class QueryKnowledgeBaseParams(BaseModel):
    query: str = Field(
        ...,
        description="The caller's specific question, topic, or inquiry to search in the knowledge base.",
    )


class QueryKnowledgeBaseResponse(BaseModel):
    status: str
    query: str
    context: str
    match_count: int


class QueryKnowledgeBaseAction(
    BaseAction[
        QueryKnowledgeBaseActionConfig,
        QueryKnowledgeBaseParams,
        QueryKnowledgeBaseResponse,
    ]
):
    """
    Action that retrieves relevant company/clinic/school knowledge chunks from ChromaDB.
    Configured with should_respond='always' to guarantee acoustic latency masking
    while the vector search and embedding execution run asynchronously.
    """
    description: str = (
        "Searches the internal knowledge base for company policies, hours, clinic procedures, "
        "school guidelines, FAQs, or technical documentation."
    )
    parameters_type: Type[QueryKnowledgeBaseParams] = QueryKnowledgeBaseParams
    response_type: Type[QueryKnowledgeBaseResponse] = QueryKnowledgeBaseResponse

    def __init__(self, action_config: QueryKnowledgeBaseActionConfig):
        super().__init__(
            action_config=action_config,
            quiet=False,
            should_respond="always",
            is_interruptible=True,
        )

    def get_function_name(self) -> str:
        return "query_knowledge_base"

    async def run(
        self, action_input: ActionInput[QueryKnowledgeBaseParams]
    ) -> ActionOutput[QueryKnowledgeBaseResponse]:
        query_text = action_input.params.query
        logger.info(f"[VOICE_ACTION: QUERY_KNOWLEDGE_BASE] Executing search for: '{query_text}'")

        try:
            search_result = await rag_service.query_knowledge(
                query=query_text,
            )
            matches = search_result.get("matches", [])
            match_count = len(matches)

            if match_count > 0:
                snippets = []
                for idx, m in enumerate(matches, 1):
                    doc_title = m.get("metadata", {}).get("document_title", "Document")
                    text = m.get("text", "").strip()
                    snippets.append(f"[Fact {idx} - {doc_title}]: {text}")
                context = (
                    "Relevant Knowledge Base Excerpts:\n"
                    + "\n".join(snippets)
                    + "\nSpoken Grounding Directive: Synthesize the answer concisely in 1 to 2 spoken sentences. "
                    "Do NOT read citations, bracket numbers, or URLs."
                )
                status = "found"
            else:
                context = "No specific internal policy or record found matching this query."
                status = "not_found"

        except Exception as exc:
            logger.error(f"[VOICE_ACTION: QUERY_KNOWLEDGE_BASE] Error retrieving knowledge: {exc}")
            context = "Knowledge base service momentarily unavailable."
            status = "error"
            match_count = 0

        response = QueryKnowledgeBaseResponse(
            status=status,
            query=query_text,
            context=context,
            match_count=match_count,
        )
        return ActionOutput(
            action_type=action_input.action_config.type,
            response=response,
        )
