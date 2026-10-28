import asyncio

from agent_framework import Executor, WorkflowContext, handler

from src.bussiness.chunking.chunk_executor import (
    DocumentChunkExecutor,
    SpreadsheetChunkExecutor,
)
from src.bussiness.ingestion.filter import filter_files
from src.bussiness.ingestion.pdf_extractor import (
    DocumentExtractor,
)
from src.bussiness.ingestion.spreedsheet_executor import (
    SpreadsheetExecutor,
)
from src.bussiness.ingestion.text_extractor import TXTExecutor
from src.core.logger import logger
from src.models.ingestion import ChunkData, Files


class SpreadsheetPipelineExecutor(Executor):
    @handler
    async def process(
        self,
        files: Files,
        ctx: WorkflowContext[ChunkData],
    ):

        logger.info("Spreadsheet pipeline initiated")

        spreadsheet_files = filter_files(files, [".xlsx", ".csv"])

        if not spreadsheet_files:
            logger.info("No spreadsheet files found")

            return

        logger.info(f"Spreadsheet files found: {len(spreadsheet_files)}")

        spreadsheet_files = Files(files=spreadsheet_files)

        extractor = SpreadsheetExecutor(id="spreadsheet-extractor")

        chunker = SpreadsheetChunkExecutor(id="spreadsheet-chunker")

        extracted_data = []

        class ExtractionContext:
            async def send_message(self, message):

                extracted_data.append(message)

        extraction_ctx = ExtractionContext()

        # SpreadsheetExecutor accepts multiple files
        await extractor.extract_spreadsheet(spreadsheet_files, extraction_ctx)

        if not extracted_data:
            logger.warning("No spreadsheet data extracted")

            return

        final_chunks = []

        class ChunkContext:
            async def send_message(self, message):

                final_chunks.append(message)

        chunk_ctx = ChunkContext()

        chunk_tasks = []

        for document in extracted_data:
            chunk_tasks.append(chunker.chunk_spreadsheet(document, chunk_ctx))

        await asyncio.gather(*chunk_tasks)

        chunks = []

        for result in final_chunks:
            if isinstance(result, ChunkData):
                chunks.extend(result.chunks)

            elif isinstance(result, list):
                chunks.extend(result)

        if chunks:
            await ctx.send_message(ChunkData(chunks=chunks))

        logger.info(f"Spreadsheet pipeline completed: {len(chunks)} chunks")


class DocumentPipelineExecutor(Executor):
    @handler
    async def process(
        self,
        files: Files,
        ctx: WorkflowContext[ChunkData],
    ):

        logger.info("Document pipeline initiated")

        document_files = filter_files(
            files,
            [
                ".pdf",
                ".docx",
                ".txt",
                ".json",
            ],
        )

        if not document_files:
            logger.info("No document files found")

            return

        logger.info(f"Document files found: {len(document_files)}")

        document_files = Files(files=document_files)

        extracted_data = []

        class ExtractionContext:
            async def send_message(self, message):

                extracted_data.append(message)

        extraction_ctx = ExtractionContext()

        extraction_tasks = []

        doc_files = []
        txt_files = []

        for file in document_files.files:
            if file.extension in {".pdf", ".docx"}:
                doc_files.append(file)

            elif file.extension in {".txt", ".json"}:
                txt_files.append(file)

        if doc_files:
            extractor = DocumentExtractor(id="document-extractor")

            extraction_tasks.append(
                extractor.extract_documents(Files(files=doc_files), extraction_ctx)
            )

        if txt_files:
            extractor = TXTExecutor(id="txt-extractor")

            extraction_tasks.append(
                extractor.extract_txt(Files(files=txt_files), extraction_ctx)
            )

        if extraction_tasks:
            await asyncio.gather(*extraction_tasks)

        if not extracted_data:
            logger.warning("No document data extracted")

            return

        chunker = DocumentChunkExecutor(id="document-chunker")

        final_chunks = []

        class ChunkContext:
            async def send_message(self, message):

                final_chunks.append(message)

        chunk_ctx = ChunkContext()

        chunk_tasks = []

        for document in extracted_data:
            chunk_tasks.append(chunker.chunk_document(document, chunk_ctx))

        await asyncio.gather(*chunk_tasks)

        chunks = []

        for result in final_chunks:
            if isinstance(result, ChunkData):
                chunks.extend(result.chunks)

            elif isinstance(result, list):
                chunks.extend(result)

        if chunks:
            await ctx.send_message(ChunkData(chunks=chunks))

        logger.info(f"Document pipeline completed: {len(chunks)} chunks")


class ConcurrentIngestionExecutor(Executor):
    @handler
    async def process(
        self,
        files: Files,
        ctx: WorkflowContext[ChunkData],
    ):

        logger.info("Concurrent ingestion started")

        spreadsheet_pipeline = SpreadsheetPipelineExecutor(id="spreadsheet-pipeline")

        document_pipeline = DocumentPipelineExecutor(id="document-pipeline")

        spreadsheet_results = []
        document_results = []

        class SpreadsheetContext:
            async def send_message(self, message):

                spreadsheet_results.append(message)

        class DocumentContext:
            async def send_message(self, message):

                document_results.append(message)

        spreadsheet_ctx = SpreadsheetContext()
        document_ctx = DocumentContext()

        await asyncio.gather(
            spreadsheet_pipeline.process(files, spreadsheet_ctx),
            document_pipeline.process(files, document_ctx),
        )

        all_chunks = []

        for result in spreadsheet_results:
            if isinstance(result, ChunkData):
                all_chunks.extend(result.chunks)

        for result in document_results:
            if isinstance(result, ChunkData):
                all_chunks.extend(result.chunks)

        if all_chunks:
            await ctx.send_message(ChunkData(chunks=all_chunks))

        logger.info(f"Concurrent ingestion completed: {len(all_chunks)} total chunks")
