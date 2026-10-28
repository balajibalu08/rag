from pydantic import BaseModel, Field


class File(BaseModel):
    file_path: str = Field(..., description="Path of a file")
    extension: str | None = Field(None, description="Extension of a file")


class Files(BaseModel):
    files: list[File] = Field(..., description="All successfully uploaded files")


class ChunkData(BaseModel):
    chunks: list[dict] = Field(..., description="All generated chunks")


class SheetData(BaseModel):
    sheet_name: str = Field(..., description="Name of the sheet")
    columns: list[str] = Field(..., description="Column names in the sheet")
    rows: list[dict] = Field(..., description="Rows from the sheet")
    metadata: dict[str, str | int | bool | None] = Field(
        default_factory=dict, description="Metadata of the sheet"
    )


class SpreadsheetData(BaseModel):
    file_name: str = Field(..., description="Name of the original spreadsheet")
    file_type: str = Field(..., description="Format of the spreadsheet")
    sheets: list[SheetData] = Field(
        ..., description="Sheets contained in the spreadsheet"
    )
    metadata: dict[str, str | int | bool | None] = Field(
        default_factory=dict, description="Metadata of the spreadsheet"
    )
