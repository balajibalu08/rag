from pathlib import Path

from agent_framework import Executor, WorkflowContext, handler
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from src.bussiness.ingestion.models import ChunkData
from src.core.config import config
from src.core.logger import logger


class EmbeddingExecutor(Executor):
    @handler
    async def create_embeddings(
        self,
        chunks: list[ChunkData] | ChunkData,
        ctx: WorkflowContext[str],
    ):
        logger.info("Embedding executor initiated")

        try:
            flattened_chunks = self._flatten_chunks(chunks)

            if not flattened_chunks:
                logger.warning("No chunks received for embedding")
                return

            documents = self._convert_to_documents(flattened_chunks)

            if not documents:
                logger.warning("No valid documents found for embedding")
                return

            embeddings = self._create_embedding_model()

            vector_store_dir = Path(
                config["Application"]["ingestion"]["vector_store"]["directory"]
            )

            index_file = vector_store_dir / "index.faiss"

            if index_file.exists():
                vector_store = FAISS.load_local(
                    str(vector_store_dir),
                    embeddings,
                    allow_dangerous_deserialization=True,
                )

                vector_store.add_documents(documents)

                logger.info(
                    "Added %d documents to existing FAISS index",
                    len(documents),
                )

            else:
                vector_store = self._create_vector_store(
                    documents=documents,
                    embeddings=embeddings,
                )

            self._save_vector_store(
                vector_store=vector_store,
                directory=vector_store_dir,
            )

            logger.info("Embedding executor completed successfully")

            await ctx.yield_output(
                f"Vector store created successfully with {len(documents)} documents"
            )

        except Exception as e:
            logger.exception(f"Embedding executor failed: {e}")

            raise

    def _flatten_chunks(
        self,
        chunks: list[ChunkData] | ChunkData,
    ) -> list[dict]:
        if isinstance(chunks, ChunkData):
            return chunks.chunks

        flattened: list[dict] = []
        for item in chunks:
            if isinstance(item, ChunkData):
                flattened.extend(item.chunks)
            elif isinstance(item, list):
                flattened.extend(item)
        return flattened

    def _convert_to_documents(
        self,
        chunks: list[dict],
    ) -> list[Document]:

        documents = []

        for index, chunk in enumerate(chunks):
            try:
                if not isinstance(chunk, dict):
                    logger.warning(f"Skipping invalid chunk at index {index}")
                    continue

                content = chunk.get("content", "")

                if not isinstance(content, str) or not content.strip():
                    logger.warning(f"Skipping empty chunk at index {index}")
                    continue

                metadata = chunk.get("metadata", {})

                metadata = {
                    **metadata,
                    "chunk_id": chunk.get("chunk_id"),
                    "document_name": chunk.get("document_name"),
                }

                documents.append(
                    Document(
                        page_content=content,
                        metadata=metadata,
                    )
                )

            except Exception:
                logger.exception(f"Failed to convert chunk at index {index}")

        logger.info(f"Converted {len(documents)} chunks into LangChain documents")

        return documents

    def _create_embedding_model(
        self,
    ) -> OllamaEmbeddings:

        embedding_model = config["Application"]["ingestion"]["embedding"]["model"]

        logger.info(f"Initializing embedding model: {embedding_model}")

        return OllamaEmbeddings(model=embedding_model)

    def _create_vector_store(
        self,
        documents: list[Document],
        embeddings: OllamaEmbeddings,
    ) -> FAISS:

        logger.info(f"Creating FAISS vector store for {len(documents)} documents")

        vector_store = FAISS.from_documents(
            documents=documents,
            embedding=embeddings,
        )

        logger.info("FAISS vector store created successfully")

        return vector_store

    def _save_vector_store(
        self,
        vector_store: FAISS,
        directory: Path,
    ) -> None:

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        vector_store.save_local(str(directory))

        logger.info(f"Vector store saved to: {directory.resolve()}")

    def retrieve_documents(
        self,
        vector_store,
        query: str,
        k: int,
    ):

        logger.info(f"Retrieving top {k} documents for query")

        documents = vector_store.similarity_search(
            query,
            k=k,
        )

        logger.info(f"Retrieved {len(documents)} documents")

        return documents

    def load_vector_store(
        self,
        directory: str,
        embeddings,
    ):

        logger.info(f"Loading FAISS vector store from: {directory}")

        vector_store = FAISS.load_local(
            directory,
            embeddings,
            allow_dangerous_deserialization=True,
        )

        logger.info("FAISS vector store loaded successfully")

        return vector_store
