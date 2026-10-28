from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.mcp.server import mcp
from src.presentation.api.routes_chat import router as chat_router
from src.presentation.api.routes_upload import router as upload_router

mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="RAG API", lifespan=lifespan)

STATIC_DIRECTORY = Path(__file__).parent / "static"

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIRECTORY),
    name="static",
)
app.include_router(upload_router)
app.include_router(chat_router)
app.mount("/mcp", mcp_app, name="mcp")

UPLOAD_UI_PATH = STATIC_DIRECTORY / "index.html"


@app.get("/", tags=["Root"])
async def root() -> FileResponse:
    return FileResponse(UPLOAD_UI_PATH)
