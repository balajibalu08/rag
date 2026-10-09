import asyncio
import json
import re
from pathlib import Path
from typing import Any

from agent_framework.ollama import OllamaChatClient

from src.dcoument_pipeline.embedding import (
    create_embeddings,
    load_vector_store,
    retrieve_documents,
)
from src.model.rag_response_model import RAGResponse
from src.utils.logger import logger

# Configuration


DEFAULT_MODEL_ID = "qwen2.5:3b"
DEFAULT_VECTOR_STORE_DIRECTORY = "./data/vector_store"
TOP_K = 3

INSUFFICIENT_INFORMATION = "I don't have enough information in the provided documents."

INSTRUCTIONS = """
You are a document-based RAG assistant.

You must answer questions using only the retrieved documents supplied
in the user's prompt.

Rules:
1. Use the retrieved documents as your only source of factual information.
2. Never invent facts, sources, filenames, or page numbers.
3. If the documents do not contain enough information, respond with:
   "I don't have enough information in the provided documents."
4. Include only sources that support your answer.
5. Return a valid JSON object with these fields:
   - answer: a string
   - sources: a list of strings
6. Do not include Markdown code fences around the JSON.
"""


class RAGAgent:
    """Document question-answering agent using Ollama and FAISS."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        vector_store_directory: str = DEFAULT_VECTOR_STORE_DIRECTORY,
        top_k: int = TOP_K,
    ) -> None:
        logger.info("Initializing RAGAgent.")

        self.model_id = model_id
        self.top_k = top_k
        self.vector_store_directory = Path(vector_store_directory)

        if self.top_k < 1:
            raise ValueError("top_k must be greater than or equal to 1.")

        # Initialize the chat client.
        try:
            self.client = OllamaChatClient(model_id=self.model_id)
            logger.info(
                "OllamaChatClient initialized with model_id: %s",
                self.model_id,
            )
        except Exception as exc:
            logger.exception("Failed to initialize OllamaChatClient.")
            raise RuntimeError(
                f"Could not initialize Ollama model '{self.model_id}'."
            ) from exc

        # Initialize embeddings once.
        try:
            self.embedding_model = create_embeddings()
            logger.info("Embedding model initialized successfully.")
        except Exception as exc:
            logger.exception("Failed to initialize embedding model.")
            raise RuntimeError("Could not initialize the embedding model.") from exc

        # Load the persisted FAISS vector store once.
        try:
            self.vector_store = load_vector_store(
                directory=str(self.vector_store_directory),
                embeddings=self.embedding_model,
            )
            logger.info(
                "FAISS vector store loaded from: %s",
                self.vector_store_directory.resolve(),
            )
        except FileNotFoundError as exc:
            logger.exception("FAISS index files were not found.")
            raise RuntimeError(
                f"FAISS vector store was not found at "
                f"'{self.vector_store_directory.resolve()}'. "
                "Create or load the vector store before starting the agent."
            ) from exc
        except Exception as exc:
            logger.exception("Failed to load FAISS vector store.")
            raise RuntimeError("Could not load the FAISS vector store.") from exc

        # Create the chat agent.
        try:
            self.rag_agent = self.client.as_agent(
                instructions=INSTRUCTIONS,
            )
            logger.info("RAGAgent initialized successfully.")
        except Exception as exc:
            logger.exception("Failed to create the chat agent.")
            raise RuntimeError("Could not create the Ollama agent.") from exc

    @staticmethod
    def _get_source_reference(document: Any) -> str:
        """Build a source reference from document metadata."""

        metadata = getattr(document, "metadata", {}) or {}

        source = metadata.get("source") or metadata.get("file_name")

        if not source:
            source = metadata.get("filename") or metadata.get("file_path")

        page = metadata.get("page")

        if page is None:
            page = metadata.get("page_number")

        # Preserve the actual metadata without inventing missing values.
        if source and page is not None:
            return f"{source}, page {page}"

        if source:
            return str(source)

        if page is not None:
            return f"Page {page}, source filename unavailable"

        return "Source metadata unavailable"

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """Extract text from the Agent Framework response."""

        # AgentResponse implementations may expose the final text
        # through different attributes.
        text = getattr(response, "text", None)

        if isinstance(text, str) and text.strip():
            return text.strip()

        value = getattr(response, "value", None)

        if isinstance(value, str) and value.strip():
            return value.strip()

        if value is not None:
            return str(value).strip()

        raise ValueError("The agent returned an empty response.")

    @staticmethod
    def _parse_json_response(raw_response: str) -> dict[str, Any]:
        """
        Parse JSON output, including JSON wrapped in Markdown fences.

        This method does not treat arbitrary prose as a validated JSON
        response.
        """

        cleaned = raw_response.strip()

        # Remove optional Markdown code fences.
        cleaned = re.sub(
            r"^\s*```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

        parsed = json.loads(cleaned)

        if not isinstance(parsed, dict):
            raise ValueError("The model response must be a JSON object.")

        return parsed

    async def route_request(self, query: str) -> RAGResponse:
        """
        Retrieve documents first, then generate a grounded answer.

        Retrieval is mandatory because it happens in application code
        before the LLM is called.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError("The query must be a non-empty string.")

        query = query.strip()

        logger.info("Processing RAG query: %s", query)

        # Step 1: Retrieve documents

        try:
            retrieved_docs = retrieve_documents(
                self.vector_store,
                query,
                k=self.top_k,
            )

        except Exception as exc:
            logger.exception("Document retrieval failed.")

            raise RuntimeError(
                "Could not retrieve documents from the FAISS vector store."
            ) from exc

        if not retrieved_docs:
            logger.warning("No documents were retrieved for the query.")

            return RAGResponse(
                answer=INSUFFICIENT_INFORMATION,
                sources=[],
            )

        logger.info(
            "Retrieved %d documents for the query.",
            len(retrieved_docs),
        )

        # Step 2: Prepare context and source references

        context_parts: list[str] = []
        sources: list[str] = []

        for index, doc in enumerate(retrieved_docs, start=1):
            content = getattr(doc, "page_content", None)

            if not isinstance(content, str) or not content.strip():
                logger.warning(
                    "Retrieved document %d has empty or invalid content.",
                    index,
                )
                continue

            source_reference = self._get_source_reference(doc)

            if source_reference not in sources:
                sources.append(source_reference)

            context_parts.append(
                f"Document {index}\n"
                f"Source: {source_reference}\n"
                f"Content:\n{content.strip()}"
            )

        if not context_parts:
            logger.warning("Retrieved documents did not contain usable text.")

            return RAGResponse(
                answer=INSUFFICIENT_INFORMATION,
                sources=[],
            )

        context = "\n\n---\n\n".join(context_parts)

        # Step 3: Build the grounded prompt

        prompt = f"""
Answer the user's question using only the retrieved document context.

If the context does not contain sufficient information to answer,
return exactly this answer:
"{INSUFFICIENT_INFORMATION}"

Do not infer missing facts from general knowledge.

The sources field must contain only source references listed in
the retrieved context that support the answer.

Return a JSON object with this structure:
{{
    "answer": "Answer based on the retrieved documents",
    "sources": ["source filename, page number"]
}}

USER QUESTION:
{query}

RETRIEVED DOCUMENT CONTEXT:
<context>
{context}
</context>
"""

        # Step 4: Generate the answer

        try:
            response = await self.rag_agent.run(prompt)
            raw_response = self._extract_response_text(response)

            logger.debug("Raw model response: %s", raw_response)

        except Exception as exc:
            logger.exception("Ollama answer generation failed.")

            raise RuntimeError(
                "The Ollama agent failed to generate an answer."
            ) from exc

        # Step 5: Parse and validate the JSON response

        try:
            parsed_response = self._parse_json_response(raw_response)

            result = RAGResponse.model_validate(parsed_response)

        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning(
                "The model did not return a valid RAGResponse: %s",
                exc,
            )

            # Avoid returning arbitrary unvalidated prose as a successful
            # grounded answer. Preserve actual retrieved source references.
            result = RAGResponse(
                answer=(
                    "The model returned an invalid response format. "
                    "Please try the question again."
                ),
                sources=sources,
            )

        # Step 6: Validate source references

        allowed_sources = set(sources)

        validated_sources = []

        for source in result.sources:
            if source in allowed_sources and source not in validated_sources:
                validated_sources.append(source)
            else:
                logger.warning(
                    "Ignoring an unrecognized or duplicate source: %s",
                    source,
                )

        result.sources = validated_sources

        # If the model omitted sources, use the actual retrieved sources.
        # This identifies retrieved material, but does not independently
        # prove every source supports the answer.
        if not result.sources:
            result.sources = sources

        logger.info("RAG response generated successfully.")

        return result

    @property
    def agent(self):
        """Return the underlying Agent Framework agent."""
        return self.rag_agent


async def main() -> None:
    """Run a sample RAG query."""

    try:
        rag = RAGAgent()

        query = "Students use which forms or services to request involving enrollment?"

        response = await rag.route_request(query)

        print("\nAnswer:")
        print(response.answer)

        print("\nSources:")

        if response.sources:
            for source in response.sources:
                print(f"- {source}")
        else:
            print("No sources available.")

    except (ValueError, RuntimeError) as exc:
        logger.error("RAG application error: %s", exc)
        print(f"\nError: {exc}")

    except Exception:
        logger.exception("Unexpected application failure.")
        print("\nAn unexpected error occurred. Check the application logs.")


if __name__ == "__main__":
    asyncio.run(main())
