import json
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.config import config
from src.core.logger import logger

MAX_CHUNK_SIZE = config["Application"]["ingestion"]["chunking"]["spreadsheet"][
    "max_chunk_size"
]
CHUNK_OVERLAP = config["Application"]["ingestion"]["chunking"]["spreadsheet"][
    "chunk_overlap"
]


splitter = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def load_chunks(json_path: str) -> list[dict[str, Any]]:

    path = Path(json_path)

    if not path.exists():
        logger.error("Input JSON file does not exist: %s", path.resolve())

        raise FileNotFoundError(f"Input JSON file not found: {path.resolve()}")

    if path.stat().st_size == 0:
        logger.error("Input JSON file is empty: %s", path.resolve())

        raise ValueError(f"Input JSON file is empty: {path.resolve()}")

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

    except json.JSONDecodeError as exc:
        logger.exception("Invalid JSON in file: %s", path.resolve())

        raise ValueError("Input JSON contains invalid JSON.") from exc

    if not isinstance(data, list):
        raise TypeError("Expected JSON root to contain a list of chunks.")

    return data


def validate_chunk(chunk: dict[str, Any], index: int) -> bool:

    if not isinstance(chunk, dict):
        logger.warning("Chunk at index %d is not a dictionary. Skipping.", index)

        return False

    required_fields = ["chunk_id", "document_name", "content"]

    missing_fields = [field for field in required_fields if field not in chunk]

    if missing_fields:
        logger.warning(
            "Chunk at index %d is missing fields: %s.", index, missing_fields
        )

        return False

    if not isinstance(chunk["content"], str):
        logger.warning("Chunk %s has non-string content. Skipping.", chunk["chunk_id"])

        return False

    if not chunk["content"].strip():
        logger.warning("Chunk %s has empty content. Skipping.", chunk["chunk_id"])

        return False

    return True


def refine_chunk(chunk: dict[str, Any]) -> list[dict[str, Any]]:

    chunk_id = chunk["chunk_id"]
    content = chunk["content"].strip()

    if len(content) <= MAX_CHUNK_SIZE:
        refined_chunk = dict(chunk)

        metadata = dict(refined_chunk.get("metadata", {}))

        metadata.update(
            {
                "chunk_size": len(content),
                "refined": False,
            }
        )

        refined_chunk["metadata"] = metadata

        return [refined_chunk]

    logger.info(
        "Oversized spreadsheet chunk detected: %s (%d characters).",
        chunk_id,
        len(content),
    )

    smaller_chunks = splitter.split_text(content)

    refined_chunks = []

    total_parts = len(smaller_chunks)

    for part_number, text in enumerate(smaller_chunks, start=1):
        text = text.strip()

        if not text:
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

        refined_chunks.append(
            {
                "chunk_id": (f"{chunk_id}_part_{part_number}"),
                "document_name": chunk["document_name"],
                "content": text,
                "metadata": metadata,
            }
        )

    return refined_chunks


def refine_all_chunks(input_path: str, output_path: str) -> list[dict[str, Any]]:

    logger.info("========== SPREADSHEET CHUNK REFINEMENT STARTED ==========")

    chunks = load_chunks(input_path)

    final_chunks = []

    for index, chunk in enumerate(chunks):
        chunk_id = (
            chunk.get("chunk_id", f"index_{index}")
            if isinstance(chunk, dict)
            else f"index_{index}"
        )

        try:
            if not validate_chunk(chunk, index):
                continue

            refined_chunks = refine_chunk(chunk)

            final_chunks.extend(refined_chunks)

        except Exception:  # noqa: BLE001 - Continue refining the remaining chunks.
            logger.exception("Failed to process spreadsheet chunk: %s", chunk_id)

    output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(final_chunks, file, indent=2, ensure_ascii=False)

    remaining_oversized = sum(
        1 for chunk in final_chunks if len(chunk.get("content", "")) > MAX_CHUNK_SIZE
    )

    logger.info("Original chunks : %d", len(chunks))

    logger.info("Final chunks    : %d", len(final_chunks))

    logger.info("Still oversized : %d", remaining_oversized)

    logger.info("Output file     : %s", output_path.resolve())

    logger.info("========== SPREADSHEET CHUNK REFINEMENT COMPLETED ==========")

    return final_chunks
