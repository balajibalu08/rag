import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS

from src.utils.logger import logger



# CONFIGURATION


CHUNKS_FILE = "data/chunks/final_chunks.json"

VECTOR_STORE_DIR = "data/vector_store"

EMBEDDING_MODEL = "qwen3-embedding:0.6b"

TOP_K = 3



# LOAD CHUNKS



def load_documents(chunks_file: str) -> List[Document]:
    """
    Load final chunks and convert them into
    LangChain Document objects.
    """

    path = Path(chunks_file)

    if not path.exists():
        logger.error("Chunks file not found: %s", path.resolve())

        raise FileNotFoundError(f"Chunks file not found: {path.resolve()}")

    if path.stat().st_size == 0:
        logger.error("Chunks file is empty: %s", path.resolve())

        raise ValueError("Chunks file is empty.")

    logger.info("Loading chunks from: %s", path.resolve())

    try:
        with open(path, "r", encoding="utf-8") as file:
            raw_docs = json.load(file)

    except json.JSONDecodeError as exc:
        logger.exception("Invalid JSON in chunks file.")

        raise ValueError("final_chunks.json contains invalid JSON.") from exc

    if not isinstance(raw_docs, list):
        logger.error("Expected chunks JSON to contain a list.")

        raise ValueError("Chunks JSON must contain a list.")

    documents = []

    for index, doc in enumerate(raw_docs):
        try:
            if not isinstance(doc, dict):
                logger.warning("Skipping invalid chunk at index %d.", index)

                continue

            content = doc.get("content", "")

            if not isinstance(content, str) or not content.strip():
                logger.warning("Skipping empty chunk at index %d.", index)

                continue

            metadata = doc.get("metadata", {})

            # Keep chunk ID available in metadata
            metadata = {
                **metadata,
                "chunk_id": doc.get("chunk_id"),
                "document_name": doc.get("document_name"),
            }

            documents.append(Document(page_content=content, metadata=metadata))

        except Exception:
            logger.exception("Failed to convert chunk at index %d.", index)

    logger.info("Successfully created %d LangChain documents.", len(documents))

    if not documents:
        raise ValueError("No valid documents were found in final_chunks.json.")

    return documents



# CREATE EMBEDDING MODEL



def create_embeddings() -> OllamaEmbeddings:
    """
    Create Ollama embedding model.
    """

    logger.info("Initializing Ollama embedding model: %s", EMBEDDING_MODEL)

    try:
        embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)

        return embeddings

    except Exception:
        logger.exception("Failed to initialize Ollama embeddings.")

        raise



# CREATE VECTOR STORE



def create_vector_store(
    documents: List[Document], embeddings: OllamaEmbeddings
) -> FAISS:
    """
    Create FAISS vector store from documents.
    """

    logger.info("Creating FAISS vector store for %d documents.", len(documents))

    try:
        vector_store = FAISS.from_documents(documents=documents, embedding=embeddings)

    except Exception:
        logger.exception("Failed to create FAISS vector store.")

        raise

    logger.info("FAISS vector store created successfully.")

    return vector_store



# SAVE VECTOR STORE



def save_vector_store(vector_store: FAISS, directory: str) -> None:
    """
    Save FAISS index locally.
    """

    path = Path(directory)

    try:
        path.mkdir(parents=True, exist_ok=True)

        vector_store.save_local(str(path))

    except Exception:
        logger.exception("Failed to save FAISS vector store to: %s", path.resolve())

        raise

    logger.info("Vector store saved successfully: %s", path.resolve())



# LOAD VECTOR STORE



def load_vector_store(directory: str, embeddings: OllamaEmbeddings) -> FAISS:
    """
    Load an existing FAISS vector store.
    """

    path = Path(directory)

    index_file = path / "index.faiss"
    metadata_file = path / "index.pkl"

    if not index_file.exists():
        raise FileNotFoundError(f"FAISS index not found: {index_file.resolve()}")

    if not metadata_file.exists():
        raise FileNotFoundError(f"FAISS metadata not found: {metadata_file.resolve()}")

    logger.info("Loading FAISS vector store from: %s", path.resolve())

    try:
        vector_store = FAISS.load_local(
            str(path), embeddings, allow_dangerous_deserialization=True
        )

    except Exception:
        logger.exception("Failed to load FAISS vector store.")

        raise

    logger.info("FAISS vector store loaded successfully.")

    return vector_store



# RETRIEVE DOCUMENTS



def retrieve_documents(vector_store: FAISS, query: str, k: int = TOP_K):
    """
    Retrieve the most relevant documents.
    """

    if not query or not query.strip():
        logger.warning("Empty retrieval query received.")

        raise ValueError("Query cannot be empty.")

    logger.info("Running retrieval query: %s", query)

    try:
        retriever = vector_store.as_retriever(search_kwargs={"k": k})

        retrieved_docs = retriever.invoke(query)

    except Exception:
        logger.exception("Retrieval failed.")

        raise

    logger.info("Retrieved %d documents.", len(retrieved_docs))

    return retrieved_docs


def build_vector_store(chunks_file: str, vector_store_dir: str):
    """
    Build and persist the vector store from final chunks.

    If a vector store already exists, it will be loaded
    instead of generating embeddings again.
    """

    logger.info("Starting vector store build: %s", chunks_file)

    try:
        
        # Create embedding model
        

        embeddings = create_embeddings()

        vector_store_path = Path(vector_store_dir)

        index_file = vector_store_path / "index.faiss"
        metadata_file = vector_store_path / "index.pkl"

        
        # Existing vector store
        

        if index_file.exists() and metadata_file.exists():
            logger.info("Existing vector store found. Loading it.")

            vector_store = load_vector_store(
                directory=vector_store_dir, embeddings=embeddings
            )

            logger.info("Existing vector store loaded successfully.")

            return vector_store

        
        # Create new vector store
        

        logger.info("No existing vector store found.")

        documents = load_documents(chunks_file)

        logger.info("Creating embeddings for %d documents.", len(documents))

        vector_store = create_vector_store(documents=documents, embeddings=embeddings)

        
        # Save locally
        

        save_vector_store(vector_store=vector_store, directory=vector_store_dir)

        logger.info("Vector store created and saved successfully.")

        return vector_store

    except Exception:
        logger.exception("Failed to build vector store.")

        raise



# PRINT RESULTS



def display_results(retrieved_docs: List[Document]) -> None:

    print("\n" + "=" * 70)

    print("RETRIEVED DOCUMENTS")

    print("=" * 70)

    for index, document in enumerate(retrieved_docs, start=1):
        print(f"\n--- RESULT {index} ---")

        print("\nMetadata:")

        print(document.metadata)

        print("\nContent:")

        print(document.page_content)

        print("-" * 70)



# MAIN



def main():

    logger.info("========== EMBEDDING PIPELINE STARTED ==========")

    try:
        
        # 1. Create embedding model
        

        embeddings = create_embeddings()

        vector_store_path = Path(VECTOR_STORE_DIR)

        
        # 2. Check whether vector store already exists
        

        index_exists = (vector_store_path / "index.faiss").exists()

        metadata_exists = (vector_store_path / "index.pkl").exists()

        if index_exists and metadata_exists:
            logger.info("Existing vector store detected.")

            vector_store = load_vector_store(
                directory=VECTOR_STORE_DIR, embeddings=embeddings
            )

        else:
            logger.info("No existing vector store found.")

            
            # 3. Load chunks
            

            documents = load_documents(CHUNKS_FILE)

            
            # 4. Create vectors
            

            vector_store = create_vector_store(
                documents=documents, embeddings=embeddings
            )

            
            # 5. Save vectors locally
            

            save_vector_store(vector_store=vector_store, directory=VECTOR_STORE_DIR)

        
        # 6. Test retrieval
        

        query = "students use which forms or services to request involving enrollment?"

        retrieved_docs = retrieve_documents(
            vector_store=vector_store, query=query, k=TOP_K
        )

        
        # 7. Display results
        

        display_results(retrieved_docs)

        logger.info("========== EMBEDDING PIPELINE COMPLETED ==========")

    except Exception:
        logger.exception("Embedding pipeline failed.")

        raise



# ENTRY POINT


if __name__ == "__main__":
    main()
