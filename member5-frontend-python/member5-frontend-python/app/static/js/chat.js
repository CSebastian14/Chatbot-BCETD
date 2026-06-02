/**
 * BCETD Chat Client — Browser-side logic
 *
 * Communicates exclusively with the Python Flask backend at /api/*.
 * The browser never knows about n8n — Flask proxies everything.
 *
 * Response contract from /api/chat:
 *   {
 *     answer:    string,
 *     sources:   Array<{label, url, type}>,
 *     used_tool: boolean,
 *     rejected:  boolean,
 *     fallback:  boolean,
 *     error:     boolean
 *   }
 */

const CHAT_API = "/api/chat";
const SESSION_RESET_API = "/api/session/reset";
const REQUEST_TIMEOUT = 30000;

let isWaiting = false;

const chatInner = document.getElementById("chat-inner");
const chatContainer = document.getElementById("chat-container");
const queryInput = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const typingIndicator = document.getElementById("typing-indicator");
const welcomeScreen = document.getElementById("welcome-screen");
const charCountEl = document.getElementById("char-count");

// Inline SVG icons used in source chips
const ICON_LINK = '<svg class="source-icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M9 2h5v5h-1V3.707L7.354 9.354l-.708-.708L12.293 3H9V2z"/><path d="M3 4a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V8h1v5a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5v1H3z"/></svg>';
const ICON_FILE = '<svg class="source-icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4 0h5.293A1 1 0 0 1 10 .293L13.707 4a1 1 0 0 1 .293.707V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2zm5.5 1.5v2a1 1 0 0 0 1 1h2L9.5 1.5z"/></svg>';

marked.setOptions({ breaks: true, gfm: true });

/* ── UI helpers ────────────────────────────────────────────── */

function autoResize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
  sendBtn.disabled = textarea.value.trim().length === 0 || isWaiting;
}

function updateCharCount() {
  const len = queryInput.value.length;
  if (len > 400) {
    charCountEl.textContent = len + "/500";
    charCountEl.classList.toggle("warn", len > 480);
  } else {
    charCountEl.textContent = "";
  }
}

function handleKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function scrollToBottom() {
  setTimeout(() => { chatContainer.scrollTop = chatContainer.scrollHeight; }, 50);
}

function hideWelcome() {
  if (welcomeScreen) welcomeScreen.style.display = "none";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function askSuggestion(btn) {
  queryInput.value = btn.textContent;
  autoResize(queryInput);
  sendMessage();
}

function showTyping() {
  typingIndicator.classList.add("visible");
  scrollToBottom();
}

function hideTyping() {
  typingIndicator.classList.remove("visible");
}

/* ── Source rendering ──────────────────────────────────────── */

function renderSource(src) {
  let label, url, type;

  if (typeof src === "object" && src !== null) {
    label = (src.label || "").trim();
    url = (src.url || "").trim();
    type = src.type || (url ? "link" : "file");
  } else if (typeof src === "string") {
    const s = src.trim();
    if (s.match(/^https?:\/\//i)) {
      label = "Pagină oficială";
      url = s;
      type = "link";
    } else {
      label = s;
      url = "";
      type = "file";
    }
  } else {
    return "";
  }

  if (!label && !url) return "";

  if (type === "link" && url) {
    return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer" ' +
           'class="source-link" title="' + escapeHtml(url) + '">' +
           ICON_LINK + '<span class="source-link-label">' +
           escapeHtml(label || "Sursă oficială") + '</span></a>';
  }

  if (type === "file" && label && label.match(/\.(txt|pdf|docx|md)$/i)) {
    return '<a href="/documents/' + encodeURIComponent(label) + '" target="_blank" rel="noopener noreferrer" ' +
           'class="source-link" title="Document local: ' + escapeHtml(label) + '">' +
           ICON_FILE + '<span class="source-link-label">' + escapeHtml(label) + '</span></a>';
  }

  return '<span class="source-tag">' + escapeHtml(label) + '</span>';
}

/* ── Message bubble ────────────────────────────────────────── */

function addMessage(text, role, extra = {}) {
  hideWelcome();

  const msgDiv = document.createElement("div");
  msgDiv.className = "message " + role;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = role === "user" ? "Tu" : "UB";

  const body = document.createElement("div");
  body.className = "msg-body";
  if (extra.rejected) body.classList.add("rejected");
  if (extra.error) body.classList.add("error-msg");

  if (role === "bot") {
    body.innerHTML = marked.parse(text);

    if (extra.sources && extra.sources.length > 0) {
      const sourcesHtml = extra.sources
        .map(renderSource)
        .filter(html => html.length > 0)
        .join("");

      if (sourcesHtml) {
        const srcDiv = document.createElement("div");
        srcDiv.className = "msg-sources";
        srcDiv.innerHTML =
          '<div class="msg-sources-label">\uD83D\uDCC4 Surse</div>' +
          '<div class="msg-sources-list">' + sourcesHtml + '</div>';
        body.appendChild(srcDiv);
      }
    }
  } else {
    body.textContent = text;
  }

  msgDiv.appendChild(avatar);
  msgDiv.appendChild(body);
  chatInner.insertBefore(msgDiv, typingIndicator);
  scrollToBottom();
}

/* ── Send message to Python backend ────────────────────────── */

async function sendMessage() {
  const query = queryInput.value.trim();
  if (!query || isWaiting) return;

  addMessage(query, "user");
  queryInput.value = "";
  autoResize(queryInput);
  updateCharCount();
  isWaiting = true;
  sendBtn.disabled = true;
  showTyping();

  let data;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

    const response = await fetch(CHAT_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    data = await response.json();
  } catch (err) {
    hideTyping();
    const errorMsg = err.name === "AbortError"
      ? "Conexiunea a expirat. Vă rugăm să încercați din nou."
      : "Conexiune întreruptă. Reîncărcați pagina și încercați din nou.";
    addMessage(errorMsg, "bot", { error: true });
    isWaiting = false;
    sendBtn.disabled = queryInput.value.trim().length === 0;
    queryInput.focus();
    return;
  }

  hideTyping();

  addMessage(data.answer || "Nu am primit un răspuns valid.", "bot", {
    sources: data.sources || [],
    rejected: !!data.rejected,
    fallback: !!data.fallback,
    error: !!data.error,
  });

  isWaiting = false;
  sendBtn.disabled = queryInput.value.trim().length === 0;
  queryInput.focus();
}

/* ── Clear chat ────────────────────────────────────────────── */

async function clearChat() {
  chatInner.querySelectorAll(".message").forEach(m => m.remove());
  if (welcomeScreen) welcomeScreen.style.display = "";
  try {
    await fetch(SESSION_RESET_API, { method: "POST" });
  } catch (e) {
    // silent — session reset is non-critical
  }
}

queryInput.focus();