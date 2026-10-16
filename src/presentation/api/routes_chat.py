import asyncio
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from src.bussiness.rag.models.rag_response_model import RagRespone
from src.bussiness.rag.rag import RAGAgent
from src.core.logger import logger
from src.presentation.schemas.chat_schema import ChatRequest
from src.presentation.schemas.response_schema import ChatResponse

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

_chat_lock = asyncio.Lock()


@lru_cache(maxsize=1)
def get_rag_agent() -> RAGAgent:
    """Keep one agent alive so its runtime conversation history is retained."""
    return RAGAgent()


def make_chat_response(result: RagRespone) -> ChatResponse:
    critic = result.critic_response

    return ChatResponse(
        query=result.query,
        answer=result.answer,
        sources=result.sources,
        confidence=critic.confidence if critic else None,
        is_correct=critic.is_correct if critic else None,
        reasoning=critic.reasoning if critic else None,
        feedback=critic.feedback if critic else None,
    )


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        # The agent keeps conversation history in memory; serialize calls so
        # concurrent requests cannot interleave turns in that history.
        async with _chat_lock:
            result = await get_rag_agent().route_request(request.query)

    except RuntimeError as exc:
        logger.exception("RAG request failed.")
        raise HTTPException(
            status_code=503,
            detail="The RAG service could not answer the question.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while handling a chat request.")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the question.",
        ) from exc

    return make_chat_response(result)
