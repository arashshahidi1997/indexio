/**
 * indexio chatbot widget — reusable across all projio subsystems.
 *
 * Usage: include this script in your docs site.  Configure via a global object
 * BEFORE loading the script:
 *
 *   <script>
 *     window.INDEXIO_CHAT = {
 *       apiUrl: "http://localhost:9100/chat/",   // chat endpoint
 *       title:  "My Docs Assistant",             // header title
 *       storageKey: "myproject_chat_v1",          // localStorage key
 *     };
 *   </script>
 *   <script src="/chatbot/chatbot.js"></script>
 *   <link  href="/chatbot/chatbot.css" rel="stylesheet">
 */
document.addEventListener("DOMContentLoaded", () => {
  const cfg = window.INDEXIO_CHAT || {};
  const API_URL = cfg.apiUrl || "/chat/";
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
    return { isOpen: false, messages: [] };
  }

  let state = loadState() || freshState();

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
  const titleEl = el("span", "chatbot-title", TITLE);
  const clearBtn = el("button", "chatbot-clear", "Clear");
  clearBtn.type = "button";
  clearBtn.title = "Clear chat history";
  const closeBtn = el("button", "chatbot-close", "\u00d7");
  closeBtn.type = "button";

  const headerRight = el("span", "chatbot-header-right");
  headerRight.appendChild(clearBtn);
  headerRight.appendChild(closeBtn);

  header.appendChild(titleEl);
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
      const resp = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      if (data && typeof data.answer === "string") {
        state.messages.push({ type: "bot", text: data.answer });
        if (Array.isArray(data.sources) && data.sources.length > 0) {
          state.messages.push({ type: "sources", sources: data.sources });
        }
        saveState(state);
        await addMd(data.answer, "bot");
        if (Array.isArray(data.sources) && data.sources.length > 0) {
          addSources(data.sources);
        }
      } else {
        const fb = "Unexpected response from server.";
        state.messages.push({ type: "bot", text: fb });
        saveState(state);
        addPlain(fb, "bot");
      }
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
    saveState(state);
    messagesEl.innerHTML = "";
  }

  // ── Wire events ─────────────────────────────────────────────

  launcher.addEventListener("click", () => toggle());
  closeBtn.addEventListener("click", () => toggle(false));
  clearBtn.addEventListener("click", clearHistory);
  form.addEventListener("submit", send);

  render();
});
