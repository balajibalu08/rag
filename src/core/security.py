import os

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
