import os
import tempfile
from pathlib import Path
from tempfile import SpooledTemporaryFile

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.core.config import config
from src.core.logger import logger
from src.core.security import validate_file_content, validate_file_extension
from src.mcp.server import mcp
from src.models.upload import FileInformation, UploadResponse

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
)


UPLOAD_DIRECTORY = Path(
    config["Application"]["file_upload_settings"]["upload_directory"]
).resolve()
MAX_FILE_SIZE_BYTES = (
    config["Application"]["file_upload_settings"]["max_file_size"] * 1024 * 1024
)
ALLOWED_FILE_TYPES = [
    f".{file_type.lstrip('.')}"
    for file_type in config["Application"]["file_upload_settings"]["allowed_file_types"]
]


def reserve_upload_path(filename: str) -> Path:
    """Choose an unused filename without overwriting an existing upload."""
    original_path = Path(filename)
    stem = original_path.stem
    suffix = original_path.suffix
    number = 0

    while True:
        if number == 0:
            candidate_name = filename
        else:
            candidate_name = f"{stem} ({number}){suffix}"

        candidate = UPLOAD_DIRECTORY / candidate_name

        try:
            with candidate.open("xb"):
                pass
        except FileExistsError:
            number += 1
            continue

        return candidate


@router.get("/info")
async def upload_info() -> dict[str, int | list[str]]:
    return {
        "max_file_size_bytes": MAX_FILE_SIZE_BYTES,
        "allowed_file_types": ALLOWED_FILE_TYPES,
    }


@router.post("/", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),  # noqa: B008 - FastAPI request parameter.
) -> UploadResponse:
    """
    Upload multiple files and validate them before saving.
    """

    logger.info("File upload request received.")

    uploaded_files: list[FileInformation] = []
    failed_files: list[FileInformation] = []
    uploaded_paths: list[str] = []

    try:
        # Create the upload directory if needed.
        UPLOAD_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True,
        )

        for uploaded_file in files:
            filename = Path(uploaded_file.filename or "").name

            if not filename:
                logger.warning("Received a file without a filename.")

                failed_files.append(
                    FileInformation(
                        filename="unknown",
                        file_size=0,
                        file_type="unknown",
                        reason="Filename is missing.",
                    )
                )

                continue

            file_type = Path(filename).suffix.lower()

            if not validate_file_extension(filename):
                failed_files.append(
                    FileInformation(
                        filename=filename,
                        file_size=0,
                        file_type=file_type,
                        reason="File type is not allowed.",
                    )
                )

                continue

            file_path: Path | None = None
            staged_path: Path | None = None

            try:
                file_size = 0
                oversized = False

                with SpooledTemporaryFile(
                    max_size=1024 * 1024,
                    mode="w+b",
                ) as temporary_file:
                    while chunk := await uploaded_file.read(64 * 1024):
                        file_size += len(chunk)

                        if file_size > MAX_FILE_SIZE_BYTES:
                            oversized = True
                            break

                        temporary_file.write(chunk)

                    if oversized:
                        logger.warning(
                            "File size validation failed: %s",
                            filename,
                        )

                        failed_files.append(
                            FileInformation(
                                filename=filename,
                                file_size=file_size,
                                file_type=file_type,
                                reason="File size exceeds the allowed limit.",
                            )
                        )

                        continue

                    temporary_file.seek(0)
                    validation_error = validate_file_content(
                        filename,
                        temporary_file.read(),
                    )

                    if validation_error:
                        failed_files.append(
                            FileInformation(
                                filename=filename,
                                file_size=file_size,
                                file_type=file_type,
                                reason=validation_error,
                            )
                        )
                        continue

                    temporary_file.seek(0)

                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        prefix=".upload-",
                        suffix=".tmp",
                        dir=UPLOAD_DIRECTORY,
                        delete=False,
                    ) as staged_file:
                        staged_path = Path(staged_file.name)

                        while chunk := temporary_file.read(64 * 1024):
                            staged_file.write(chunk)

                file_path = reserve_upload_path(filename)
                os.replace(staged_path, file_path)
                staged_path = None

                if not file_path.is_file():
                    logger.warning(
                        "Uploaded file was not saved: %s",
                        filename,
                    )

                    failed_files.append(
                        FileInformation(
                            filename=filename,
                            file_size=file_size,
                            file_type=file_type,
                            reason="Failed to save the uploaded file.",
                        )
                    )

                    continue

                logger.info(
                    "File uploaded successfully: %s",
                    file_path.name,
                )

                uploaded_paths.append(str(file_path))

                uploaded_files.append(
                    FileInformation(
                        filename=file_path.name,
                        file_size=file_size,
                        file_type=file_type,
                        reason=None,
                    )
                )

            except OSError as exc:
                logger.exception(
                    "Failed to process uploaded file: %s",
                    filename,
                )

                if staged_path is not None:
                    staged_path.unlink(missing_ok=True)

                if file_path is not None:
                    file_path.unlink(missing_ok=True)

                failed_files.append(
                    FileInformation(
                        filename=filename,
                        file_size=0,
                        file_type=file_type,
                        reason=(
                            "Failed to save the file: "
                            f"{exc.strerror or 'an operating system error occurred'}."
                        ),
                    )
                )

        if uploaded_paths:
            try:
                ingestion_result = await mcp.call_tool(
                    "ingest_documents",
                    {"file_paths": uploaded_paths},
                )

                if isinstance(ingestion_result, tuple) and len(ingestion_result) == 2:
                    result_payload = ingestion_result[1]
                else:
                    result_payload = ingestion_result

                if not isinstance(result_payload, dict):
                    raise TypeError("The ingestion MCP tool returned an invalid response.")

                if result_payload.get("success") is not True:
                    raise RuntimeError("The ingestion MCP tool reported a failure.")

            except Exception as exc:
                logger.exception(
                    "Files were saved but MCP ingestion or vector-store refresh failed."
                )

                raise HTTPException(
                    status_code=500,
                    detail="Document indexing failed. Please try again.",
                ) from exc

        success = len(uploaded_files) > 0

        if success:
            message = "Files uploaded successfully."
        else:
            message = "No files were uploaded successfully."

        logger.info(
            "Upload completed. Successful: %d, Failed: %d",
            len(uploaded_files),
            len(failed_files),
        )

        return UploadResponse(
            success=success,
            message=message,
            uploaded_files=uploaded_files,
            failed_files=failed_files,
        )

    except Exception:
        logger.exception("File upload request failed.")
        raise
