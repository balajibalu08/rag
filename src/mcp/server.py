import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from src.bussiness.ingestion.router import ingest_uploaded_files
from src.bussiness.rag.runtime import chat_lock, get_rag_agent
from src.core.config import config
from src.core.logger import logger

mcp = FastMCP(
    name="RAG Knowledge Base",
    instructions=(
        "Retrieve relevant documents from the indexed RAG knowledge base, "
        "or ingest uploaded documents through the existing workflow."
    ),
    streamable_http_path="/",
)


@mcp.tool()
async def retrieve_documents(query: str) -> list[dict[str, object]]:
    """Retrieve relevant indexed document passages matching the user's query."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("The query must be a non-empty string.")

    agent = get_rag_agent()

    try:
        documents = await asyncio.to_thread(
            agent.vector_store.similarity_search,
            query.strip(),
            k=agent.top_k,
        )
    except Exception as exc:
        logger.exception("MCP vector-store document retrieval failed.")
        raise RuntimeError(
            "Could not retrieve documents from the vector store."
        ) from exc

    return [
        {
            "content": document.page_content,
            "metadata": document.metadata,
        }
        for document in documents
    ]


@mcp.tool()
async def ingest_documents(file_paths: list[str]) -> dict[str, object]:
    """Ingest uploaded files through the existing document workflow."""
    logger.info("MCP document ingestion requested.")
    if not isinstance(file_paths, list) or not file_paths:
        logger.warning("MCP document ingestion received no file paths.")
        return {
            "success": False,
            "message": "Document ingestion failed.",
            "error": "At least one file path is required.",
            "processed_files": [],
        }

    upload_directory = Path(
        config["Application"]["file_upload_settings"]["upload_directory"]
    ).resolve()
    resolved_paths: list[Path] = []
    try:
        for file_path in file_paths:
            if not isinstance(file_path, str) or not file_path.strip():
                raise ValueError("Each file path must be a non-empty string.")

            path = Path(file_path).resolve(strict=True)
            if not path.is_file():
                raise ValueError(f"File is not a regular file: {path.name}")
            if not path.is_relative_to(upload_directory):
                raise ValueError("Files must be located in the configured upload directory.")
            resolved_paths.append(path)

        unique_paths = list(dict.fromkeys(resolved_paths))
        logger.info(
            "MCP ingestion requested for %d files: %s",
            len(unique_paths),
            [path.name for path in unique_paths],
        )

        async with chat_lock:
            await ingest_uploaded_files([str(path) for path in unique_paths])

            if get_rag_agent.cache_info().currsize:
                rag_agent = get_rag_agent()
                rag_agent.reload_vector_store()
                rag_agent.conversation_history.clear()

        logger.info("MCP document ingestion workflow completed.")
        return {
            "success": True,
            "message": "Documents ingested and indexed successfully.",
            "processed_files": [str(path) for path in unique_paths],
        }
    except Exception as exc:  # noqa: BLE001 - Return structured MCP failure details.
        logger.exception("MCP document ingestion failed.")
        return {
            "success": False,
            "message": "Document ingestion failed.",
            "error": str(exc),
            "processed_files": [str(path) for path in resolved_paths],
        }
