import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.utils.logger import logger



# CONFIGURATION


INPUT_JSON = "./data/chunks/chunks.json"
OUTPUT_JSON = "./data/chunks/final_chunks.json"

MAX_CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200



# TEXT SPLITTER


splitter = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)



# LOAD CHUNKS



def load_chunks(json_path: str) -> List[Dict[str, Any]]:
    """
    Load header-based chunks from JSON.
    """

    path = Path(json_path)

    if not path.exists():
        logger.error("Input JSON file does not exist: %s", path.resolve())
        raise FileNotFoundError(f"Input JSON file not found: {path.resolve()}")

    if path.stat().st_size == 0:
        logger.error("Input JSON file is empty: %s", path.resolve())
        raise ValueError(f"Input JSON file is empty: {path.resolve()}")

    logger.info("Loading chunks from: %s", path.resolve())

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

    except json.JSONDecodeError as exc:
        logger.exception("Invalid JSON in file: %s", path.resolve())

        raise ValueError("Input JSON contains invalid JSON.") from exc

    if not isinstance(data, list):
        logger.error("Expected JSON root to be a list.")

        raise ValueError("Expected JSON root to contain a list of chunks.")

    logger.info("Successfully loaded %d chunks.", len(data))

    return data



# VALIDATE CHUNK



def validate_chunk(chunk: Dict[str, Any], index: int) -> bool:
    """
    Validate a chunk before refinement.
    """

    if not isinstance(chunk, dict):
        logger.warning("Chunk at index %d is not a dictionary. Skipping.", index)

        return False

    required_fields = ["chunk_id", "document_name", "content"]

    missing_fields = [field for field in required_fields if field not in chunk]

    if missing_fields:
        logger.warning(
            "Chunk at index %d is missing fields: %s. Skipping.", index, missing_fields
        )

        return False

    if not isinstance(chunk["content"], str):
        logger.warning("Chunk %s has non-string content. Skipping.", chunk["chunk_id"])

        return False

    if not chunk["content"].strip():
        logger.warning("Chunk %s has empty content. Skipping.", chunk["chunk_id"])

        return False

    return True



# REFINE ONE CHUNK



def refine_chunk(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Split an oversized chunk into smaller chunks.

    Chunks below MAX_CHUNK_SIZE are kept unchanged.
    """

    chunk_id = chunk["chunk_id"]
    content = chunk["content"].strip()

    content_length = len(content)

    
    # Chunk is already within the limit
    

    if content_length <= MAX_CHUNK_SIZE:
        logger.debug(
            "Chunk %s is within size limit: %d characters.", chunk_id, content_length
        )

        refined_chunk = dict(chunk)

        metadata = dict(refined_chunk.get("metadata", {}))

        metadata.update({"chunk_size": content_length, "refined": False})

        refined_chunk["metadata"] = metadata

        return [refined_chunk]

    
    # Chunk is oversized
    

    logger.info(
        "Oversized chunk detected: %s (%d characters).", chunk_id, content_length
    )

    try:
        smaller_chunks = splitter.split_text(content)

    except Exception:
        logger.exception("Failed to split chunk: %s", chunk_id)

        raise

    if not smaller_chunks:
        logger.error("No sub-chunks generated for: %s", chunk_id)

        return []

    refined_chunks = []

    total_parts = len(smaller_chunks)

    for part_number, text in enumerate(smaller_chunks, start=1):
        text = text.strip()

        if not text:
            logger.warning("Empty sub-chunk generated from %s. Skipping.", chunk_id)

            continue

        metadata = dict(chunk.get("metadata", {}))

        metadata.update(
            {
                "parent_chunk_id": chunk_id,
                "part_number": part_number,
                "total_parts": total_parts,
                "chunk_size": len(text),
                "refined": True,
            }
        )

        refined_chunk = {
            "chunk_id": (f"{chunk_id}_part_{part_number}"),
            "document_name": chunk["document_name"],
            "content": text,
            "metadata": metadata,
        }

        refined_chunks.append(refined_chunk)

    logger.info("Chunk %s split into %d parts.", chunk_id, len(refined_chunks))

    return refined_chunks



# REFINE ALL CHUNKS



def refine_all_chunks(input_path: str, output_path: str) -> List[Dict[str, Any]]:
    """
    Refine all chunks and save the final result.
    """

    logger.info("========== CHUNK REFINEMENT STARTED ==========")

    
    # Load
    

    try:
        chunks = load_chunks(input_path)

    except Exception:
        logger.exception("Unable to load input chunks.")

        raise

    final_chunks = []

    processed_count = 0
    skipped_count = 0
    failed_count = 0
    oversized_count = 0

    
    # Process each chunk
    

    for index, chunk in enumerate(chunks):
        chunk_id = (
            chunk.get("chunk_id", f"index_{index}")
            if isinstance(chunk, dict)
            else f"index_{index}"
        )

        try:
            
            # Validate
            

            if not validate_chunk(chunk, index):
                skipped_count += 1
                continue

            processed_count += 1

            
            # Check size
            

            if len(chunk["content"]) > MAX_CHUNK_SIZE:
                oversized_count += 1

            
            # Refine
            

            refined_chunks = refine_chunk(chunk)

            final_chunks.extend(refined_chunks)

        except Exception:
            failed_count += 1

            logger.exception("Failed to process chunk: %s", chunk_id)

    
    # Validate output directory
    

    output_path = Path(output_path)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    except OSError:
        logger.exception(
            "Unable to create output directory: %s", output_path.parent.resolve()
        )

        raise

    
    # Save final chunks
    

    try:
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(final_chunks, file, indent=2, ensure_ascii=False)

    except OSError:
        logger.exception("Failed to write output JSON: %s", output_path.resolve())

        raise

    
    # Final validation
    

    remaining_oversized = sum(
        1 for chunk in final_chunks if len(chunk.get("content", "")) > MAX_CHUNK_SIZE
    )

    
    # Statistics
    

    logger.info("========== CHUNK REFINEMENT COMPLETED ==========")

    logger.info("Original chunks     : %d", len(chunks))

    logger.info("Processed chunks    : %d", processed_count)

    logger.info("Skipped chunks      : %d", skipped_count)

    logger.info("Failed chunks       : %d", failed_count)

    logger.info("Oversized chunks    : %d", oversized_count)

    logger.info("Final chunks        : %d", len(final_chunks))

    logger.info("Still oversized     : %d", remaining_oversized)

    logger.info("Output file         : %s", output_path.resolve())

    return final_chunks



# MAIN


if __name__ == "__main__":
    try:
        refine_all_chunks(input_path=INPUT_JSON, output_path=OUTPUT_JSON)

    except Exception:
        logger.exception("Chunk refinement pipeline failed.")

        raise
