import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.bussiness.rag.runtime import chat_lock, get_rag_agent
from src.core.logger import logger
from src.models.chat import ChatRequest, ChatResponse
from src.models.rag import RagRespone

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


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
        async with chat_lock:
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


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    async def events():
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def send_answer_chunk(chunk: str | None) -> None:
            if chunk is None:
                await queue.put(("reset", ""))
            else:
                await queue.put(("delta", chunk))

        async def run_chat() -> None:
            try:
                async with chat_lock:
                    result = await get_rag_agent().route_request(
                        request.query,
                        on_answer_chunk=send_answer_chunk,
                    )
                await queue.put(
                    ("complete", make_chat_response(result).model_dump(mode="json"))
                )
            except RuntimeError:
                logger.exception("RAG streaming request failed.")
                await queue.put(
                    (
                        "error",
                        {"detail": "The RAG service could not answer the question."},
                    )
                )
            except Exception as exc:  # noqa: BLE001 - Report failures through SSE.
                logger.exception(
                    "Unexpected error while streaming a chat response: %s",
                    exc,
                )
                await queue.put(
                    (
                        "error",
                        {
                            "detail": (
                                "An unexpected error occurred while processing "
                                "the question."
                            )
                        },
                    )
                )
            finally:
                await queue.put(("end", None))

        task = asyncio.create_task(run_chat())
        try:
            while True:
                event, payload = await queue.get()
                if event == "end":
                    break
                yield f"event: {event}\ndata: {json.dumps(payload)}\n\n"
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
