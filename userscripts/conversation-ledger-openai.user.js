// ==UserScript==
// @name         Conversation Ledger OpenAI Adapter
// @namespace    https://github.com/AganinAlexandr/ConversationLedger
// @version      0.2.0
// @description  Record rendered Codex and ChatGPT conversation turns into the local Conversation Ledger collector.
// @author       AganinAlexandr
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @match        https://codex.openai.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

(function () {
  "use strict";

  const SCRIPT_VERSION = "0.2.0";
  const DEFAULTS = {
    collectorUrl: "http://127.0.0.1:8765",
    collectorToken: "",
    projectId: "default-project",
    paused: false,
  };

  const SELECTOR_GROUPS = {
    codex: [
      "[data-message-author-role]",
      "[data-testid^='conversation-turn-']",
      "main article",
      "main [role='article']",
      "main section article",
      "main [data-testid*='message']",
      "main [data-testid*='turn']",
    ],
    chatgpt: [
      "[data-message-author-role]",
      "[data-testid^='conversation-turn-']",
      "main article",
      "main [role='article']",
      "main [data-testid*='conversation-turn']",
      "main [data-testid*='message']",
    ],
  };

  const state = {
    config: {
      collectorUrl: loadSetting("collectorUrl", DEFAULTS.collectorUrl),
      collectorToken: loadSetting("collectorToken", DEFAULTS.collectorToken),
      projectId: loadSetting("projectId", DEFAULTS.projectId),
      paused: loadSetting("paused", DEFAULTS.paused),
    },
    status: "booting",
    profile: null,
    overlay: null,
    knownMessages: new Map(),
    flushTimer: null,
    rescanTimer: null,
    pendingEvents: [],
    observer: null,
    healthTimer: null,
    rootObserver: null,
  };

  function loadSetting(key, fallback) {
    try {
      const value = GM_getValue(key);
      return value === undefined ? fallback : value;
    } catch (_error) {
      return fallback;
    }
  }

  function saveSetting(key, value) {
    state.config[key] = value;
    GM_setValue(key, value);
  }

  function currentProfile() {
    const host = window.location.host;
    const path = window.location.pathname;
    if (host === "codex.openai.com" || path.startsWith("/codex")) {
      return { id: "codex", platform: "codex", label: "Codex" };
    }
    if (host === "chatgpt.com" || host === "chat.openai.com") {
      return { id: "chatgpt", platform: "chatgpt", label: "ChatGPT" };
    }
    return null;
  }

  function setupMenu() {
    GM_registerMenuCommand("Conversation Ledger: set project_id", () => {
      const value = window.prompt("Conversation Ledger project_id", state.config.projectId);
      if (value) {
        saveSetting("projectId", value.trim());
        renderOverlay();
        scheduleScan();
      }
    });

    GM_registerMenuCommand("Conversation Ledger: set collector URL", () => {
      const value = window.prompt("Collector URL", state.config.collectorUrl);
      if (value) {
        saveSetting("collectorUrl", value.trim().replace(/\/$/, ""));
        pingCollector();
      }
    });

    GM_registerMenuCommand("Conversation Ledger: set collector token", () => {
      const value = window.prompt("Collector bearer token", state.config.collectorToken);
      if (value !== null) {
        saveSetting("collectorToken", value.trim());
        pingCollector();
      }
    });

    GM_registerMenuCommand("Conversation Ledger: toggle pause", () => {
      setPaused(!state.config.paused);
    });

    GM_registerMenuCommand("Conversation Ledger: ping collector", () => {
      pingCollector();
    });
  }

  function renderOverlay() {
    if (!state.overlay) {
      const root = document.createElement("div");
      root.id = "conversation-ledger-overlay";
      root.style.cssText = [
        "position:fixed",
        "right:16px",
        "bottom:16px",
        "z-index:2147483647",
        "font:12px/1.4 system-ui,-apple-system,Segoe UI,sans-serif",
        "display:flex",
        "align-items:center",
        "gap:8px",
        "padding:10px 12px",
        "border-radius:999px",
        "background:rgba(15,23,42,0.92)",
        "color:#f8fafc",
        "box-shadow:0 12px 32px rgba(15,23,42,0.25)",
        "backdrop-filter:blur(8px)",
      ].join(";");

      const statusDot = document.createElement("span");
      statusDot.dataset.role = "status-dot";
      statusDot.style.cssText = "width:10px;height:10px;border-radius:999px;display:inline-block;";
      root.appendChild(statusDot);

      const label = document.createElement("span");
      label.dataset.role = "status-label";
      root.appendChild(label);

      const project = document.createElement("span");
      project.dataset.role = "project-label";
      project.style.cssText = "opacity:.8;";
      root.appendChild(project);

      const button = document.createElement("button");
      button.type = "button";
      button.dataset.role = "pause-button";
      button.style.cssText = [
        "border:0",
        "border-radius:999px",
        "padding:6px 10px",
        "cursor:pointer",
        "background:#e2e8f0",
        "color:#0f172a",
      ].join(";");
      button.addEventListener("click", () => setPaused(!state.config.paused));
      root.appendChild(button);

      document.documentElement.appendChild(root);
      state.overlay = root;
    }

    const dot = state.overlay.querySelector("[data-role='status-dot']");
    const label = state.overlay.querySelector("[data-role='status-label']");
    const project = state.overlay.querySelector("[data-role='project-label']");
    const button = state.overlay.querySelector("[data-role='pause-button']");
    const paused = state.config.paused;
    const palette = {
      recording: "#22c55e",
      paused: "#f59e0b",
      error: "#ef4444",
      booting: "#38bdf8",
    };

    dot.style.background = palette[state.status] || palette.booting;
    label.textContent = `Ledger ${state.status}`;
    project.textContent = `${state.profile ? state.profile.label : "OpenAI"} / ${state.config.projectId}`;
    button.textContent = paused ? "Resume" : "Pause";
  }

  function setStatus(nextStatus) {
    state.status = nextStatus;
    renderOverlay();
  }

  async function setPaused(paused) {
    saveSetting("paused", Boolean(paused));
    renderOverlay();
    try {
      await postJson("/control/pause", { paused: state.config.paused });
      setStatus(state.config.paused ? "paused" : "recording");
    } catch (_error) {
      setStatus("error");
    }
  }

  function pingCollector() {
    window.clearTimeout(state.healthTimer);
    state.healthTimer = window.setTimeout(async () => {
      try {
        const response = await httpRequest({
          method: "GET",
          url: `${state.config.collectorUrl}/health`,
          headers: { Accept: "application/json" },
        });
        const payload = JSON.parse(response.responseText || "{}");
        if (payload.status === "paused" || state.config.paused) {
          setStatus("paused");
        } else {
          setStatus("recording");
        }
      } catch (_error) {
        setStatus("error");
      }
    }, 50);
  }

  function bootstrap() {
    state.profile = currentProfile();
    if (!state.profile) {
      return;
    }
    setupMenu();
    renderOverlay();
    pingCollector();
    attachObservers();
    scheduleScan();
    window.addEventListener("popstate", handleRouteChange);
    window.addEventListener("hashchange", handleRouteChange);
    patchHistory();
  }

  function patchHistory() {
    const wrap = (methodName) => {
      const original = history[methodName];
      history[methodName] = function patchedHistory(...args) {
        const result = original.apply(this, args);
        handleRouteChange();
        return result;
      };
    };
    wrap("pushState");
    wrap("replaceState");
  }

  function handleRouteChange() {
    state.profile = currentProfile();
    state.knownMessages.clear();
    renderOverlay();
    scheduleScan();
  }

  function attachObservers() {
    if (state.rootObserver) {
      state.rootObserver.disconnect();
    }

    state.rootObserver = new MutationObserver(() => {
      if (!state.observer) {
        const root = locateConversationRoot();
        if (root) {
          attachConversationObserver(root);
          scheduleScan();
        }
      }
    });

    state.rootObserver.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });

    const root = locateConversationRoot();
    if (root) {
      attachConversationObserver(root);
    }
  }

  function attachConversationObserver(root) {
    if (state.observer) {
      state.observer.disconnect();
    }
    state.observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "childList" || mutation.type === "characterData") {
          scheduleScan();
          break;
        }
      }
    });
    state.observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  function scheduleScan() {
    window.clearTimeout(state.rescanTimer);
    state.rescanTimer = window.setTimeout(scanMessages, 250);
  }

  function locateConversationRoot() {
    return (
      document.querySelector("main") ||
      document.querySelector("[role='main']") ||
      document.body
    );
  }

  function scanMessages() {
    if (!state.profile || state.config.paused) {
      renderOverlay();
      return;
    }

    const candidates = collectMessageCandidates();
    candidates.forEach((node, index) => {
      const extracted = extractMessage(node, index);
      if (!extracted) {
        return;
      }
      const previous = state.knownMessages.get(extracted.messageKey);
      if (!previous) {
        queueEvent(buildEvent(extracted, "message_final"));
        state.knownMessages.set(extracted.messageKey, {
          contentSha: extracted.contentSha,
          messageId: extracted.messageId,
        });
        return;
      }

      if (previous.contentSha !== extracted.contentSha) {
        queueEvent(buildEvent(extracted, "message_revision"));
        state.knownMessages.set(extracted.messageKey, {
          contentSha: extracted.contentSha,
          messageId: extracted.messageId,
        });
      }
    });
  }

  function collectMessageCandidates() {
    const root = locateConversationRoot();
    const selectors = SELECTOR_GROUPS[state.profile.id] || [];
    const nodes = new Set();

    selectors.forEach((selector) => {
      root.querySelectorAll(selector).forEach((node) => {
        if (node instanceof HTMLElement) {
          nodes.add(normalizeMessageNode(node));
        }
      });
    });

    return Array.from(nodes).filter((node) => isUsefulMessageNode(node));
  }

  function normalizeMessageNode(node) {
    return (
      node.closest("[data-message-author-role]") ||
      node.closest("[data-testid^='conversation-turn-']") ||
      node.closest("article") ||
      node
    );
  }

  function isUsefulMessageNode(node) {
    if (!(node instanceof HTMLElement)) {
      return false;
    }
    if (!node.isConnected || node.closest("#conversation-ledger-overlay")) {
      return false;
    }
    if (node.matches("form, textarea, input, button")) {
      return false;
    }
    if (node.querySelector("textarea,[contenteditable='true'],input[type='text']")) {
      return false;
    }
    const text = node.innerText.replace(/\s+/g, " ").trim();
    return text.length >= 2;
  }

  function extractMessage(node, index) {
    const contentRoot = locateContentRoot(node);
    if (!contentRoot) {
      return null;
    }
    const contentMarkdown = toMarkdown(contentRoot).trim();
    if (!contentMarkdown) {
      return null;
    }

    const threadId = extractThreadId();
    const role = extractRole(node);
    const messageKey = deriveMessageKey(node, index, role, contentMarkdown);
    const messageId = shortHash(`message:${state.profile.platform}:${threadId}:${messageKey}`);
    const contentSha = sha256(contentMarkdown);

    return {
      role,
      contentMarkdown,
      contentSha,
      messageKey,
      messageId,
      threadId,
      attachments: extractAttachments(node),
      timestampObserved: new Date().toISOString(),
    };
  }

  function locateContentRoot(node) {
    const selectors = [
      "[data-message-content]",
      "[data-testid='markdown']",
      ".markdown",
      "article",
      "[class*='markdown']",
      "[class*='prose']",
    ];
    for (const selector of selectors) {
      const match = node.matches(selector) ? node : node.querySelector(selector);
      if (match instanceof HTMLElement && match.innerText.trim()) {
        return match;
      }
    }
    return node;
  }

  function extractRole(node) {
    const direct = node.getAttribute("data-message-author-role");
    if (direct) {
      return normalizeRole(direct);
    }

    const roleHint = [
      node.getAttribute("data-testid"),
      node.getAttribute("aria-label"),
      node.className,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    if (roleHint.includes("assistant")) {
      return "assistant";
    }
    if (roleHint.includes("user")) {
      return "user";
    }
    if (roleHint.includes("system")) {
      return "system";
    }
    if (roleHint.includes("tool")) {
      return "tool";
    }
    return "unknown";
  }

  function normalizeRole(rawRole) {
    const value = String(rawRole || "").toLowerCase();
    if (["assistant", "user", "system", "tool"].includes(value)) {
      return value;
    }
    return "unknown";
  }

  function deriveMessageKey(node, index, role, contentMarkdown) {
    const preferred =
      node.getAttribute("data-message-id") ||
      node.getAttribute("data-id") ||
      node.getAttribute("data-testid") ||
      node.id;
    if (preferred) {
      return preferred;
    }

    const href = node.querySelector("a[href]")?.getAttribute("href") || "";
    const structuralPath = buildDomPath(node);
    return shortHash(`${role}:${index}:${href}:${structuralPath}:${contentMarkdown.length}`);
  }

  function buildDomPath(node) {
    const segments = [];
    let current = node;
    while (current && current instanceof HTMLElement && current.tagName !== "MAIN" && segments.length < 8) {
      const parent = current.parentElement;
      const siblingIndex = parent ? Array.from(parent.children).indexOf(current) : 0;
      segments.push(`${current.tagName.toLowerCase()}:${siblingIndex}`);
      current = parent;
    }
    return segments.reverse().join(">");
  }

  function extractThreadId() {
    const url = new URL(window.location.href);
    const chatMatch = url.pathname.match(/\/c\/([^/]+)/);
    if (chatMatch) {
      return chatMatch[1];
    }
    if (url.pathname.startsWith("/codex")) {
      return `codex${url.pathname.replace(/[^\w-]+/g, "-") || "-home"}`;
    }
    return `${url.host}${url.pathname}`.replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "") || "openai-thread";
  }

  function extractAttachments(node) {
    const attachments = [];
    node.querySelectorAll("a[href]").forEach((link) => {
      const href = link.getAttribute("href");
      const text = (link.textContent || "").trim();
      if (!href || !text) {
        return;
      }
      if (href.startsWith("#")) {
        return;
      }
      attachments.push({
        name: text,
        href: new URL(href, window.location.href).toString(),
      });
    });
    return attachments.slice(0, 10);
  }

  function buildEvent(extracted, eventType) {
    const revisionSeed = eventType === "message_revision" ? `:${extracted.contentSha}` : "";
    return {
      schema_version: "conversation_event_v0",
      event_id: shortHash(
        `${state.profile.platform}:${state.config.projectId}:${extracted.threadId}:${extracted.messageKey}:${eventType}${revisionSeed}`
      ),
      project_id: state.config.projectId,
      platform: state.profile.platform,
      source_product: state.profile.id,
      model_family: null,
      runtime_vendor: "openai",
      source_surface: "browser_web",
      thread_id: extracted.threadId,
      message_id: extracted.messageId,
      parent_message_id: null,
      timestamp_observed: extracted.timestampObserved,
      role: extracted.role,
      event_type: eventType,
      content_markdown: extracted.contentMarkdown,
      content_sha256: extracted.contentSha,
      attachment_refs: extracted.attachments,
      source_url: window.location.href,
      capture_adapter: `openai-userscript@${SCRIPT_VERSION}`,
    };
  }

  function queueEvent(event) {
    state.pendingEvents.push(event);
    window.clearTimeout(state.flushTimer);
    state.flushTimer = window.setTimeout(flushEvents, 200);
  }

  async function flushEvents() {
    if (!state.pendingEvents.length || state.config.paused) {
      return;
    }
    const batch = state.pendingEvents.splice(0, state.pendingEvents.length);
    try {
      await postJson("/events", { events: batch });
      setStatus("recording");
    } catch (_error) {
      state.pendingEvents.unshift(...batch);
      setStatus("error");
    }
  }

  async function postJson(path, payload) {
    const response = await httpRequest({
      method: "POST",
      url: `${state.config.collectorUrl}${path}`,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${state.config.collectorToken}`,
      },
      data: JSON.stringify(payload),
    });
    const status = Number(response.status || 0);
    if (status < 200 || status >= 300) {
      throw new Error(`collector_http_${status}`);
    }
    return JSON.parse(response.responseText || "{}");
  }

  function httpRequest(options) {
    return new Promise((resolve, reject) => {
      if (typeof GM_xmlhttpRequest === "function") {
        GM_xmlhttpRequest({
          method: options.method,
          url: options.url,
          headers: options.headers,
          data: options.data,
          onload: resolve,
          onerror: reject,
          ontimeout: reject,
        });
        return;
      }

      fetch(options.url, {
        method: options.method,
        headers: options.headers,
        body: options.data,
      })
        .then(async (response) => {
          resolve({
            status: response.status,
            responseText: await response.text(),
          });
        })
        .catch(reject);
    });
  }

  function toMarkdown(root) {
    return normalizeMarkdown(serializeNode(root, 0));
  }

  function serializeNode(node, depth) {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent || "";
    }
    if (!(node instanceof HTMLElement)) {
      return "";
    }
    if (["SCRIPT", "STYLE", "SVG", "NOSCRIPT", "TEXTAREA", "INPUT", "BUTTON"].includes(node.tagName)) {
      return "";
    }
    if (node.tagName === "PRE") {
      const code = node.innerText.replace(/\n+$/, "");
      const language = inferCodeLanguage(node);
      return `\n\`\`\`${language}\n${code}\n\`\`\`\n`;
    }
    if (node.tagName === "CODE") {
      return `\`${collapseWhitespace(node.textContent || "")}\``;
    }
    if (node.tagName === "BR") {
      return "\n";
    }
    if (/^H[1-6]$/.test(node.tagName)) {
      const level = Number(node.tagName[1]);
      return `\n${"#".repeat(level)} ${inlineChildren(node)}\n`;
    }
    if (node.tagName === "A") {
      const text = inlineChildren(node).trim() || node.getAttribute("href") || "";
      const href = node.getAttribute("href");
      if (!href) {
        return text;
      }
      return `[${text}](${new URL(href, window.location.href).toString()})`;
    }
    if (node.tagName === "BLOCKQUOTE") {
      const inner = normalizeMarkdown(blockChildren(node, depth)).trim();
      return `\n${inner.split("\n").map((line) => `> ${line}`).join("\n")}\n`;
    }
    if (node.tagName === "UL") {
      return `\n${Array.from(node.children).map((child) => `${"  ".repeat(depth)}- ${normalizeMarkdown(serializeNode(child, depth + 1)).trim()}`).join("\n")}\n`;
    }
    if (node.tagName === "OL") {
      return `\n${Array.from(node.children).map((child, index) => `${"  ".repeat(depth)}${index + 1}. ${normalizeMarkdown(serializeNode(child, depth + 1)).trim()}`).join("\n")}\n`;
    }
    if (node.tagName === "LI") {
      return blockChildren(node, depth);
    }
    if (node.tagName === "TABLE") {
      return `\n${tableToMarkdown(node)}\n`;
    }
    if (node.tagName === "P") {
      return `\n${inlineChildren(node)}\n`;
    }
    if (node.tagName === "STRONG" || node.tagName === "B") {
      return `**${inlineChildren(node)}**`;
    }
    if (node.tagName === "EM" || node.tagName === "I") {
      return `*${inlineChildren(node)}*`;
    }
    return blockChildren(node, depth);
  }

  function blockChildren(node, depth) {
    return Array.from(node.childNodes).map((child) => serializeNode(child, depth)).join("");
  }

  function inlineChildren(node) {
    return collapseWhitespace(Array.from(node.childNodes).map((child) => serializeNode(child, 0)).join(""));
  }

  function tableToMarkdown(table) {
    const rows = Array.from(table.querySelectorAll("tr")).map((row) =>
      Array.from(row.querySelectorAll("th,td")).map((cell) => collapseWhitespace(cell.innerText))
    );
    if (!rows.length) {
      return "";
    }
    const header = rows[0];
    const divider = header.map(() => "---");
    const body = rows.slice(1);
    return [
      `| ${header.join(" | ")} |`,
      `| ${divider.join(" | ")} |`,
      ...body.map((row) => `| ${row.join(" | ")} |`),
    ].join("\n");
  }

  function inferCodeLanguage(node) {
    const className = node.querySelector("code")?.className || node.className || "";
    const match = className.match(/language-([a-z0-9_-]+)/i);
    return match ? match[1] : "";
  }

  function collapseWhitespace(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  function normalizeMarkdown(value) {
    return value
      .replace(/\r/g, "")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[ \t]+\n/g, "\n")
      .trim();
  }

  function shortHash(value) {
    return sha256(value).slice(0, 32);
  }

  function sha256(value) {
    let h1 = 0xdeadbeef;
    let h2 = 0x41c6ce57;
    for (let index = 0; index < value.length; index += 1) {
      const charCode = value.charCodeAt(index);
      h1 = Math.imul(h1 ^ charCode, 2654435761);
      h2 = Math.imul(h2 ^ charCode, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    const part1 = (h2 >>> 0).toString(16).padStart(8, "0");
    const part2 = (h1 >>> 0).toString(16).padStart(8, "0");
    return `${part1}${part2}${part1}${part2}`;
  }

  bootstrap();
})();
