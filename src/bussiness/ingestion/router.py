import asyncio
from pathlib import Path

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from src.bussiness.ingestion.embedding_executor import EmbeddingExecutor
from src.bussiness.ingestion.pipeline import (
    DocumentPipelineExecutor,
    SpreadsheetPipelineExecutor,
)
from src.core.config import config
from src.core.logger import logger
from src.core.security import (
    validate_file_content,
    validate_file_extension,
    validate_file_size,
)
from src.models.ingestion import ChunkData, File, Files

_ingestion_lock = asyncio.Lock()


class FileLoaderExecutor(Executor):
    @handler
    async def load_files(
        self,
        incoming_files: Files,
        ctx: WorkflowContext[Files],
    ):

        logger.info("File loader executor initiated")

        upload_folder = Path(
            config["Application"]["file_upload_settings"]["upload_directory"]
        )

        if incoming_files.files:
            files = incoming_files.files

        else:
            if not upload_folder.exists():
                logger.warning(f"Upload folder does not exist: {upload_folder}")

                await ctx.send_message(Files(files=[]))

                return

            if not upload_folder.is_dir():
                logger.error(f"Upload path is not a directory: {upload_folder}")

                await ctx.send_message(Files(files=[]))

                return

            files = []

            for file_path in upload_folder.iterdir():
                if not file_path.is_file():
                    continue

                extension = file_path.suffix.lower()

                if not validate_file_extension(str(file_path)):
                    continue

                if not validate_file_size(str(file_path)):
                    continue

                try:
                    content = file_path.read_bytes()
                except OSError:
                    logger.exception("Could not read uploaded file: %s", file_path)
                    continue

                if error := validate_file_content(str(file_path), content):
                    logger.warning("Skipping invalid upload %s: %s", file_path, error)
                    continue

                files.append(File(file_path=str(file_path), extension=extension))

            logger.info(f"Found {len(files)} files in upload folder")

        await ctx.send_message(Files(files=files))

        logger.info("File loader executor completed")


class ChunkCollectorExecutor(Executor):
    @handler
    async def collect_chunks(
        self,
        data: ChunkData,
        ctx: WorkflowContext[ChunkData],
    ):

        logger.info("Chunk collector executor initiated")

        await ctx.send_message(data)

        logger.info(f"Collected {len(data.chunks)} chunks")


file_loader = FileLoaderExecutor(id="file loader")

document_pipeline = DocumentPipelineExecutor(id="document pipeline")

spreadsheet_pipeline = SpreadsheetPipelineExecutor(id="spreadsheet pipeline")

chunk_collector = ChunkCollectorExecutor(id="chunk collector")

embedding_executor = EmbeddingExecutor(id="embedding executor")


workflow_builder = WorkflowBuilder(start_executor=file_loader)


workflow_builder.add_edge(file_loader, document_pipeline)

workflow_builder.add_edge(file_loader, spreadsheet_pipeline)


workflow_builder.add_edge(document_pipeline, chunk_collector)

workflow_builder.add_edge(spreadsheet_pipeline, chunk_collector)


workflow_builder.add_edge(chunk_collector, embedding_executor)


workflow = workflow_builder.build()


async def ingest_uploaded_files(
    file_paths: list[str],
) -> None:
    validated_files = []
    for file_path in file_paths:
        path = Path(file_path)
        if not path.is_file():
            raise ValueError(f"Uploaded file does not exist: {path}")
        if not validate_file_size(str(path)):
            raise ValueError(
                f"Uploaded file exceeds the configured size limit: {path.name}"
            )
        try:
            content = path.read_bytes()
        except OSError as exc:
            logger.exception("Could not read uploaded file: %s", path)
            raise RuntimeError(f"Could not read uploaded file: {path.name}") from exc
        if error := validate_file_content(str(path), content):
            raise ValueError(f"Invalid uploaded file {path.name}: {error}")
        validated_files.append(File(file_path=str(path), extension=path.suffix.lower()))

    files = Files(files=validated_files)

    if not files.files:
        raise ValueError("At least one uploaded file path is required for ingestion.")

    logger.info(
        "Starting ingestion for %d uploaded files.",
        len(files.files),
    )

    try:
        async with _ingestion_lock:
            await workflow.run(files)

    except Exception as exc:
        logger.exception("Ingestion failed for the uploaded file batch.")

        raise RuntimeError("The uploaded files could not be ingested.") from exc

    logger.info("Uploaded file batch ingestion completed.")


async def main():

    logger.info("========== INGESTION WORKFLOW STARTED ==========")

    files = Files(files=[])

    try:
        result = await workflow.run(files)

        print("\nWorkflow completed")

        print(result)

        logger.info("========== INGESTION WORKFLOW COMPLETED ==========")

    except Exception:
        logger.exception("Ingestion workflow failed")

        raise


if __name__ == "__main__":
    asyncio.run(main())
