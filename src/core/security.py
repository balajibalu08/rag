import csv
import io
import json
import os
import zipfile
from pathlib import Path

from src.core.config import config
from src.core.logger import logger


def validate_file_extension(
    file_path: str,
    allowed_extensions: list[str] = config["Application"]["file_upload_settings"][
        "allowed_file_types"
    ],
) -> bool:
    """
    this function validates the given file name using allowed_extenstions list
    """
    logger.info("Validate_file_extenstion is initiated")
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    normalized_allowed = [
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in allowed_extensions
    ]

    return ext in normalized_allowed


def validate_file_content(filename: str, content: bytes) -> str | None:
    """Validate a file's contents against its configured extension."""
    extension = Path(filename).suffix.lower()

    if not validate_file_extension(filename):
        return "File type is not allowed."

    if not content:
        return "The file is empty."

    if extension == ".pdf":
        if b"%PDF-" not in content[:1024]:
            return "File content does not match the .pdf extension."
        return None

    if extension in {".docx", ".xlsx"}:
        required_member = (
            "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
        )

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = set(archive.namelist())
        except (OSError, zipfile.BadZipFile):
            return f"File content is not a valid {extension} document."

        if "[Content_Types].xml" not in members or required_member not in members:
            return f"File content does not match the {extension} extension."
        return None

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return f"File content is not valid UTF-8 for the {extension} extension."

    if "\x00" in decoded:
        return f"File content does not match the {extension} extension."

    if extension == ".json":
        try:
            json.loads(decoded)
        except json.JSONDecodeError:
            return "File content is not valid JSON."

    elif extension == ".csv":
        try:
            rows = csv.reader(io.StringIO(decoded), strict=True)
            next(rows, None)
            for _ in rows:
                pass
        except csv.Error:
            return "File content is not valid CSV."

    return None


def validate_file_size(
    file_path: str,
    max_file_size: int = config["Application"]["file_upload_settings"]["max_file_size"],
) -> bool:
    """
    this function validates the given file name is in under given size or not
    """
    file_size_bytes = os.path.getsize(file_path)
    max_size_bytes = max_file_size * 1024 * 1024  # Converting MB to bytes
    if file_size_bytes > max_size_bytes:
        file_size_mb = file_size_bytes / (1024 * 1024)
        logger.warning(
            f"File size ({file_size_mb:.2f}MB) exceeds the maximum limit of"
            f" {max_file_size}MB.",
        )
        return False
    logger.info("Validation successful!")
    return True
