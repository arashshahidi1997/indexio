/**
 * indexio chatbot widget — reusable across all projio subsystems.
 *
 * Usage: include this script in your docs site.  Configure via a global object
 * BEFORE loading the script:
 *
 *   <script>
 *     window.INDEXIO_CHAT = {
 *       apiUrl: "http://localhost:9100/chat/",        // chat endpoint
 *       streamUrl: "http://localhost:9100/chat/stream", // SSE stream endpoint
 *       statusUrl: "http://localhost:9100/status",     // status endpoint
 *       title:  "My Docs Assistant",
 *       storageKey: "myproject_chat_v1",
 *     };
 *   </script>
 *   <script src="/chatbot/chatbot.js"></script>
 *   <link  href="/chatbot/chatbot.css" rel="stylesheet">
 */
document.addEventListener("DOMContentLoaded", () => {
  const cfg = window.INDEXIO_CHAT || {};
  const API_URL = cfg.apiUrl || "/chat/";
  const STREAM_URL = cfg.streamUrl || API_URL.replace(/\/$/, "") + "/stream";
  const STATUS_URL = cfg.statusUrl || "/status";
  const TITLE = cfg.title || "Docs Assistant";
  const STORAGE_KEY = cfg.storageKey || "indexio_chat_state_v1";

  // ── Persistent state ────────────────────────────────────────

  function loadState() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function saveState(state) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {}
  }

  function freshState() {
    return { isOpen: false, messages: [], useLlm: true, k: 6 };
  }

  let state = loadState() || freshState();
  if (state.useLlm === undefined) state.useLlm = true;
  if (state.k === undefined) state.k = 6;

  // ── Markdown renderer (lazy-loaded) ─────────────────────────

  function ensureMarked() {
    return new Promise((resolve) => {
      if (window.marked) {
        resolve(window.marked);
        return;
      }
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/marked/marked.min.js";
      s.onload = () => resolve(window.marked);
      s.onerror = () => resolve(null);
      document.head.appendChild(s);
    });
  }

  function renderMd(lib, text) {
    if (!lib) return null;
    if (typeof lib.parse === "function") return lib.parse(text);
    if (typeof lib === "function") return lib(text);
    return null;
  }

  // ── DOM helpers ─────────────────────────────────────────────

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // Build UI
  const launcher = el("button", "chatbot-launcher", "Chat");
  launcher.type = "button";

  const win = el("div", "chatbot-window");
  const header = el("div", "chatbot-header");

  // Status indicator
  const statusDot = el("span", "chatbot-status-dot chatbot-status-loading");
  statusDot.title = "Vector store loading\u2026";

  const titleEl = el("span", "chatbot-title", TITLE);
  const clearBtn = el("button", "chatbot-clear", "Clear");
  clearBtn.type = "button";
  clearBtn.title = "Clear chat history";
  const closeBtn = el("button", "chatbot-close", "\u00d7");
  closeBtn.type = "button";

  // LLM toggle
  const llmToggle = el("label", "chatbot-llm-toggle");
  const llmCheckbox = document.createElement("input");
  llmCheckbox.type = "checkbox";
  llmCheckbox.checked = state.useLlm;
  llmCheckbox.title = "Enable LLM answer generation";
  const llmLabel = el("span", "chatbot-llm-label", "LLM");
  llmToggle.appendChild(llmCheckbox);
  llmToggle.appendChild(llmLabel);

  // Top-k dropdown
  const kWrap = el("label", "chatbot-k-wrap");
  const kLabel = el("span", "chatbot-k-label", "k");
  const kSelect = document.createElement("select");
  kSelect.className = "chatbot-k-select";
  kSelect.title = "Number of sources to retrieve";
  [3, 6, 10, 15, 20].forEach((v) => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    if (v === state.k) o.selected = true;
    kSelect.appendChild(o);
  });
  kWrap.appendChild(kLabel);
  kWrap.appendChild(kSelect);

  const headerLeft = el("span", "chatbot-header-left");
  headerLeft.appendChild(statusDot);
  headerLeft.appendChild(titleEl);

  const headerRight = el("span", "chatbot-header-right");
  headerRight.appendChild(kWrap);
  headerRight.appendChild(llmToggle);
  headerRight.appendChild(clearBtn);
  headerRight.appendChild(closeBtn);

  header.appendChild(headerLeft);
  header.appendChild(headerRight);

  const messagesEl = el("div", "chatbot-messages");

  const form = el("form", "chatbot-form");
  const input = el("input", "chatbot-input");
  input.type = "text";
  input.placeholder = "Ask a question\u2026";
  const sendBtn = el("button", "chatbot-send", "Send");
  sendBtn.type = "submit";
  form.appendChild(input);
  form.appendChild(sendBtn);

  win.appendChild(header);
  win.appendChild(messagesEl);
  win.appendChild(form);

  document.body.appendChild(win);
  document.body.appendChild(launcher);

  // ── Status polling ────────────────────────────────────────────

  let statusResolved = false;

  async function pollStatus() {
    try {
      const resp = await fetch(STATUS_URL);
      if (!resp.ok) return;
      const data = await resp.json();
      const vs = data.vectorstore || "loading";
      statusDot.className = "chatbot-status-dot chatbot-status-" + vs;
      if (vs === "ready") {
        statusDot.title = "Vector store connected";
        statusResolved = true;
      } else if (vs === "error") {
        statusDot.title = "Vector store error: " + (data.detail || "unknown");
        statusResolved = true;
      } else {
        statusDot.title = "Vector store loading\u2026";
      }
    } catch {
      // Server not reachable yet
    }
  }

  const statusInterval = setInterval(() => {
    if (statusResolved) { clearInterval(statusInterval); return; }
    pollStatus();
  }, 2000);
  pollStatus();

  // ── UI logic ────────────────────────────────────────────────

  function toggle(force) {
    const open = force !== undefined ? force : !win.classList.contains("open");
    win.classList.toggle("open", open);
    if (open) input.focus();
    state.isOpen = open;
    saveState(state);
  }

  function addPlain(text, role) {
    const m = el("div", `chatbot-message chatbot-${role}`);
    m.textContent = text;
    messagesEl.appendChild(m);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return m;
  }

  async function addMd(text, role) {
    const m = el("div", `chatbot-message chatbot-${role}`);
    const lib = await ensureMarked();
    const html = renderMd(lib, text);
    if (html === null) {
      m.textContent = text;
    } else {
      m.innerHTML = html;
    }
    messagesEl.appendChild(m);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return m;
  }

  function addPhase(text) {
    const m = el("div", "chatbot-message chatbot-phase");
    m.textContent = text;
    messagesEl.appendChild(m);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return m;
  }

  function addSources(sources) {
    const c = el("div", "chatbot-message chatbot-sources");
    c.appendChild(el("div", "chatbot-sources-label", "Sources:"));
    sources.forEach((src) => {
      if (typeof src === "string") {
        c.appendChild(el("div", "chatbot-source-line", src));
        return;
      }
      const { source_id, corpus, source_path, url } = src;
      const line = el("div", "chatbot-source-line");
      const label = `${source_id ?? "?"} [${corpus ?? "?"}] \u2014 ${source_path ?? ""}`;
      if (url) {
        const a = document.createElement("a");
        a.textContent = label;
        a.href = url;
        a.target = "_blank";
        line.appendChild(a);
      } else {
        line.textContent = label;
      }
      c.appendChild(line);
    });
    messagesEl.appendChild(c);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setDisabled(disabled) {
    input.disabled = disabled;
    sendBtn.disabled = disabled;
  }

  // ── Restore from localStorage ───────────────────────────────

  async function render() {
    messagesEl.innerHTML = "";
    for (const item of state.messages) {
      if (!item || !item.type) continue;
      if (item.type === "user") addPlain(item.text, "user");
      else if (item.type === "bot") await addMd(item.text, "bot");
      else if (item.type === "sources" && Array.isArray(item.sources))
        addSources(item.sources);
    }
    win.classList.toggle("open", !!state.isOpen);
  }

  // ── SSE helper ──────────────────────────────────────────────

  const PHASE_LABELS = {
    searching: "Searching knowledge base\u2026",
    generating: "Generating answer\u2026",
  };

  async function sendStreaming(msg) {
    let phaseEl = null;
    let botEl = null;
    let botText = "";
    let sources = null;

    const resp = await fetch(STREAM_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, use_llm: state.useLlm, k: state.k }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parse SSE lines
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        let eventType = "message";
        let dataStr = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) eventType = line.slice(7);
          else if (line.startsWith("data: ")) dataStr = line.slice(6);
        }
        if (!dataStr) continue;
        const data = JSON.parse(dataStr);

        if (eventType === "phase") {
          // Remove previous phase indicator
          if (phaseEl) { phaseEl.remove(); phaseEl = null; }
          const label = PHASE_LABELS[data] || data;
          phaseEl = addPhase(label);
        } else if (eventType === "sources") {
          sources = data;
          addSources(data);
        } else if (eventType === "token") {
          // Remove phase indicator once tokens start
          if (phaseEl) { phaseEl.remove(); phaseEl = null; }
          botText += data;
          if (!botEl) {
            botEl = el("div", "chatbot-message chatbot-bot");
            messagesEl.appendChild(botEl);
          }
          // Re-render markdown as tokens accumulate
          const lib = await ensureMarked();
          const html = renderMd(lib, botText);
          if (html !== null) {
            botEl.innerHTML = html;
          } else {
            botEl.textContent = botText;
          }
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (eventType === "error") {
          if (phaseEl) { phaseEl.remove(); phaseEl = null; }
          botText = `LLM error: ${data}`;
          if (!botEl) {
            botEl = el("div", "chatbot-message chatbot-bot");
            messagesEl.appendChild(botEl);
          }
          botEl.textContent = botText;
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (eventType === "done") {
          if (phaseEl) { phaseEl.remove(); phaseEl = null; }
        }
      }
    }

    return { answer: botText, sources: sources };
  }

  // ── Send message ────────────────────────────────────────────

  async function send(e) {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;

    state.messages.push({ type: "user", text: msg });
    if (state.messages.length > 200) state.messages = state.messages.slice(-200);
    saveState(state);

    addPlain(msg, "user");
    input.value = "";
    setDisabled(true);

    try {
      const result = await sendStreaming(msg);

      if (result.answer) {
        state.messages.push({ type: "bot", text: result.answer });
      }
      if (Array.isArray(result.sources) && result.sources.length > 0) {
        state.messages.push({ type: "sources", sources: result.sources });
      }
      saveState(state);
    } catch (err) {
      const errText = `Error: ${err instanceof Error ? err.message : "Unknown error"}`;
      state.messages.push({ type: "bot", text: errText });
      saveState(state);
      addPlain(errText, "bot");
    } finally {
      setDisabled(false);
      input.focus();
    }
  }

  // ── Clear history ───────────────────────────────────────────

  function clearHistory() {
    state = freshState();
    state.isOpen = true;
    state.useLlm = llmCheckbox.checked;
    state.k = parseInt(kSelect.value, 10);
    saveState(state);
    messagesEl.innerHTML = "";
  }

  // ── Wire events ─────────────────────────────────────────────

  launcher.addEventListener("click", () => toggle());
  closeBtn.addEventListener("click", () => toggle(false));
  clearBtn.addEventListener("click", clearHistory);
  kSelect.addEventListener("change", () => {
    state.k = parseInt(kSelect.value, 10);
    saveState(state);
  });
  form.addEventListener("submit", send);
  llmCheckbox.addEventListener("change", () => {
    state.useLlm = llmCheckbox.checked;
    saveState(state);
  });

  render();
});
