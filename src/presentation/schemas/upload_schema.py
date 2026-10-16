from pydantic import BaseModel, Field


class FileInformation(BaseModel):
    filename: str = Field(..., description="original file name")
    file_size: int = Field(..., description="size of the file")
    file_type: str = Field(..., description="detected/accepted file format")
    reason: str | None = Field(None, description="Reason for failed")


class UploadResponse(BaseModel):
    success: bool = Field(
        ..., description="Whether the given file sucessfully uploaded or not"
    )
    message: str = Field(..., description="A message to display user")
    uploaded_files: list[FileInformation] = Field(
        ..., description="list of sucessfully uploaded files"
    )
    failed_files: list[FileInformation] = Field(
        ..., description="list of failed uploaded files"
    )
