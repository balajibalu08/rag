# RAG Knowledge Base

The application accepts PDF, DOCX, TXT, CSV, JSON, and XLSX uploads, validates
their contents, indexes them, and answers questions using the indexed documents.

## API features

- `POST /chat/` returns the existing JSON chat response.
- `POST /chat/stream` streams `delta` and `reset` events as Server-Sent Events,
  followed by a `complete` event containing the final answer and critic metadata.
- The MCP Streamable HTTP endpoint is available at `/mcp/`. The
  `retrieve_documents` tool returns relevant passages and metadata from the
  vector store for the supplied query. The separate `ingest_documents` tool
  runs the existing ingestion workflow. The upload UI saves files and invokes
  this MCP tool; the chat agent only uses `retrieve_documents` for questions.
  Set `Application.mcp.server_url` in `config/settings.yaml` or override it
  with `RAG_MCP_SERVER_URL` when the API is hosted at another URL.
- After successful ingestion via the API or MCP, the service refreshes its
  cached vector store and clears server-side conversation context. API uploads
  also clear the browser chat history.

The configured embedding model is defined once in
`Application.embedding_settings.model` in `config/settings.yaml`.

## Run with Docker Compose

Docker Compose builds the API/MCP application image, starts Ollama, downloads
the configured chat and embedding models, and then starts the application:

```powershell
docker compose up --build
```

Open `http://localhost:8000` to use the upload and chat UI. The MCP endpoint
is available at `http://localhost:8000/mcp/`. The first startup can take a
while because Ollama downloads the models. Compose persists Ollama models,
uploaded/processed files, and the vector index in named volumes.

The application container uses `OLLAMA_HOST=http://ollama:11434` to reach the
Ollama service. For a separately hosted Ollama instance, set `OLLAMA_HOST` to
its reachable URL and run the API image without the bundled Ollama services.