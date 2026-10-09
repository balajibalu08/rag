Northbridge AI --- Document Intelligence Assistant

What the project does

Northbridge AI is a document-based chatbot. It searches information from
indexed PDF documents and uses a local Ollama language model to answer
questions. Answers can include source filenames and page references when
available.

What each file/folder does

frontend/app.py --- Runs the Streamlit chat interface.

src/dcoument_pipeline/rag.py --- Coordinates retrieval and answer
generation.

src/dcoument_pipeline/embedding.py --- Creates embeddings, loads
the FAISS index, and retrieves relevant document chunks.

src/model/rag_response_model.py --- Defines the expected answer
format (answer and sources).

src/utils/logger.py --- Configures application logging.

data/vector_store/ --- Stores the saved FAISS index
(index.faiss) and its metadata (index.pkl).

data/ --- Holds project data, such as source PDFs or processed
files, depending on your setup.

pyproject.toml --- Defines project dependencies and configuration.

uv.lock --- Locks dependency versions for reproducible
installation.

README.md --- Project instructions.

The source folder is currently named dcoument_pipeline in the code.
Keep that spelling unless you also update the imports.

How to run the project

1. Open the project folder

In PowerShell:

cd D:\RAG

2. Install dependencies

Run this from the folder containing pyproject.toml:

uv sync

3. Start Ollama and download the models

Make sure Ollama is running, then run:

ollama pull qwen2.5:3b
ollama pull qwen3-embedding:0.6b

If your code uses different model names, use those names instead.

4. Check the vector store

Confirm data/vector_store/ contains index.faiss and index.pkl. The
index must have been created using the embedding model configured in the
project. If the index does not exist, run your document-processing and
indexing pipeline first.

5. Start the chatbot

From D:\RAG, run:

uv run streamlit run frontend/app.py

Open the local address shown in the terminal, usually
http://localhost:8501.

6. Ask a question

Enter a question in the chat, for example:

What student services are available at the institute?

Which form is used for enrollment requests?

Compare academic advising and career guidance based on the documents.

How it produces an answer

You submit a question in the Streamlit interface.

The embedding model converts the question into a vector.

FAISS retrieves relevant chunks from the indexed PDFs.

The RAG code sends the retrieved text to the Ollama chat model.

The chatbot displays the generated answer and available source
references.

Current limitation

The PDF uploader in the interface currently selects files but does not
automatically process them or add them to FAISS. Only documents already
included in the vector store can be searched.