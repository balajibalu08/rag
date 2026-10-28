from pydantic import BaseModel, Field


class DocumentElement(BaseModel):
    element_id: int
    type: str
    content: str
    page_number: int
    section_path: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class DocumentData(BaseModel):
    file_name: str
    file_path: str
    num_pages: int
    file_size_bytes: int
    elements: list[DocumentElement] = Field(default_factory=list)
