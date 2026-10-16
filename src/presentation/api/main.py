from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.presentation.api.routes_chat import router as chat_router
from src.presentation.api.routes_upload import router as upload_router

app = FastAPI(
    title="RAG API",
)

STATIC_DIRECTORY = Path(__file__).parent / "static"

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIRECTORY),
    name="static",
)
app.include_router(upload_router)
app.include_router(chat_router)

UPLOAD_UI_PATH = STATIC_DIRECTORY / "index.html"


@app.get("/", tags=["Root"])
async def root() -> FileResponse:
    return FileResponse(UPLOAD_UI_PATH)
