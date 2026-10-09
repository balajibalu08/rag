import asyncio
import logging
import sys
import threading
from pathlib import Path

import streamlit as st



# CONFIGURATION


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

UPLOAD_DIRECTORY = PROJECT_ROOT / "data" / "uploads"
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# PAGE CONFIGURATION


st.set_page_config(
    page_title="Northbridge AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)



# CUSTOM UI



# CUSTOM DARK THEME


st.markdown(
    """
    <style>
    /* =========================================
       GLOBAL THEME
    ========================================= */

    .stApp {
        background-color: #0f1117;
        color: #e5e7eb;
    }

    .block-container {
        max-width: 1050px;
        padding: 2rem 2rem 7rem 2rem;
    }

    header[data-testid="stHeader"] {
        background: rgba(15, 17, 23, 0.95);
    }

    footer,
    #MainMenu {
        visibility: hidden;
    }

    /* =========================================
       SIDEBAR
    ========================================= */

    section[data-testid="stSidebar"] {
        background-color: #15171e;
        border-right: 1px solid #282b36;
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 1.5rem;
    }

    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label {
        color: #c4c7d0;
    }

    .brand {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 1.5rem;
    }

    .brand-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 42px;
        height: 42px;
        border-radius: 12px;
        background: linear-gradient(135deg, #7c3aed, #4f46e5);
        color: white;
        font-size: 22px;
    }

    .brand-name {
        font-size: 19px;
        font-weight: 700;
        color: #f9fafb;
        margin: 0;
    }

    .brand-caption {
        font-size: 12px;
        color: #9296a5;
        margin-top: 3px;
    }

    .sidebar-label {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        color: #9296a5;
        margin-top: 1.5rem;
        margin-bottom: 0.7rem;
    }

    .sidebar-note {
        font-size: 12px;
        line-height: 1.7;
        color: #9296a5;
    }

    /* =========================================
       MAIN HEADING
    ========================================= */

    .page-heading {
        text-align: center;
        margin-top: 5rem;
        margin-bottom: 0.7rem;
        color: #f9fafb;
        font-size: 38px;
        font-weight: 650;
        letter-spacing: -1.2px;
    }

    .page-subheading {
        text-align: center;
        color: #9296a5;
        font-size: 15px;
        line-height: 1.8;
        margin-bottom: 2.5rem;
    }

    .section-label {
        color: #9296a5;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.8px;
        margin-top: 1.2rem;
        margin-bottom: 0.8rem;
    }

    /* =========================================
       SUGGESTION CARDS
    ========================================= */

    div.stButton > button {
        width: 100%;
        min-height: 75px;
        padding: 14px 16px;

        background: #171922;
        color: #e5e7eb;

        border: 1px solid #2b2e3b;
        border-radius: 14px;

        font-size: 13px;
        font-weight: 500;
        text-align: left;

        transition:
            background 0.2s ease,
            border-color 0.2s ease,
            transform 0.2s ease;
    }

    div.stButton > button:hover {
        background: #202231;
        border-color: #7c3aed;
        color: #ffffff;
        transform: translateY(-2px);
    }

    div.stButton > button:focus {
        box-shadow: none;
        border-color: #8b5cf6;
        color: #ffffff;
    }

    /* =========================================
       CHAT MESSAGES
    ========================================= */

    div[data-testid="stChatMessage"] {
        background: transparent;
        border: none;
        padding: 1.1rem 0.5rem;
        gap: 12px;
    }

    div[data-testid="stChatMessage"] p {
        color: #e5e7eb;
        font-size: 15px;
        line-height: 1.9;
    }

    div[data-testid="stChatMessage"] li {
        color: #d1d5db;
        line-height: 1.9;
    }

    div[data-testid="stChatMessage"] h1,
    div[data-testid="stChatMessage"] h2,
    div[data-testid="stChatMessage"] h3 {
        color: #f9fafb;
    }

    div[data-testid="stChatMessage"] code {
        background: #242632;
        color: #c4b5fd;
        border-radius: 5px;
    }

    /* =========================================
       CHAT INPUT
    ========================================= */

    div[data-testid="stChatInput"] {
        background: #191b25;
        border: 1px solid #303342;
        border-radius: 18px;

        box-shadow: 0 5px 25px rgba(0, 0, 0, 0.15);
    }

    div[data-testid="stChatInput"]:focus-within {
        border-color: #7c3aed;
        box-shadow: 0 0 0 1px #7c3aed;
    }

    div[data-testid="stChatInput"] textarea {
        color: #f9fafb;
        font-size: 15px;
        caret-color: #a78bfa;
    }

    div[data-testid="stChatInput"] textarea::placeholder {
        color: #85899a;
    }

    /* =========================================
       SOURCES
    ========================================= */

    div[data-testid="stExpander"] {
        background: #171922;
        border: 1px solid #2b2e3b;
        border-radius: 12px;
    }

    div[data-testid="stExpander"] summary {
        color: #d1d5db;
    }

    div[data-testid="stExpander"] p {
        color: #c4c7d0;
    }

    /* =========================================
       STATUS INDICATOR
    ========================================= */

    .status-indicator {
        display: flex;
        align-items: center;
        gap: 9px;

        padding: 11px 12px;

        background: #191b25;
        border: 1px solid #2b2e3b;
        border-radius: 10px;

        font-size: 13px;
        color: #e5e7eb;
    }

    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #34d399;
        box-shadow: 0 0 8px rgba(52, 211, 153, 0.4);
    }

    .status-dot-error {
        background: #f87171;
        box-shadow: 0 0 8px rgba(248, 113, 113, 0.4);
    }

    /* =========================================
       INFORMATION BOXES
    ========================================= */

    div[data-testid="stAlert"] {
        background: #191b25;
        border: 1px solid #303342;
        border-radius: 12px;
        color: #e5e7eb;
    }

    .bottom-caption {
        text-align: center;
        color: #777c8d;
        font-size: 12px;
        margin-top: 1.5rem;
        line-height: 1.7;
    }

    /* =========================================
       FILE UPLOADER
    ========================================= */

    div[data-testid="stFileUploader"] {
        background: #191b25;
        border: 1px dashed #3a3d4d;
        border-radius: 12px;
        padding: 10px;
    }

    div[data-testid="stFileUploader"] section {
        background: #191b25;
    }

    div[data-testid="stFileUploader"] button {
        background: #242632;
        color: #e5e7eb;
        border: 1px solid #3a3d4d;
    }

    /* =========================================
       DIVIDERS
    ========================================= */

    hr {
        border-color: #292c38;
    }

    /* =========================================
       SCROLLBAR
    ========================================= */

    ::-webkit-scrollbar {
        width: 7px;
    }

    ::-webkit-scrollbar-track {
        background: #0f1117;
    }

    ::-webkit-scrollbar-thumb {
        background: #353847;
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: #555a6d;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

# PERSISTENT ASYNCIO EVENT LOOP


@st.cache_resource
def get_event_loop():
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

    logger.info("Persistent asyncio event loop started.")

    return loop


def run_async(coroutine):
    loop = get_event_loop()

    if loop.is_closed():
        coroutine.close()
        raise RuntimeError(
            "The persistent asyncio event loop has been closed."
        )

    future = asyncio.run_coroutine_threadsafe(
        coroutine,
        loop,
    )

    return future.result()



# RAG INITIALIZATION


@st.cache_resource(show_spinner=False)
def get_rag_agent():
    from src.dcoument_pipeline.rag import RAGAgent

    logger.info("Initializing RAG agent.")

    return RAGAgent()


def initialize_session_state():

    defaults = {
        "messages": [],
        "rag_agent": None,
        "rag_initialization_error": None,
        "pending_query": None,
    }

    for key, value in defaults.items():

        if key not in st.session_state:
            st.session_state[key] = value


def initialize_rag_agent():

    if st.session_state.rag_agent is not None:
        return

    try:

        with st.spinner("Starting document assistant..."):

            st.session_state.rag_agent = get_rag_agent()

        st.session_state.rag_initialization_error = None

    except Exception as exc:

        logger.exception("RAG initialization failed.")

        st.session_state.rag_initialization_error = str(exc)



# SIDEBAR


def render_sidebar():

    with st.sidebar:

        # Brand

        st.markdown(
            """
            <div class="brand">
                <div class="brand-icon">📚</div>
                <div>
                    <div class="brand-name">Northbridge AI</div>
                    <div class="brand-caption">
                        Document Intelligence
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # New conversation

        if st.button(
            "＋  New conversation",
            use_container_width=True,
        ):

            st.session_state.messages = []
            st.session_state.pending_query = None

            st.rerun()

        # System status

        st.markdown(
            '<div class="sidebar-label">System status</div>',
            unsafe_allow_html=True,
        )

        if st.session_state.rag_agent is not None:

            st.markdown(
                """
                <div class="status-indicator">
                    <span class="status-dot"></span>
                    <span>Assistant ready</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.caption("Model: Ollama")
            st.caption("Retrieval: FAISS")

        else:

            st.markdown(
                """
                <div class="status-indicator">
                    <span class="status-dot-error status-dot"></span>
                    <span>Assistant unavailable</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.session_state.rag_initialization_error:

                with st.expander("Initialization details"):

                    st.code(
                        st.session_state.rag_initialization_error
                    )

            if st.button(
                "Retry connection",
                use_container_width=True,
            ):

                get_rag_agent.clear()

                st.session_state.rag_agent = None
                st.session_state.rag_initialization_error = None

                st.rerun()

        st.divider()

        # Document upload

        st.markdown(
            '<div class="sidebar-label">Your documents</div>',
            unsafe_allow_html=True,
        )

        uploaded_files = st.file_uploader(
            "Add PDF files",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            help="Choose PDF documents.",
        )

        if uploaded_files:

            st.caption(
                f"{len(uploaded_files)} PDF file(s) selected"
            )

            for uploaded_file in uploaded_files:

                st.markdown(
                    f"📄 {uploaded_file.name}"
                )

            st.info(
                "PDF indexing is not connected yet. "
                "Selected files are not searchable until "
                "the document-processing pipeline is integrated."
            )

        else:

            st.markdown(
                """
                <div class="sidebar-note">
                    Upload support is being prepared.
                    The current assistant searches documents
                    already indexed in FAISS.
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()

        # Conversation controls

        st.markdown(
            '<div class="sidebar-label">Conversation</div>',
            unsafe_allow_html=True,
        )

        st.caption(
            f"{len(st.session_state.messages)} messages "
            "in this session"
        )

        if st.button(
            "Clear conversation",
            use_container_width=True,
        ):

            st.session_state.messages = []
            st.session_state.pending_query = None

            st.rerun()

        # Footer

        st.markdown(
            """
            <br>
            <div class="sidebar-note">
                Built with Python, Streamlit, Ollama and FAISS.
            </div>
            """,
            unsafe_allow_html=True,
        )



# WELCOME SCREEN


SUGGESTIONS = [
    (
        "🎓",
        "Student services",
        "What student services are available at the institute?",
    ),
    (
        "📝",
        "Enrollment",
        "Which form is used for enrollment requests?",
    ),
    (
        "📖",
        "Student policies",
        "What information is available about student policies?",
    ),
    (
        "🔎",
        "Explore documents",
        "Summarize the main information in the student handbook.",
    ),
]


def render_welcome_screen():

    st.markdown(
        """
        <div class="page-heading">
            What would you like to know?
        </div>

        <div class="page-subheading">
            Ask questions about your documents.
            <br>
            Get answers grounded in your indexed knowledge base.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-label">GET STARTED</div>',
        unsafe_allow_html=True,
    )

    first_row = st.columns(2)

    second_row = st.columns(2)

    columns = first_row + second_row

    for index, (icon, title, question) in enumerate(SUGGESTIONS):

        with columns[index]:

            if st.button(
                f"{icon}  {title}\n\n{question}",
                key=f"suggestion_{index}",
                use_container_width=True,
            ):

                st.session_state.pending_query = question

                st.rerun()

    st.markdown(
        """
        <div class="bottom-caption">
            Answers are generated from your indexed documents.
            Always verify important information against the source.
        </div>
        """,
        unsafe_allow_html=True,
    )



# CHAT HISTORY


def render_chat_history():

    for message in st.session_state.messages:

        with st.chat_message(message["role"]):

            st.markdown(message["content"])

            sources = message.get("sources", [])

            if message["role"] == "assistant" and sources:

                with st.expander(
                    f"📚 Sources ({len(sources)})"
                ):

                    for source in sources:

                        st.markdown(f"- `{source}`")



# CHAT PROCESSING


def process_query(query: str):

    query = query.strip()

    if not query:
        return

    # Save the user message.

    st.session_state.messages.append(
        {
            "role": "user",
            "content": query,
            "sources": [],
        }
    )

    # Show the question.

    with st.chat_message("user"):

        st.markdown(query)

    # Check agent availability.

    rag_agent = st.session_state.rag_agent

    if rag_agent is None:

        answer = (
            "The assistant is currently unavailable. "
            "Please check the system status and try again."
        )

        with st.chat_message("assistant"):

            st.error(answer)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer,
                "sources": [],
            }
        )

        return

    # Generate response.

    with st.chat_message("assistant"):

        with st.spinner("Searching your documents..."):

            try:

                response = run_async(
                    rag_agent.route_request(query)
                )

                answer = response.answer
                sources = response.sources or []

                st.markdown(answer)

                if sources:

                    with st.expander(
                        f"📚 Sources ({len(sources)})"
                    ):

                        for source in sources:

                            st.markdown(f"- `{source}`")

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "sources": sources,
                    }
                )

                logger.info(
                    "Response generated successfully."
                )

            except Exception as exc:

                logger.exception(
                    "Failed to generate the RAG response."
                )

                answer = (
                    "I couldn't generate a response this time. "
                    "Please try again."
                )

                st.error(answer)

                with st.expander("Technical details"):

                    st.code(
                        f"{type(exc).__name__}: {exc}"
                    )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "sources": [],
                    }
                )



# MAIN APPLICATION


def main():

    initialize_session_state()

    initialize_rag_agent()

    render_sidebar()

    # Welcome screen or existing conversation.

    if not st.session_state.messages:

        render_welcome_screen()

    else:

        st.markdown(
            """
            <div style="
                font-size: 24px;
                font-weight: 650;
                color: #202123;
                margin-bottom: 1.5rem;
            ">
                Northbridge AI
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_chat_history()

    # Chat input.

    query = st.chat_input(
        "Ask anything about your documents..."
    )

    # Handle a selected suggestion.

    if st.session_state.pending_query:

        query = st.session_state.pending_query

        st.session_state.pending_query = None

    if query:

        process_query(query)

        st.rerun()


if __name__ == "__main__":
    main()