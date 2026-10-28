import asyncio
from functools import lru_cache

from src.bussiness.rag.rag import RAGAgent

chat_lock = asyncio.Lock()


@lru_cache(maxsize=1)
def get_rag_agent() -> RAGAgent:
    """Keep one agent alive so its runtime conversation history is retained."""
    return RAGAgent()
