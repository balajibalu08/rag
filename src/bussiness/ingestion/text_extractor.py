from pathlib import Path

from agent_framework import Executor, WorkflowContext, handler

from src.bussiness.ingestion.document_extraction import (
    DocumentData,
    DocumentElement,
)
from src.bussiness.ingestion.models import Files
from src.core.logger import logger


class TXTExecutor(Executor):
    @handler
    async def extract_txt(
        self,
        files: Files,
        ctx: WorkflowContext[DocumentData],
    ):

        for file in files.files:
            logger.info(f"TXT extraction started: {file.file_path}")

            file_path = Path(file.file_path)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()

                document = DocumentData(
                    file_path=str(file_path),
                    file_name=file_path.name,
                    num_pages=1,
                    file_size_bytes=file_path.stat().st_size,
                    elements=[
                        DocumentElement(
                            element_id=1,
                            type="TEXT",
                            content=text,
                            page_number=1,
                        )
                    ],
                )

                await ctx.send_message(document)

                logger.info(f"TXT extraction completed: {file_path.name}")

            except Exception:
                logger.exception(f"TXT extraction failed: {file_path}")

                raise
