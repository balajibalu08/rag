import logging
from pathlib import Path

from src.dcoument_pipeline.chunk_split import refine_all_chunks
from src.dcoument_pipeline.document_chunking import create_chunks
from src.dcoument_pipeline.document_extraction import extract_folder_to_json
from src.dcoument_pipeline.embedding import build_vector_store

logger = logging.getLogger(__name__)


def run_document_pipeline(upload_folder: str | Path, output_folder: str | Path):
    """
    Run the complete document processing pipeline.

    Parameters
    --
    upload_folder:
        Folder containing user-uploaded PDF files.

    output_folder:
        Folder where extracted data, chunks and
        vector index will be stored.
    """

    upload_folder = Path(upload_folder)
    output_folder = Path(output_folder)

    # Validate upload folder

    if not upload_folder.exists():
        logger.error("Upload folder does not exist: %s", upload_folder)

        raise FileNotFoundError(f"Upload folder not found: {upload_folder}")

    if not upload_folder.is_dir():
        logger.error("Upload path is not a directory: %s", upload_folder)

        raise NotADirectoryError(f"Upload path is not a directory: {upload_folder}")

    # Find PDFs

    pdf_files = list(upload_folder.glob("*.pdf"))

    if not pdf_files:
        logger.error("No PDF files found in: %s", upload_folder)

        raise ValueError(f"No PDF files found in {upload_folder}")

    logger.info("Found %d PDF files in %s", len(pdf_files), upload_folder)

    # Create output directories

    raw_folder = output_folder / "raw_files"
    chunks_folder = output_folder / "chunks"
    vector_folder = output_folder / "vector_store"

    raw_folder.mkdir(parents=True, exist_ok=True)

    chunks_folder.mkdir(parents=True, exist_ok=True)

    vector_folder.mkdir(parents=True, exist_ok=True)

    extracted_json = raw_folder / "extracted_data.json"

    header_chunks_json = chunks_folder / "chunks.json"

    final_chunks_json = chunks_folder / "final_chunks.json"

    # STEP 1 — EXTRACTION

    logger.info("[1/4] Starting document extraction")

    extract_folder_to_json(folder_path=upload_folder, output_json_path=extracted_json)

    logger.info("[1/4] Document extraction completed")

    # STEP 2 — HEADER CHUNKING

    logger.info("[2/4] Starting document chunking")

    create_chunks(input_json=extracted_json, output_json=header_chunks_json)

    logger.info("[2/4] Document chunking completed")

    # STEP 3 — CHUNK REFINEMENT

    logger.info("[3/4] Starting chunk refinement")

    refine_all_chunks(input_path=header_chunks_json, output_path=final_chunks_json)

    logger.info("[3/4] Chunk refinement completed")

    # STEP 4 — EMBEDDING + VECTOR STORE

    logger.info("[4/4] Starting embedding and vector indexing")

    build_vector_store(chunks_file=final_chunks_json, vector_store_dir=vector_folder)

    logger.info("[4/4] Embedding and vector indexing completed")

    # RETURN PIPELINE RESULT

    result = {
        "uploaded_files": [file.name for file in pdf_files],
        "output_folder": str(output_folder.resolve()),
        "extracted_json": str(extracted_json.resolve()),
        "chunks_json": str(header_chunks_json.resolve()),
        "final_chunks_json": str(final_chunks_json.resolve()),
        "vector_store": str(vector_folder.resolve()),
    }

    logger.info("Document pipeline completed successfully")

    return result


if __name__ == "__main__":
    try:
        # User-uploaded document folder

        upload_folder = Path("./data/pdfs")

        # Output folder

        output_folder = Path("./data/processed/user_123")

        # Check upload folder

        if not upload_folder.exists():
            logger.error("Upload folder does not exist: %s", upload_folder.resolve())
            raise FileNotFoundError(f"Upload folder not found: {upload_folder}")

        if not upload_folder.is_dir():
            logger.error("Upload path is not a directory: %s", upload_folder.resolve())
            raise NotADirectoryError(f"Upload path is not a directory: {upload_folder}")

        # Check PDF files

        pdf_files = list(upload_folder.glob("*.pdf"))

        if not pdf_files:
            logger.warning("No PDF files found in: %s", upload_folder.resolve())
            raise ValueError("No PDF files found in upload folder.")

        logger.info("Found %d PDF files.", len(pdf_files))

        for pdf in pdf_files:
            logger.info("Input document: %s", pdf.name)

        # Run pipeline

        result = run_document_pipeline(
            upload_folder=upload_folder, output_folder=output_folder
        )

        # Display result

        print("\nPipeline completed successfully.")

        print(f"Processed files: {len(result['uploaded_files'])}")

        print(f"Vector store: {result['vector_store']}")

    except Exception:
        logger.exception("Document pipeline execution failed.")

        print("\nPipeline failed. Check the log file for details.")
