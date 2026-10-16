from agent_framework import Executor, WorkflowContext, handler

from bussiness.chunking.spreadsheet_chunking import (
    chunk_spreadsheet,
)
from src.bussiness.chunking.document_chunking import (
    chunk_document,
)
from src.bussiness.ingestion.document_extraction import (
    DocumentData,
)
from src.bussiness.ingestion.models import (
    SpreadsheetData,
)
from src.core.logger import logger


class DocumentChunkExecutor(Executor):
    @handler
    async def chunk_document(self, document: DocumentData, ctx: WorkflowContext[list[dict]],):

        logger.info("Document chunk executor initiated")

        try:
            chunks = chunk_document(document.model_dump())

            if not chunks:
                logger.warning(f"No chunks created for: {document.file_name}")

                return

            await ctx.send_message(chunks)

            logger.info(
                f"Document chunking completed: "
                f"{document.file_name} "
                f"({len(chunks)} chunks)"
            )

        except Exception as e:
            logger.exception(
                f"Error while chunking document: {document.file_name} - {e}"
            )


class SpreadsheetChunkExecutor(Executor):
    @handler
    async def chunk_spreadsheet( self, spreadsheet: SpreadsheetData,ctx: WorkflowContext[list[dict]] ):

        logger.info("Spreadsheet chunk executor initiated")

        try:
            chunks = chunk_spreadsheet(spreadsheet.model_dump())

            if not chunks:
                logger.warning(f"No chunks created for: {spreadsheet.file_name}")

                return

            await ctx.send_message(chunks)

            logger.info(
                f"Spreadsheet chunking completed: "
                f"{spreadsheet.file_name} "
                f"({len(chunks)} chunks)"
            )

        except Exception as e:
            logger.exception(
                f"Error while chunking spreadsheet: {spreadsheet.file_name} - {e}"
            )
