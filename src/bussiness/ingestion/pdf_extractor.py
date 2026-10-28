from agent_framework import Executor, WorkflowContext, handler

from src.bussiness.ingestion.document_extraction import extract_document
from src.bussiness.ingestion.filter import filter_files
from src.core.logger import logger
from src.models.document import DocumentData
from src.models.ingestion import Files


class DocumentExtractor(Executor):
    @handler
    async def extract_documents(
        self,
        files: Files,
        ctx: WorkflowContext[DocumentData],
    ):

        logger.info("Document extractor initiated")

        selected_files = filter_files(
            files=files,
            extensions=[".pdf", ".docx"],
        )

        for file in selected_files:
            try:
                document_data = extract_document(file.file_path)

                if document_data is None:
                    logger.warning(f"Document extraction failed: {file.file_path}")

                    continue

                await ctx.send_message(document_data)

                logger.info(f"Document extraction completed: {file.file_path}")

            except Exception as e:  # noqa: BLE001 - Isolate parser failures per file.
                logger.exception(f"Error in document extractor: {file.file_path} - {e}")
