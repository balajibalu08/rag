import asyncio
import json
import re
from pathlib import Path

from agent_framework_ollama import OllamaChatClient
from pydantic import BaseModel, Field

from src.bussiness.ingestion.embedding_executor import EmbeddingExecutor
from src.bussiness.rag.critic import CriticAgent
from src.bussiness.rag.models.critic_response_model import CriticResponse
from src.bussiness.rag.models.rag_response_model import RagRespone
from src.core.config import config
from src.core.logger import logger

INSUFFICIENT_INFORMATION = "I don't have enough information in the provided documents."

QUERY_REWRITE_INSTRUCTIONS = """
Determine whether the latest user question depends on the conversation
history to be understood.

If the question is understandable on its own, set
`depends_on_history` to false. If it refers to a previous topic, entity,
or answer, set it to true and rewrite it as a standalone search query.

Do not answer the question or add facts.
"""


class QueryContextDecision(BaseModel):
    depends_on_history: bool = Field(
        ...,
        description="Whether the latest question requires earlier conversation turns.",
    )
    standalone_query: str = Field(
        ...,
        description=(
            "A standalone rewrite if history is needed; otherwise return "
            "the latest question unchanged."
        ),
    )


INSTRUCTIONS = """
You are a document-based RAG assistant.

You must answer questions using only the retrieved documents supplied
in the prompt.

Rules:

1. Use the retrieved documents as the only source of factual information.

2. Never invent facts, sources, filenames, page numbers, or information.

3. If the documents do not contain enough information, respond with:
   "I don't have enough information in the provided documents."

4. Include only sources that actually support the answer.

5. Answer the user's question directly and clearly.

6. Do not use outside knowledge.

7. Return a valid JSON object with exactly these fields:

{
    "query": "The user's question",
    "answer": "Answer based on the retrieved documents",
    "sources": ["source filename"]
}

8. Do not include Markdown code fences around the JSON.

9. Do not provide explanations outside the JSON object.
"""


class RAGAgent:
    def __init__( self):

        logger.info("Initializing RAGAgent.")

        self.conversation_history: list[dict[str, str]] = []
        self.max_history_turns = 10

        self.model_id = config["Application"]["rag"]["llm_model"]

        self.top_k = config["Application"]["rag"]["top_k_retrievals"]

        self.confidence_threshold = config["Application"]["rag"]["confidence_threshold"]

        self.max_attempts = config["Application"]["rag"]["max_attempts"]

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
            self.client = OllamaChatClient(model=self.model_id)

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
            self.rag_agent = self.client.as_agent(
                instructions=INSTRUCTIONS,
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

    @staticmethod
    def _get_source_reference( document ):

        metadata = getattr(document, "metadata", {})

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
    def _extract_response_text( response ):

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
    def _parse_json_response( raw_response: str ):

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
            raise ValueError("The model response must be a JSON object.")

        return parsed

    async def _generate_rag_response( self, query: str, context: str, feedback: str | None = None ) -> RagRespone:

        if feedback:
            prompt = f"""
Improve the previous RAG answer using the critic feedback.

Answer the user's question using ONLY the retrieved document context.

Do not use outside knowledge.

Do not invent information.

Make sure the answer directly addresses the user's question.

CRITIC FEEDBACK:
{feedback}

If the retrieved context does not contain sufficient information,
return exactly:

"{INSUFFICIENT_INFORMATION}"

USER QUESTION:
{query}

RETRIEVED DOCUMENT CONTEXT:
<context>
{context}
</context>

Return ONLY a JSON object with this structure:

{{
    "query": "{query}",
    "answer": "Answer based only on retrieved documents",
    "sources": ["source filename"]
}}
"""

        else:
            prompt = f"""
Answer the user's question using only the retrieved document context.

If the context does not contain sufficient information to answer,
return exactly:

"{INSUFFICIENT_INFORMATION}"

Do not infer missing facts from general knowledge.

Do not invent information.

The sources field must contain only source references listed
in the retrieved context that support the answer.

USER QUESTION:
{query}

RETRIEVED DOCUMENT CONTEXT:
<context>
{context}
</context>

Return ONLY a JSON object with this structure:

{{
    "query": "{query}",
    "answer": "Answer based on the retrieved documents",
    "sources": ["source filename"]
}}
"""

        try:
            response = await self.rag_agent.run(prompt)

            raw_response = self._extract_response_text(response)

            logger.debug("Raw model response: %s", raw_response)

        except Exception as exc:
            logger.exception("Ollama answer generation failed.")

            raise RuntimeError(
                "The Ollama agent failed to generate an answer."
            ) from exc

        try:
            parsed_response = self._parse_json_response(raw_response)

            result = RagRespone.model_validate(parsed_response)

        except (
            json.JSONDecodeError,
            ValueError,
            TypeError,
        ) as exc:
            logger.warning(
                "The model did not return a valid RAGResponse: %s",
                exc,
            )

            result = RagRespone(
                query=query,
                answer=(
                    "The model returned an invalid "
                    "response format. "
                    "Please try the question again."
                ),
                sources=[],
            )

        return result

    def _validate_sources( self, result: RagRespone, sources: list[str] ):

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

    async def _rewrite_query(self,query: str ) -> str:

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

    def _save_conversation_turn( self, query: str, answer: str ) -> None:

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

    async def route_request( self, query: str ) -> RagRespone:
        """
        Retrieve documents first, then generate a grounded answer.

        Retrieval is mandatory because it happens in application code
        before the LLM is called.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError("The query must be a non-empty string.")

        query = query.strip()

        logger.info("Processing RAG query: %s", query)

        # Step 1: Resolve follow-up references using in-memory history.
        retrieval_query = await self._rewrite_query(query)

        # Step 2: Retrieve documents from the existing FAISS index.

        try:
            retrieved_docs = self.embedding.retrieve_documents(
                self.vector_store,
                retrieval_query,
                k=self.top_k,
            )

        except Exception as exc:
            logger.exception("Document retrieval failed.")

            raise RuntimeError(
                "Could not retrieve documents from the FAISS vector store."
            ) from exc

        if not retrieved_docs:
            logger.warning("No documents were retrieved for the query.")

            result = RagRespone(
                query=query,
                answer=INSUFFICIENT_INFORMATION,
                sources=[],
            )
            self._save_conversation_turn(
                query,
                result.answer,
            )
            return result

        logger.info(
            "Retrieved %d documents for the query.",
            len(retrieved_docs),
        )

        # Step 3: Prepare context and source references.

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

            result = RagRespone(
                query=query,
                answer=INSUFFICIENT_INFORMATION,
                sources=[],
            )
            self._save_conversation_turn(
                query,
                result.answer,
            )
            return result

        context = "\n\n---\n\n".join(context_parts)

        # Step 4: Generate the initial RAG response using the resolved query.

        result = await self._generate_rag_response(
            query=retrieval_query,
            context=context,
        )

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

                result = await self._generate_rag_response(
                    query=retrieval_query,
                    context=context,
                    feedback=critic_response.feedback,
                )

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

    except Exception as exc:
        logger.exception("Unexpected application failure.")

        print(f"\nError: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
