import sys
import asyncio
import shutil
import threading
from pathlib import Path

# Resolve the project root: D:\RAG
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Add the project root to Python's import path
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import streamlit as st

from src.dcoument_pipeline.pipeline import run_document_pipeline
from src.dcoument_pipeline.embedding import (
    create_embeddings,
    load_vector_store,
)
from src.dcoument_pipeline.rag import RAGAgent

DATA_DIR = PROJECT_DIR / "data"

# Temporary directory containing only the PDFs being indexed
UPLOAD_DIR = DATA_DIR / "uploads" / "current_batch"

# The pipeline will create data/vector_store under this directory.
OUTPUT_DIR = DATA_DIR

# Must match the vector-store directory used by RAGAgent.
VECTOR_STORE_DIR = DATA_DIR / "vector_store"


# ============================================================
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Document Intelligence",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DARK THEME
# ============================================================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #0f1117;
        color: #f9fafb;
    }

    [data-testid="stSidebar"] {
        background-color: #15171e;
        border-right: 1px solid #292c36;
    }

    [data-testid="stHeader"] {
        background-color: #0f1117;
    }

    h1, h2, h3, p, label {
        color: #f9fafb;
    }

    .main-title {
        font-size: 2.3rem;
        font-weight: 750;
        margin-bottom: 0.25rem;
        color: #f9fafb;
    }

    .subtitle {
        color: #9296a5;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }

    .info-card {
        background-color: #171922;
        border: 1px solid #292c36;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 12px;
    }

    .info-label {
        color: #9296a5;
        font-size: 0.9rem;
    }

    .info-value {
        color: #f9fafb;
        font-size: 1.2rem;
        font-weight: 650;
    }

    .stButton > button {
        background-color: #7c3aed;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.55rem 1rem;
        font-weight: 600;
    }

    .stButton > button:hover {
        background-color: #6d28d9;
        color: white;
        border: none;
    }

    [data-testid="stChatMessage"] {
        background-color: #171922;
        border: 1px solid #292c36;
        border-radius: 12px;
        padding: 12px;
    }

    [data-testid="stFileUploader"] {
        background-color: #171922;
        border: 1px dashed #454957;
        border-radius: 12px;
        padding: 12px;
    }

    code {
        color: #c4b5fd;
    }

    hr {
        border-color: #292c36;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# PERSISTENT ASYNCIO EVENT LOOP
# ============================================================

@st.cache_resource
def get_event_loop():
    """
    Create one persistent event loop for asynchronous agent calls.
    """

    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(
        target=run_loop,
        name="RAGAsyncLoop",
        daemon=True,
    )

    thread.start()

    return loop


def run_async(coroutine):
    """
    Execute a coroutine on the persistent event loop.
    """

    loop = get_event_loop()

    if loop.is_closed():
        coroutine.close()
        raise RuntimeError("The RAG event loop has been closed.")

    future = asyncio.run_coroutine_threadsafe(coroutine, loop)

    return future.result()


# ============================================================
# INITIALIZE RAG AGENT
# ============================================================

@st.cache_resource
def get_rag_agent():
    agent = RAGAgent(
        model_id="qwen2.5:3b",
        vector_store_directory=str(VECTOR_STORE_DIR),
    )

    agent.initialize_session()

    return agent
def refresh_vector_store():
    """
    Reload the persisted FAISS index after document indexing.

    This prevents the running agent from continuing to use
    an older in-memory vector store.
    """

    embeddings = create_embeddings()

    updated_vector_store = load_vector_store(
        directory=str(VECTOR_STORE_DIR),
        embeddings=embeddings,
    )

    agent = get_rag_agent()

    # Update the vector store used by the existing RAG agent.
    agent.vector_store = updated_vector_store

    return agent


# ============================================================
# SESSION STATE
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "indexed_files" not in st.session_state:
    st.session_state.indexed_files = []

if "last_index_result" not in st.session_state:
    st.session_state.last_index_result = None


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="main-title">📚 Document Intelligence</div>
    <div class="subtitle">
        Upload your PDFs, index their contents, and ask questions
        using retrieval-augmented generation.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR: DOCUMENT UPLOAD AND INDEXING
# ============================================================

with st.sidebar:
    st.header("📂 Knowledge Base")

    st.write(
        "Upload PDF documents and index their contents "
        "to make them searchable."
    )

    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if uploaded_files:
        st.markdown("### Selected documents")

        for uploaded_file in uploaded_files:
            file_size_mb = uploaded_file.size / (1024 * 1024)

            st.caption(
                f"📄 {uploaded_file.name} "
                f"({file_size_mb:.2f} MB)"
            )

    st.divider()

    index_button = st.button(
        "⚡ Index PDFs",
        use_container_width=True,
        disabled=not uploaded_files,
    )

    if index_button:
        try:
            # Create the temporary upload directory.
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

            # Remove files from the previous upload batch.
            # This prevents accidentally indexing all previous
            # uploads again during every indexing operation.
            for existing_file in UPLOAD_DIR.iterdir():
                if existing_file.is_dir():
                    shutil.rmtree(existing_file)
                else:
                    existing_file.unlink()

            # Save the selected PDFs.
            saved_files = []

            for uploaded_file in uploaded_files:
                filename = Path(uploaded_file.name).name

                if not filename.lower().endswith(".pdf"):
                    continue

                destination = UPLOAD_DIR / filename

                with destination.open("wb") as file:
                    file.write(uploaded_file.getbuffer())

                if destination.stat().st_size == 0:
                    destination.unlink()
                    raise ValueError(
                        f"The uploaded file is empty: {filename}"
                    )

                saved_files.append(destination)

            if not saved_files:
                st.error("No valid PDF files were uploaded.")

            else:
                # Execute the existing document pipeline.
                with st.spinner(
                    "Extracting, chunking, embedding, and indexing PDFs..."
                ):
                    result = run_document_pipeline(
                        upload_folder=UPLOAD_DIR,
                        output_folder=OUTPUT_DIR,
                    )

                # Reload the vector store used by the RAG agent.
                with st.spinner("Refreshing the RAG knowledge base..."):
                    refresh_vector_store()

                st.session_state.indexed_files = [
                    file.name for file in saved_files
                ]

                st.session_state.last_index_result = result

                st.success(
                    f"Successfully indexed {len(saved_files)} PDF(s)."
                )

                st.rerun()

        except Exception as exc:
            st.error(
                "PDF indexing failed. Check the application logs "
                "for the underlying error."
            )

            st.exception(exc)

    # Show the latest indexing result.
    if st.session_state.last_index_result:
        st.divider()

        st.markdown("### Latest indexing result")

        st.success("Indexing completed")

        st.caption(
            f"Files: "
            f"{len(st.session_state.last_index_result['uploaded_files'])}"
        )

        st.caption(
            f"Vector store: {st.session_state.last_index_result['vector_store']}"
        )

    st.divider()

    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# ============================================================
# MAIN CONTENT: KNOWLEDGE BASE STATUS
# ============================================================

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <div class="info-card">
            <div class="info-label">Embedding model</div>
            <div class="info-value">qwen3-embedding:0.6b</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
        <div class="info-card">
            <div class="info-label">Language model</div>
            <div class="info-value">qwen2.5:3b</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()

st.subheader("💬 Ask your documents")

st.caption(
    "Ask questions about your indexed PDFs. "
    "Answers are generated using retrieved document content."
)


# ============================================================
# DISPLAY CHAT HISTORY
# ============================================================

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message.get("sources"):
            with st.expander("📑 Sources"):
                for source in message["sources"]:
                    st.write(f"- {source}")


# ============================================================
# CHAT INPUT
# ============================================================

query = st.chat_input(
    "Ask a question about your indexed documents..."
)

if query:
    # Display the user's message.
    st.session_state.messages.append(
        {
            "role": "user",
            "content": query,
        }
    )

    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching documents and generating an answer..."):
                agent = get_rag_agent()

                response = run_async(
                    agent.route_request(query)
                )

            # Support a Pydantic response or a dictionary.
            if hasattr(response, "answer"):
                answer = response.answer
                sources = response.sources

            elif isinstance(response, dict):
                answer = response.get(
                    "answer",
                    "The agent did not return an answer.",
                )

                sources = response.get("sources", [])

            else:
                answer = str(response)
                sources = []

            st.markdown(answer)

            if sources:
                with st.expander("📑 Sources"):
                    for source in sources:
                        st.write(f"- {source}")

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                    "sources": sources,
                }
            )

        except Exception:
            st.error(
                "The RAG agent failed to generate an answer. "
                "Check the application logs for details."
            )

            st.exception(
                __import__("sys").exc_info()[1]
            )