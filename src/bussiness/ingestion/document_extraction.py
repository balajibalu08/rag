from pathlib import Path

import pandas as pd
from docling.document_converter import DocumentConverter
from docling_core.types.doc import (
    DocItemLabel,
    PictureItem,
    TableItem,
    TextItem,
)

from src.core.config import config
from src.core.logger import logger
from src.models.document import DocumentData, DocumentElement


def extract_table_headers(table_md: str, df: pd.DataFrame) -> list[str]:

    headers = []
    # extracting Headers from tables
    lines = table_md.splitlines()

    for line in lines:
        if line.strip().startswith("|"):
            parts = [item.strip() for item in line.strip().strip("|").split("|")]

            if parts and not all(set(item) <= {"-", ":"} for item in parts):
                headers = parts
                break

    if not headers and not df.empty:
        headers = [str(column) for column in df.columns]

    return headers


def extract_document(file_path: str | Path) -> DocumentData | None:

    logger.info("Document extraction initiated")

    try:
        file_path = Path(file_path)

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")

            return None

        if not file_path.is_file():
            logger.warning(f"Given path is not a file: {file_path}")

            return None

        converter = DocumentConverter()

        result = converter.convert(file_path, raises_on_error=False)

        if result.status.name != "SUCCESS":
            logger.warning(f"Docling failed to process {file_path.name}")

            return None

        doc = result.document

        document_data = DocumentData(
            file_name=file_path.name,
            file_path=str(file_path.resolve()),
            num_pages=(len(doc.pages) if hasattr(doc, "pages") else 0),
            file_size_bytes=file_path.stat().st_size,
        )

        element_counter = 1
        section_stack: list[str] = []

        for item, level in doc.iterate_items():
            page_number = (
                item.prov[0].page_no if hasattr(item, "prov") and item.prov else 1
            )

            label_name = item.label.name if hasattr(item, "label") else "TEXT"

            # Ignore headers and footers
            if item.label in (
                DocItemLabel.PAGE_HEADER,
                DocItemLabel.PAGE_FOOTER,
            ):
                continue

            # Document index / table of contents
            if (
                item.label == DocItemLabel.DOCUMENT_INDEX
                or label_name == "DOCUMENT_INDEX"
            ):
                content = (
                    item.export_to_markdown(doc=doc)
                    if hasattr(item, "export_to_markdown")
                    else "[Document Index]"
                )

                document_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type="document_index",
                        content=content,
                        page_number=page_number,
                        section_path=list(section_stack),
                        metadata={
                            "docling_label": label_name,
                            "is_navigation": True,
                        },
                    )
                )

                element_counter += 1
                continue

            # Title and section headings
            if item.label in (
                DocItemLabel.TITLE,
                DocItemLabel.SECTION_HEADER,
            ):
                heading_text = item.text.strip() if hasattr(item, "text") else ""

                if not heading_text:
                    continue

                if level == 0:
                    section_stack = [heading_text]

                else:
                    section_stack = section_stack[:level]

                    section_stack.append(heading_text)

                element_type = (
                    "title" if item.label == DocItemLabel.TITLE else "heading"
                )

                document_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type=element_type,
                        content=heading_text,
                        page_number=page_number,
                        section_path=list(section_stack),
                        metadata={
                            "docling_label": label_name,
                            "level": level,
                        },
                    )
                )

                element_counter += 1
                continue

            # Normal text
            if isinstance(item, TextItem):
                text = item.text.strip()

                if not text:
                    continue

                element_type = "paragraph"

                if item.label == DocItemLabel.LIST_ITEM:
                    element_type = "list_item"

                elif item.label == DocItemLabel.CAPTION:
                    element_type = "caption"

                elif item.label == DocItemLabel.CODE:
                    element_type = "code"

                document_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type=element_type,
                        content=text,
                        page_number=page_number,
                        section_path=list(section_stack),
                        metadata={
                            "docling_label": label_name,
                        },
                    )
                )

                element_counter += 1
                continue

            # Tables
            if isinstance(item, TableItem) or item.label == DocItemLabel.TABLE:
                table_markdown = item.export_to_markdown(doc=doc)

                df = item.export_to_dataframe(doc=doc)

                headers = extract_table_headers(table_markdown, df)

                table_metadata = {
                    "docling_label": label_name,
                    "headers": headers,
                    "num_rows": len(df),
                    "num_cols": len(df.columns),
                    "caption": (
                        item.caption.text
                        if hasattr(item, "caption") and item.caption
                        else None
                    ),
                    "is_navigation": False,
                }

                document_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type="table",
                        content=table_markdown,
                        page_number=page_number,
                        section_path=list(section_stack),
                        metadata=table_metadata,
                    )
                )

                element_counter += 1
                continue

            # Pictures / images
            if isinstance(item, PictureItem) or item.label == DocItemLabel.PICTURE:
                caption_text = (
                    item.caption.text
                    if hasattr(item, "caption") and item.caption
                    else ""
                )

                document_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type="picture",
                        content=(caption_text or "[Image]"),
                        page_number=page_number,
                        section_path=list(section_stack),
                        metadata={
                            "docling_label": label_name,
                            "caption": caption_text,
                        },
                    )
                )

                element_counter += 1

        logger.info(f"Document extraction completed: {file_path.name}")

        return document_data

    except Exception as e:  # noqa: BLE001 - Docling can raise parser-specific errors.
        logger.exception(f"Error while extracting {file_path}: {e}")

        return None


def extract_documents_from_upload_directory() -> list[DocumentData]:

    logger.info("Starting document extraction from upload directory")

    documents = []

    try:
        upload_directory = Path(
            config["Application"]["file_upload_settings"]["upload_directory"]
        )

        processed_directory = Path(
            config["Application"]["file_upload_settings"]["processed_directory"]
        )

        upload_directory.mkdir(parents=True, exist_ok=True)

        processed_directory.mkdir(parents=True, exist_ok=True)

        for file_path in upload_directory.iterdir():
            if not file_path.is_file():
                continue

            document_data = extract_document(file_path)

            if document_data is not None:
                documents.append(document_data)

        logger.info(f"Total documents extracted: {len(documents)}")

        return documents

    except OSError as e:
        logger.exception(f"Error while extracting documents from upload directory: {e}")

        return documents
