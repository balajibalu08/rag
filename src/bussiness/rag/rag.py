import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from agent_framework import MCPStreamableHTTPTool
from agent_framework_ollama import OllamaChatClient

from mcp import types as mcp_types
from src.bussiness.ingestion.embedding_executor import EmbeddingExecutor
from src.bussiness.rag.critic import CriticAgent
from src.core.config import config
from src.core.logger import logger
from src.models.rag import CriticResponse, QueryContextDecision, RagRespone

INSUFFICIENT_INFORMATION = "I don't have enough information in the provided documents."

QUERY_REWRITE_INSTRUCTIONS = """
Determine whether the latest user question depends on the conversation
history to be understood.

If the question is understandable on its own, set
`depends_on_history` to false. If it refers to a previous topic, entity,
or answer, set it to true and rewrite it as a standalone search query.

Do not answer the question or add facts.
"""


INSTRUCTIONS = """
You are a document-based RAG assistant.

You have access to the `retrieve_documents` MCP tool.

Rules:

1. The application has already called `retrieve_documents` for this request.
   Use only the retrieved passages included in the user message.

2. Do not call the retrieval tool again.

3. If no relevant passages were retrieved or they do not
   contain enough information, respond with:
   "I don't have enough information in the provided documents."

4. Never invent facts, sources, filenames, page numbers, or information.

5. Answer the user's question directly and clearly.

6. Do not use outside knowledge.

7. Return only the answer text. Do not include JSON, source lists, or
   explanations outside the answer.
"""

class RAGAgent:
    def __init__(self):

        logger.info("Initializing RAGAgent.")

        self.conversation_history: list[dict[str, str]] = []
        self.max_history_turns = 10

        self.model_id = config["Application"]["rag"]["llm_model"]

        self.top_k = config["Application"]["rag"]["top_k_retrievals"]

        self.confidence_threshold = config["Application"]["rag"]["confidence_threshold"]

        self.max_attempts = config["Application"]["rag"]["max_attempts"]
        self._retrieved_documents: ContextVar[list[dict[str, Any]] | None] = ContextVar(
            f"rag_retrieved_documents_{id(self)}", default=None
        )

        if (
            type(self.confidence_threshold) is not int
            or not 0 <= self.confidence_threshold <= 100
        ):
            raise ValueError(
                "RAG confidence_threshold must be an integer between 0 and 100."
            )

        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("RAG max_attempts must be a positive integer.")

        self.vector_store_directory = Path(
            config["Application"]["vector_database_settings"]["vector_store_directory"]
        )

        try:
            self.client = OllamaChatClient(
                model=self.model_id,
                host=os.getenv("OLLAMA_HOST"),
            )

            logger.info(
                "OllamaChatClient initialized with model_id: %s",
                self.model_id,
            )

        except Exception as exc:
            logger.exception("Failed to initialize OllamaChatClient.")

            raise RuntimeError(
                f"Could not initialize Ollama model '{self.model_id}'."
            ) from exc

        try:
            self.embedding = EmbeddingExecutor(id="rag-embedding-executor")

            self.embedding_model = self.embedding._create_embedding_model()

            logger.info("Embedding model initialized successfully.")

        except Exception as exc:
            logger.exception("Failed to initialize embedding model.")

            raise RuntimeError("Could not initialize the embedding model.") from exc

        try:
            self.vector_store = self.embedding.load_vector_store(
                directory=str(self.vector_store_directory),
                embeddings=self.embedding_model,
            )

            logger.info("FAISS vector store loaded successfully")

            logger.info(
                "FAISS vector store loaded from: %s",
                self.vector_store_directory.resolve(),
            )

        except Exception as exc:
            logger.exception("Failed to load FAISS vector store.")

            raise RuntimeError("Could not load the FAISS vector store.") from exc

        try:
            mcp_settings = config["Application"]["mcp"]
            self.mcp_tool = MCPStreamableHTTPTool(
                name="rag_knowledge_base",
                url=os.getenv("RAG_MCP_SERVER_URL", mcp_settings["server_url"]),
                allowed_tools=["retrieve_documents"],
                parse_tool_results=self._capture_mcp_tool_result,
                description="Retrieve relevant document passages from the RAG vector store.",
            )

            self.rag_agent = self.client.as_agent(
                instructions=INSTRUCTIONS,
                tools=[self.mcp_tool],
            )

            self.query_rewriter_agent = self.client.as_agent(
                instructions=QUERY_REWRITE_INSTRUCTIONS,
            )

            logger.info("RAGAgent initialized successfully.")

        except Exception as exc:
            logger.exception("Failed to create the RAG agent.")

            raise RuntimeError("Could not create the Ollama agent.") from exc

        try:
            self.critic = CriticAgent()

            logger.info("CriticAgent initialized successfully.")

        except Exception as exc:
            logger.exception("Failed to initialize CriticAgent.")

            raise RuntimeError("Could not initialize the critic agent.") from exc

    def reload_vector_store(self) -> None:
        """Reload the on-disk index after newly uploaded documents are ingested."""
        try:
            self.vector_store = self.embedding.load_vector_store(
                directory=str(self.vector_store_directory),
                embeddings=self.embedding_model,
            )
        except Exception as exc:
            logger.exception("Failed to reload the FAISS vector store.")
            raise RuntimeError("Could not reload the FAISS vector store.") from exc

        logger.info(
            "FAISS vector store reloaded from: %s",
            self.vector_store_directory.resolve(),
        )

    @staticmethod
    def _get_source_reference(document):
        metadata = (
            document
            if isinstance(document, dict)
            else getattr(document, "metadata", {})
        )

        if not metadata:
            return "Unknown source"

        source = (
            metadata.get("source")
            or metadata.get("document_name")
            or metadata.get("file_name")
            or metadata.get("filename")
        )

        page = metadata.get("page") or metadata.get("page_number")

        if source and page is not None:
            return f"{source}, page {page}"

        if source:
            return str(source)

        return "Unknown source"

    @staticmethod
    def _extract_response_text(response):

        text = getattr(response, "text", None)

        if isinstance(text, str) and text.strip():
            return text.strip()

        value = getattr(response, "value", None)

        if isinstance(value, str) and value.strip():
            return value.strip()

        if value is not None:
            return str(value).strip()

        raise ValueError("The agent returned an empty response.")

    def _capture_mcp_tool_result(self, result: mcp_types.CallToolResult) -> str:
        structured_result = result.structuredContent
        if isinstance(structured_result, dict):
            documents = structured_result.get("result")
            current_documents = self._retrieved_documents.get()
            if isinstance(documents, list) and current_documents is not None:
                current_documents.extend(
                    document for document in documents if isinstance(document, dict)
                )
            return json.dumps(structured_result, ensure_ascii=False, default=str)

        text_result = "\n".join(
            item.text
            for item in result.content
            if isinstance(item, mcp_types.TextContent)
        )
        if text_result:
            try:
                parsed_result = json.loads(text_result)
            except json.JSONDecodeError:
                return text_result
            if isinstance(parsed_result, dict):
                documents = parsed_result.get("result")
                current_documents = self._retrieved_documents.get()
                if isinstance(documents, list) and current_documents is not None:
                    current_documents.extend(
                        document for document in documents if isinstance(document, dict)
                    )
            return text_result

        return "The retrieval tool returned no document content."

    @staticmethod
    def _parse_json_response(raw_response: str):
        """
        This method is a helper function that takes the LLM's raw response, cleans it,
        converts it from JSON text into a Python dictionary, and validates that the result
        is actually a JSON object.
        """
        cleaned = raw_response.strip()

        cleaned = re.sub(
            r"^\s*```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```\s*$",
            "",
            cleaned,
        )

        parsed = json.loads(cleaned)

        if not isinstance(parsed, dict):
            raise TypeError("The model response must be a JSON object.")

        return parsed

    async def _generate_rag_response(
        self,
        query: str,
        retrieval_query: str,
        feedback: str | None = None,
        on_answer_chunk: Callable[[str | None], Awaitable[None]] | None = None,
    ) -> tuple[RagRespone, list[dict[str, Any]]]:
        retrieved_documents: list[dict[str, Any]] = []
        retrieval_token = self._retrieved_documents.set(retrieved_documents)
        try:
            async with self.mcp_tool:
                await self.mcp_tool.call_tool(
                    "retrieve_documents",
                    query=retrieval_query,
                )

                logger.info(
                    "MCP retrieval returned %d passages for query: %s",
                    len(retrieved_documents),
                    retrieval_query,
                )

                context, _ = self._format_retrieved_documents(retrieved_documents)
                if not context:
                    return (
                        RagRespone(
                            query=query,
                            answer=INSUFFICIENT_INFORMATION,
                            sources=[],
                        ),
                        retrieved_documents,
                    )

                request_guidance = (
                    "Answer the user's question using only the retrieved "
                    "information below. If the information does not answer "
                    "the question, respond exactly:\n"
                    f'"{INSUFFICIENT_INFORMATION}"'
                )
                retry_guidance = f"\n\nCRITIC FEEDBACK:\n{feedback}" if feedback else ""
                prompt = f"""
{request_guidance}
Do not infer missing facts from general knowledge or invent information.
Return only the answer text, without JSON or a source list.
{retry_guidance}

USER QUESTION:
{query}

STANDALONE SEARCH QUERY:
{retrieval_query}

RETRIEVED INFORMATION:
<context>
{context}
</context>
"""

                if on_answer_chunk is None:
                    response = await self.rag_agent.run(prompt)
                else:
                    response_stream = self.rag_agent.run(prompt, stream=True)
                    async for update in response_stream:
                        if update.text and retrieved_documents:
                            await on_answer_chunk(update.text)
                    response = await response_stream.get_final_response()

            answer = self._extract_response_text(response)
            logger.debug("Generated RAG answer: %s", answer)
        except Exception as exc:
            logger.exception("RAG agent or MCP tool execution failed.")
            raise RuntimeError(
                "The RAG agent failed to process the request using MCP tools."
            ) from exc
        finally:
            self._retrieved_documents.reset(retrieval_token)

        return RagRespone(query=query, answer=answer, sources=[]), retrieved_documents

    def _format_retrieved_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> tuple[str, list[str]]:
        context_parts: list[str] = []
        sources: list[str] = []

        for index, document in enumerate(documents, start=1):
            content = document.get("content")
            metadata = document.get("metadata", {})
            if not isinstance(content, str) or not content.strip():
                logger.warning("Retrieved document %d has empty content.", index)
                continue

            source_reference = self._get_source_reference(metadata)
            if source_reference not in sources:
                sources.append(source_reference)
            context_parts.append(
                f"Document {index}\n"
                f"Source: {source_reference}\n"
                f"Content:\n{content.strip()}"
            )

        return "\n\n---\n\n".join(context_parts), sources

    def _validate_sources(self, result: RagRespone, sources: list[str]):
        """
        This function is responsible for checking and
        cleaning the sources returned by the critic/RAG response.
        """
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

        if not result.sources:
            result.sources = sources

        return result

    async def _rewrite_query(self, query: str) -> str:
        """
        this function is responsible for handling follow-up questions in s RAG system.
        """
        if not self.conversation_history:
            return query

        history = "\n\n".join(
            f"User: {turn['query']}\nAssistant: {turn['answer']}"
            for turn in self.conversation_history
        )

        prompt = f"""
CONVERSATION HISTORY:
{history}

LATEST USER QUESTION:
{query}

Classify whether the latest question depends on the history.

Examples:
- Earlier question: "What rules do I have to follow?"
  Latest question: "who am i"
  This is independent. Set depends_on_history=false.
- Earlier question: "What are student responsibilities?"
  Latest question: "What about deadlines?"
  This depends on the earlier question. Set depends_on_history=true and
  rewrite standalone_query to include the student-responsibilities context.

If depends_on_history is false, standalone_query should be the latest
question unchanged. Do not answer the question.
"""

        try:
            response = await self.query_rewriter_agent.run(
                prompt,
                options={
                    "response_format": QueryContextDecision,
                },
            )

            decision = QueryContextDecision.model_validate(
                self._parse_json_response(self._extract_response_text(response))
            )

            if not decision.depends_on_history:
                logger.info("Current query is independent of conversation history.")

                return query

            rewritten_query = decision.standalone_query.strip()

        except Exception as exc:
            logger.exception("Failed to classify or rewrite the follow-up query.")

            raise RuntimeError(
                "Could not classify the query using conversation history."
            ) from exc

        if not rewritten_query:
            raise ValueError("The query rewriter returned an empty standalone query.")

        logger.info(
            "Rewrote history-dependent query for retrieval: %s",
            rewritten_query,
        )

        return rewritten_query

    def _save_conversation_turn(self, query: str, answer: str) -> None:

        self.conversation_history.append(
            {
                "query": query,
                "answer": answer,
            }
        )

        if len(self.conversation_history) > self.max_history_turns:
            del self.conversation_history[
                : len(self.conversation_history) - self.max_history_turns
            ]

    async def route_request(
        self,
        query: str,
        *,
        on_answer_chunk: Callable[[str | None], Awaitable[None]] | None = None,
    ) -> RagRespone:
        """
        Retrieve documents first, then generate a grounded answer.

        Retrieval is mandatory because the agent must call the MCP retrieval
        tool before answering.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError("The query must be a non-empty string.")

        query = query.strip()

        logger.info("Processing RAG query: %s", query)

        # Step 1: Resolve follow-up references using in-memory history.
        retrieval_query = await self._rewrite_query(query)

        # Step 2: Generate with the MCP retrieval tool available to the agent.
        result, retrieved_docs = await self._generate_rag_response(
            query=query,
            retrieval_query=retrieval_query,
            on_answer_chunk=on_answer_chunk,
        )

        if not retrieved_docs:
            logger.warning("The MCP retrieval tool returned no documents.")
            result.answer = INSUFFICIENT_INFORMATION
            result.sources = []
            self._save_conversation_turn(query, result.answer)
            return result

        # Step 3: Prepare retrieved context for critic evaluation and sources.
        context, sources = self._format_retrieved_documents(retrieved_docs)

        if not context:
            logger.warning("Retrieved documents did not contain usable text.")
            result.answer = INSUFFICIENT_INFORMATION
            self._save_conversation_turn(query, result.answer)
            return result

        result = self._validate_sources(
            result,
            sources,
        )
        result.query = query

        # Step 5: Critic evaluation and feedback-based retries.

        logger.info(
            "Critic acceptance threshold: %d; maximum RAG attempts: %d",
            self.confidence_threshold,
            self.max_attempts,
        )

        critic_response = None

        for attempt in range(self.max_attempts):
            logger.info(
                "Running critic evaluation. Attempt %d/%d",
                attempt + 1,
                self.max_attempts,
            )

            critic_prompt = f"""
Evaluate the following RAG response.

USER QUERY:
{query}

INTERPRETED SEARCH QUERY:
{retrieval_query}

RAG ANSWER:
{result.answer}

RETRIEVED INFORMATION:
<context>
{context}
</context>

Evaluate whether the RAG answer:

* Correctly answers the user's query.
* Is supported by the retrieved documents.
* Contains unsupported or hallucinated information.
* Misses important information from the retrieved documents.
* Is relevant to the user's question.

Assign a confidence score from 0 to 100.

The `is_correct` field must be true only when the answer
is sufficiently supported by the retrieved information
and correctly addresses the user's query.

The `reasoning` field must explain the confidence score.

The `feedback` field must provide specific feedback
that the RAG agent can use to improve the answer.

Do not generate a new answer.

Do not modify or invent information from the retrieved documents.

Return only the required structured response.
"""

            # Step 5: Run critic agent

            try:
                critic_result = await self.critic.agent.run(
                    critic_prompt,
                    options={
                        "response_format": CriticResponse,
                    },
                )

                critic_raw_response = self._extract_response_text(critic_result)

                logger.debug("Raw critic response: %s", critic_raw_response)

                critic_parsed_response = self._parse_json_response(critic_raw_response)

                critic_response = CriticResponse.model_validate(critic_parsed_response)

            except Exception as exc:
                logger.exception("Critic evaluation failed.")

                raise RuntimeError(
                    "The critic agent failed to evaluate the RAG response."
                ) from exc

            logger.info("Critic confidence: %d", critic_response.confidence)

            logger.info("Critic correctness: %s", critic_response.is_correct)

            logger.info("Critic reasoning: %s", critic_response.reasoning)

            logger.info("Critic feedback: %s", critic_response.feedback)

            # Step 6: Accept response if critic approves it

            if (
                critic_response.confidence >= self.confidence_threshold
                and critic_response.is_correct
            ):
                logger.info("RAG response accepted by critic.")

                result = result.model_copy(
                    update={"query": query, "critic_response": critic_response}
                )
                self._save_conversation_turn(
                    query,
                    result.answer,
                )
                return result

            # Step 7: Retry RAG response if critic rejects it

            if attempt + 1 < self.max_attempts:
                logger.warning("RAG response rejected by critic.")

                logger.info("Retrying RAG generation using critic feedback.")

                if on_answer_chunk is not None:
                    await on_answer_chunk(None)

                result, retrieved_docs = await self._generate_rag_response(
                    query=query,
                    retrieval_query=retrieval_query,
                    feedback=critic_response.feedback,
                    on_answer_chunk=on_answer_chunk,
                )

                context, sources = self._format_retrieved_documents(retrieved_docs)
                if not context:
                    result.answer = INSUFFICIENT_INFORMATION
                    result.sources = []
                    break

                result = self._validate_sources(
                    result,
                    sources,
                )
                result.query = query

            else:
                logger.warning(
                    "Maximum RAG attempts reached; returning the latest response."
                )

        # Step 7: Save the final answer to runtime conversation history.

        logger.info("Returning final RAG response.")

        result = result.model_copy(
            update={"query": query, "critic_response": critic_response}
        )

        self._save_conversation_turn(
            query,
            result.answer,
        )

        return result

    @property
    def agent(self):

        return self.rag_agent


async def main():
    try:
        rag = RAGAgent()

        while True:
            query = input("Enter your question (or 'exit' to quit): ").strip()

            if query.lower() in {"exit", "quit"}:
                break

            if not query:
                continue

            response = await rag.route_request(query)

            print("\n" + "=" * 60)
            print("                    RAG RESPONSE")
            print("=" * 60)

            print("\nQuery:")
            print(response.query)

            print("\nAnswer:")
            print(response.answer)

            print("\nSources:")
            if response.sources:
                for source in response.sources:
                    print(f"- {source}")
            else:
                print("- No sources")

            print("\n" + "=" * 60)
            print("                   CRITIC RESPONSE")
            print("=" * 60)

            if response.critic_response is None:
                print("\nCritic evaluation was not run.")

            else:
                print("\nConfidence:")
                print(f"{response.critic_response.confidence}/100")

                print("\nIs Correct:")
                print(response.critic_response.is_correct)

                print("\nReasoning:")
                print(response.critic_response.reasoning)

                print("\nFeedback:")
                print(response.critic_response.feedback)

            print("\n" + "=" * 60)

    except Exception as exc:  # noqa: BLE001 - Report failures in the CLI entry point.
        logger.exception("Unexpected application failure.")

        print(f"\nError: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
