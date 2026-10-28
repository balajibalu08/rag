const uploadTab = document.querySelector("#upload-tab");
const chatTab = document.querySelector("#chat-tab");
const uploadView = document.querySelector("#upload-view");
const chatView = document.querySelector("#chat-view");

const fileInput = document.querySelector("#file-input");
const dropzone = document.querySelector("#dropzone");
const fileList = document.querySelector("#file-list");
const fileCount = document.querySelector("#file-count");
const uploadButton = document.querySelector("#upload-button");
const uploadButtonLabel = document.querySelector("#upload-button-label");
const fileRules = document.querySelector("#file-rules");
const uploadNotice = document.querySelector("#upload-notice");

const chatMessages = document.querySelector("#chat-messages");
const chatWelcome = document.querySelector("#chat-welcome");
const chatForm = document.querySelector("#chat-form");
const chatQuery = document.querySelector("#chat-query");
const sendButton = document.querySelector("#send-button");
const chatNotice = document.querySelector("#chat-notice");

let selectedFiles = [];
let allowedExtensions = [];
let maxFileSizeBytes = 0;
let isUploading = false;
let isSending = false;

function showView(viewName) {
  const showChat = viewName === "chat";

  uploadTab.classList.toggle("active", !showChat);
  chatTab.classList.toggle("active", showChat);
  uploadTab.setAttribute("aria-selected", String(!showChat));
  chatTab.setAttribute("aria-selected", String(showChat));
  uploadView.hidden = showChat;
  chatView.hidden = !showChat;
}

function formatSize(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function showUploadNotice(message, type) {
  uploadNotice.textContent = message;
  uploadNotice.className = `notice visible ${type}`;
}

function showChatNotice(message) {
  chatNotice.textContent = message;
  chatNotice.classList.toggle("visible", Boolean(message));
}

function clearChatHistory() {
  chatMessages.replaceChildren(chatWelcome);
  chatWelcome.hidden = false;
  showChatNotice("");
}

function getFileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function addFiles(files) {
  if (isUploading) {
    return;
  }

  uploadNotice.className = "notice";
  const knownFiles = new Set(selectedFiles.map(getFileKey));

  for (const file of files) {
    const extension = `.${file.name.split(".").pop().toLowerCase()}`;

    if (!allowedExtensions.includes(extension)) {
      showUploadNotice(`${file.name}: this file type is not supported.`, "error");
      continue;
    }

    if (maxFileSizeBytes && file.size > maxFileSizeBytes) {
      showUploadNotice(
        `${file.name}: file exceeds the ${formatSize(maxFileSizeBytes)} limit.`,
        "error"
      );
      continue;
    }

    const fileKey = getFileKey(file);
    if (!knownFiles.has(fileKey)) {
      selectedFiles.push(file);
      knownFiles.add(fileKey);
    }
  }

  renderFiles();
}

function renderFiles() {
  const fileWord = selectedFiles.length === 1 ? "file" : "files";
  fileCount.textContent = `${selectedFiles.length} ${fileWord} selected`;
  uploadButton.disabled = selectedFiles.length === 0 || isUploading;
  fileList.replaceChildren();

  if (!selectedFiles.length) {
    const emptyMessage = document.createElement("div");
    emptyMessage.className = "empty-files";
    emptyMessage.textContent = "Your selected files will appear here.";
    fileList.append(emptyMessage);
    return;
  }

  selectedFiles.forEach((file, index) => {
    const row = document.createElement("div");
    row.className = "file-row";

    const icon = document.createElement("span");
    icon.className = "file-icon";
    icon.textContent = file.name.split(".").pop().slice(0, 5);

    const details = document.createElement("span");
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.name;
    details.append(name);

    const size = document.createElement("span");
    size.className = "file-size";
    size.textContent = formatSize(file.size);

    const remove = document.createElement("button");
    remove.className = "remove-file";
    remove.type = "button";
    remove.disabled = isUploading;
    remove.setAttribute("aria-label", `Remove ${file.name}`);
    remove.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m7 7 10 10M17 7 7 17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      </svg>`;
    remove.addEventListener("click", () => {
      selectedFiles.splice(index, 1);
      renderFiles();
    });

    row.append(icon, details, size, remove);
    fileList.append(row);
  });
}

function setUploading(uploading) {
  isUploading = uploading;
  uploadButton.classList.toggle("loading", uploading);
  uploadButtonLabel.textContent = uploading
    ? "Uploading and indexing..."
    : "Upload and index";
  dropzone.setAttribute("aria-disabled", String(uploading));
  renderFiles();
}

async function uploadFiles() {
  if (!selectedFiles.length || isUploading) {
    return;
  }

  const filesBeingUploaded = [...selectedFiles];
  const formData = new FormData();
  filesBeingUploaded.forEach((file) => formData.append("files", file));

  setUploading(true);
  showUploadNotice(
    "Sending files to the server for upload and indexing...",
    "info"
  );

  try {
    const response = await fetch("/upload/", {
      method: "POST",
      body: formData,
    });
    const result = await response.json();

    if (!response.ok) {
      showUploadNotice(
        result.detail || `Upload failed (HTTP ${response.status}).`,
        "error"
      );
      return;
    }

    const uploadedFiles = result.uploaded_files ?? [];
    const failedFiles = result.failed_files ?? [];
    if (uploadedFiles.length) {
      clearChatHistory();
    }

    const failedNames = new Set(failedFiles.map((file) => file.filename));
    selectedFiles = filesBeingUploaded.filter((file) => failedNames.has(file.name));
    renderFiles();

    if (failedFiles.length) {
      const errors = failedFiles
        .map((file) => `${file.filename}: ${file.reason || "Upload failed."}`)
        .join(" ");
      const uploadedNames = uploadedFiles
        .map((file) => file.filename)
        .join(", ");
      const message = uploadedFiles.length
        ? `${uploadedFiles.length} uploaded (${uploadedNames}); ${failedFiles.length} failed. ${errors}`
        : `No files uploaded. ${errors}`;

      showUploadNotice(message, uploadedFiles.length ? "info" : "error");
      return;
    }

    const uploadedNames = uploadedFiles
      .map((file) => file.filename)
      .join(", ");
    showUploadNotice(
      `Uploaded and indexed ${uploadedFiles.length} file(s): ${uploadedNames}.`,
      "success"
    );
  } catch (error) {
    if (error instanceof SyntaxError) {
      showUploadNotice(
        "The server returned an unreadable response. Please check the API logs.",
        "error"
      );
      return;
    }

    showUploadNotice(
      "Could not reach the API. Check that the server is running and try again.",
      "error"
    );
  } finally {
    setUploading(false);
  }
}

function addMessage(role, text, className = "") {
  chatWelcome.hidden = true;

  const message = document.createElement("article");
  message.className = `message ${role}${className ? ` ${className}` : ""}`;

  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "user" ? "You" : "Document assistant";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = text;

  message.append(label, bubble);
  chatMessages.append(message);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  return message;
}

function addAnswerDetails(message, result) {
  if (result.sources?.length) {
    const sources = document.createElement("ul");
    sources.className = "answer-sources";
    sources.setAttribute("aria-label", "Sources");

    result.sources.forEach((source) => {
      const item = document.createElement("li");
      item.className = "source-chip";
      item.textContent = source;
      sources.append(item);
    });

    message.append(sources);
  }

  if (result.confidence !== null && result.confidence !== undefined) {
    const critic = document.createElement("span");
    critic.className = "critic-note";
    critic.textContent = `Review confidence: ${result.confidence}/100`;
    message.append(critic);
  }
}

function setSending(sending) {
  isSending = sending;
  sendButton.disabled = sending;
  chatQuery.disabled = sending;
  sendButton.classList.toggle("loading", sending);
}

async function sendQuestion(event) {
  event.preventDefault();

  const query = chatQuery.value.trim();
  if (!query || isSending) {
    return;
  }

  addMessage("user", query);
  chatQuery.value = "";
  chatQuery.style.height = "auto";
  showChatNotice("");
  setSending(true);

  const waitingMessage = addMessage("assistant", "Searching your documents...");
  waitingMessage.classList.add("waiting");

  try {
    const response = await fetch("/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    });
    if (!response.ok) {
      const result = await response.json();
      waitingMessage.remove();
      addMessage(
        "assistant",
        result.detail || `The request failed (HTTP ${response.status}).`,
        "error"
      );
      return;
    }

    if (!response.body) {
      throw new Error("The server did not provide a response stream.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answerMessage = null;
    let receivedTerminalEvent = false;

    const handleEvent = (block) => {
      const lines = block.split("\n");
      const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");

      if (!event || !data) {
        return;
      }

      const payload = JSON.parse(data);

      if (event === "delta") {
        if (!answerMessage) {
          waitingMessage.remove();
          answerMessage = addMessage("assistant", "");
        }
        answerMessage.querySelector(".message-bubble").textContent += payload;
      } else if (event === "reset") {
        if (!answerMessage) {
          waitingMessage.remove();
          answerMessage = addMessage("assistant", "");
        } else {
          answerMessage.querySelector(".message-bubble").textContent = "";
        }
      } else if (event === "complete") {
        if (!answerMessage) {
          waitingMessage.remove();
          answerMessage = addMessage("assistant", payload.answer);
        } else {
          answerMessage.querySelector(".message-bubble").textContent = payload.answer;
        }
        addAnswerDetails(answerMessage, payload);
        receivedTerminalEvent = true;
      } else if (event === "error") {
        waitingMessage.remove();
        answerMessage?.remove();
        addMessage(
          "assistant",
          payload.detail || "The response could not be generated.",
          "error"
        );
        receivedTerminalEvent = true;
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");

      let separator = buffer.indexOf("\n\n");
      while (separator !== -1) {
        handleEvent(buffer.slice(0, separator));
        buffer = buffer.slice(separator + 2);
        separator = buffer.indexOf("\n\n");
      }

      if (done) {
        break;
      }
    }

    if (!receivedTerminalEvent) {
      throw new Error("The response stream ended before the answer was complete.");
    }
  } catch {
    waitingMessage.remove();
    addMessage(
      "assistant",
      "I couldn't connect to the API. Check that the server is running and try again.",
      "error"
    );
  } finally {
    setSending(false);
    chatQuery.focus();
  }
}

async function loadUploadSettings() {
  try {
    const response = await fetch("/upload/info");

    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status}`);
    }

    const settings = await response.json();
    allowedExtensions = settings.allowed_file_types ?? [];
    maxFileSizeBytes = settings.max_file_size_bytes ?? 0;
    fileInput.accept = allowedExtensions.join(",");
    fileRules.replaceChildren();

    allowedExtensions.forEach((extension) => {
      const badge = document.createElement("span");
      badge.className = "file-rule";
      badge.textContent = extension.replace(".", "").toUpperCase();
      fileRules.append(badge);
    });

    const limit = document.createElement("span");
    limit.className = "file-rule";
    limit.textContent = `UP TO ${formatSize(maxFileSizeBytes)}`;
    fileRules.append(limit);
  } catch {
    showUploadNotice(
      "Could not load upload settings. Refresh the page or check the API server.",
      "error"
    );
  }
}

uploadTab.addEventListener("click", () => showView("upload"));
chatTab.addEventListener("click", () => showView("chat"));
fileInput.addEventListener("change", (event) => {
  addFiles(event.target.files);
  fileInput.value = "";
});
uploadButton.addEventListener("click", uploadFiles);
chatForm.addEventListener("submit", sendQuestion);

chatQuery.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

chatQuery.addEventListener("input", () => {
  chatQuery.style.height = "auto";
  chatQuery.style.height = `${chatQuery.scrollHeight}px`;
});

dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    if (!isUploading) {
      dropzone.classList.add("dragging");
    }
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  });
});

dropzone.addEventListener("drop", (event) => {
  addFiles(event.dataTransfer.files);
});

loadUploadSettings();
