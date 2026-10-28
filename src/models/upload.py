from pydantic import BaseModel, Field


class FileInformation(BaseModel):
    filename: str = Field(..., description="Original file name")
    file_size: int = Field(..., description="Size of the file")
    file_type: str = Field(..., description="Detected or accepted file format")
    reason: str | None = Field(None, description="Reason for failure")


class UploadResponse(BaseModel):
    success: bool = Field(
        ..., description="Whether any files were uploaded successfully"
    )
    message: str = Field(..., description="A message to display to the user")
    uploaded_files: list[FileInformation] = Field(
        ..., description="Successfully uploaded files"
    )
    failed_files: list[FileInformation] = Field(
        ..., description="Files that failed to upload"
    )
