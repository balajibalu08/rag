import json
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.config import config
from src.core.logger import logger

ROWS_PER_CHUNK = config["Application"]["ingestion"]["chunking"]["spreadsheet"][
    "rows_per_chunk"
]
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


def load_spreadsheet_data(json_path: str) -> list[dict[str, Any]]:

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
        raise ValueError("Expected JSON root to contain a list.")

    logger.info("Successfully loaded %d spreadsheets.", len(data))

    return data


def row_to_text(columns: list[str], row: dict[str, Any]) -> str:

    values = []

    for column in columns:
        value = row.get(column)

        if value is None:
            value = ""

        values.append(f"{column}: {value}")

    return " | ".join(values)


def create_semantic_chunks(sheet: dict[str, Any]) -> list[dict[str, Any]]:

    sheet_name = sheet["sheet_name"]
    columns = sheet.get("columns", [])
    rows = sheet.get("rows", [])

    chunks = []

    if not rows:
        return chunks

    for start in range(0, len(rows), ROWS_PER_CHUNK):
        end = min(start + ROWS_PER_CHUNK, len(rows))

        selected_rows = rows[start:end]

        row_texts = []

        for row_number, row in enumerate(selected_rows, start=start + 1):
            text = row_to_text(columns, row)

            row_texts.append(f"Row {row_number}: {text}")

        content = f"Sheet: {sheet_name}\nColumns: {', '.join(columns)}\n\n" + "\n".join(
            row_texts
        )

        chunks.append(
            {
                "content": content,
                "sheet_name": sheet_name,
                "start_row": start + 1,
                "end_row": end,
            }
        )

    return chunks


def chunk_spreadsheet(spreadsheet: dict[str, Any]) -> list[dict[str, Any]]:

    file_name = spreadsheet["file_name"]

    all_chunks = []

    for sheet in spreadsheet.get("sheets", []):
        semantic_chunks = create_semantic_chunks(sheet)

        for index, chunk in enumerate(semantic_chunks, start=1):
            chunk_id = f"{Path(file_name).stem}_{sheet['sheet_name']}_chunk_{index}"

            all_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "document_name": file_name,
                    "content": chunk["content"],
                    "metadata": {
                        "source": file_name,
                        "file_type": spreadsheet["file_type"],
                        "sheet_name": chunk["sheet_name"],
                        "start_row": chunk["start_row"],
                        "end_row": chunk["end_row"],
                        "columns": sheet.get("columns", []),
                        "spreadsheet_metadata": spreadsheet.get("metadata", {}),
                        "sheet_metadata": sheet.get("metadata", {}),
                    },
                }
            )

    logger.info(
        "Created %d semantic spreadsheet chunks for %s", len(all_chunks), file_name
    )

    return all_chunks


def create_chunks(input_json: str, output_json: str) -> list[dict[str, Any]]:

    logger.info("========== SPREADSHEET CHUNKING STARTED ==========")

    spreadsheets = load_spreadsheet_data(input_json)

    all_chunks = []

    for spreadsheet in spreadsheets:
        logger.info("Chunking spreadsheet: %s", spreadsheet["file_name"])

        chunks = chunk_spreadsheet(spreadsheet)

        all_chunks.extend(chunks)

    output_path = Path(output_json)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(all_chunks, file, indent=2, ensure_ascii=False)

    logger.info("Total spreadsheet chunks: %d", len(all_chunks))

    logger.info("Saved to: %s", output_path.resolve())

    logger.info("========== SPREADSHEET CHUNKING COMPLETED ==========")

    return all_chunks
