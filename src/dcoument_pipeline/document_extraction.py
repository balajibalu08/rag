import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from docling.document_converter import DocumentConverter
from docling_core.types.doc import DocItemLabel, TextItem, TableItem, PictureItem


@dataclass
class DocumentElement:
    element_id: int
    type: str  # "title", "heading", "paragraph", "list_item", "table", "document_index", "picture", "code", "caption"
    content: str  # Direct text string or canonical Markdown string
    page_number: int
    section_path: List[str]  # e.g., ["Academic Regulations", "Table of Contents"]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentData:
    file_name: str
    file_path: str
    num_pages: int
    file_size_bytes: int
    elements: List[DocumentElement] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert object into a clean JSON-serializable dictionary."""
        return asdict(self)


def extract_table_headers(table_md: str, df: pd.DataFrame) -> List[str]:
    """
    Extracts canonical table headers.
    If DataFrame generated default numeric column names ([0, 1, 2]),
    parses actual header labels from the Markdown string.
    """
    raw_cols = list(df.columns)

    # Check if headers are default numeric indices [0, 1, 2...] or ["0", "1", "2"...]
    is_numeric_default = all(isinstance(c, int) or str(c).isdigit() for c in raw_cols)

    if not is_numeric_default and len(raw_cols) > 0:
        return [str(c) for c in raw_cols]

    # Fallback: Extract top row directly from Markdown table
    if table_md:
        lines = [line.strip() for line in table_md.strip().split("\n") if line.strip()]
        if lines:
            header_line = lines[0]
            # Split by pipe '|' and clean whitespace
            headers = [col.strip() for col in header_line.split("|")]
            # Filter out empty trailing/leading splits from | col1 | col2 |
            headers = [h for h in headers if h]
            if headers:
                return headers

    return [str(c) for c in raw_cols]


# Extraction Engine


def extract_folder_to_json(
    folder_path: str | Path, output_json_path: str | Path = "extracted_data.json"
) -> List[DocumentData]:
    folder = Path(folder_path)
    converter = DocumentConverter()

    # Filter out lock files (~$), hidden files, and empty files
    pdf_files = [
        f
        for f in folder.glob("*.pdf")
        if f.is_file() and not f.name.startswith("~$") and f.stat().st_size > 0
    ]

    if not pdf_files:
        print(f"No valid PDF files found in {folder.resolve()}")
        return []

    extracted_documents: List[DocumentData] = []
    conversion_results = converter.convert_all(pdf_files, raises_on_error=False)

    for result in conversion_results:
        if result.status.name != "SUCCESS":
            print(f"Skipping failed document: {result.input.file.name}")
            continue

        doc = result.document

        doc_data = DocumentData(
            file_name=result.input.file.name,
            file_path=str(result.input.file.resolve()),
            num_pages=len(doc.pages) if hasattr(doc, "pages") else 0,
            file_size_bytes=result.input.file.stat().st_size,
        )

        element_counter = 1
        section_stack: List[str] = []

        # Iterate through elements in true linear reading order
        for item, level in doc.iterate_items():
            page_no = item.prov[0].page_no if hasattr(item, "prov") and item.prov else 1
            label_name = item.label.name if hasattr(item, "label") else "TEXT"

            # 1. Ignore running headers and footers
            if item.label in (DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER):
                continue

            # 2. Special Handling: Document Index / Table of Contents
            if (
                item.label == DocItemLabel.DOCUMENT_INDEX
                or label_name == "DOCUMENT_INDEX"
            ):
                content_str = (
                    item.export_to_markdown(doc=doc)
                    if hasattr(item, "export_to_markdown")
                    else (
                        item.text.strip()
                        if hasattr(item, "text")
                        else "[Document Index]"
                    )
                )

                doc_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type="document_index",
                        content=content_str,
                        page_number=page_no,
                        section_path=list(section_stack),
                        metadata={"docling_label": label_name, "is_navigation": True},
                    )
                )
                element_counter += 1

            # 3. Headings & Section Hierarchy Stack
            elif item.label in (DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER):
                heading_text = item.text.strip() if hasattr(item, "text") else ""
                if not heading_text:
                    continue

                if level == 0:
                    section_stack = [heading_text]
                else:
                    section_stack = section_stack[:level]
                    section_stack.append(heading_text)

                elem_type = "title" if item.label == DocItemLabel.TITLE else "heading"
                doc_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type=elem_type,
                        content=heading_text,
                        page_number=page_no,
                        section_path=list(section_stack),
                        metadata={"docling_label": label_name, "level": level},
                    )
                )
                element_counter += 1

            # 4. Standard Text Elements (Paragraphs, Lists, Code, Captions)
            elif isinstance(item, TextItem) or hasattr(item, "text"):
                text_str = item.text.strip()
                if not text_str:
                    continue

                elem_type = "paragraph"
                if item.label == DocItemLabel.LIST_ITEM:
                    elem_type = "list_item"
                elif item.label == DocItemLabel.CAPTION:
                    elem_type = "caption"
                elif item.label == DocItemLabel.CODE:
                    elem_type = "code"

                doc_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type=elem_type,
                        content=text_str,
                        page_number=page_no,
                        section_path=list(section_stack),
                        metadata={"docling_label": label_name},
                    )
                )
                element_counter += 1

            # 5. Knowledge Tables (Canonical Markdown + Clean Header Metadata)
            elif isinstance(item, TableItem) or item.label == DocItemLabel.TABLE:
                table_md = item.export_to_markdown(doc=doc)
                df: pd.DataFrame = item.export_to_dataframe(doc=doc)

                # Recover proper headers if DataFrame returned numeric indices [0, 1, 2]
                recovered_headers = extract_table_headers(table_md, df)

                table_metadata = {
                    "docling_label": label_name,
                    "headers": recovered_headers,
                    "num_rows": len(df),
                    "num_cols": len(df.columns),
                    "caption": item.caption.text
                    if hasattr(item, "caption") and item.caption
                    else None,
                    "is_navigation": False,
                }

                doc_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type="table",
                        content=table_md,  # Markdown is the canonical truth for table content
                        page_number=page_no,
                        section_path=list(section_stack),
                        metadata=table_metadata,
                    )
                )
                element_counter += 1

            # 6. Pictures / Figures
            elif isinstance(item, PictureItem) or item.label == DocItemLabel.PICTURE:
                caption_text = (
                    item.caption.text
                    if hasattr(item, "caption") and item.caption
                    else ""
                )
                doc_data.elements.append(
                    DocumentElement(
                        element_id=element_counter,
                        type="picture",
                        content=caption_text or "[Image]",
                        page_number=page_no,
                        section_path=list(section_stack),
                        metadata={"docling_label": label_name, "caption": caption_text},
                    )
                )
                element_counter += 1

        extracted_documents.append(doc_data)

    # Save to JSON
    output_path = Path(output_json_path)
    json_payload = [doc.to_dict() for doc in extracted_documents]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2, ensure_ascii=False)

    print(f"\nProcessed {len(extracted_documents)} documents.")
    print(f"Dataset saved to: {output_path.resolve()}")

    return extracted_documents


if __name__ == "__main__":
    extract_folder_to_json(
        folder_path="./data/pdfs",
        output_json_path=".//data//raw_files//extracted_data.json",
    )
