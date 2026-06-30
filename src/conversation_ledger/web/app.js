const state = {
  options: null,
  currentSearchTerms: [],
};

const elements = {
  project: document.getElementById("filter-project"),
  family: document.getElementById("filter-family"),
  product: document.getElementById("filter-product"),
  vendor: document.getElementById("filter-vendor"),
  surface: document.getElementById("filter-surface"),
  day: document.getElementById("filter-day"),
  scope: document.getElementById("search-scope"),
  query: document.getElementById("search-query"),
  treeRoot: document.getElementById("tree-root"),
  treeSummary: document.getElementById("tree-summary"),
  resultsRoot: document.getElementById("results-root"),
  resultsTitle: document.getElementById("results-title"),
  resultsMeta: document.getElementById("results-meta"),
  reloadTree: document.getElementById("reload-tree"),
  runSearch: document.getElementById("run-search"),
  loadDayContext: document.getElementById("load-day-context"),
};

async function bootstrap() {
  await loadOptions();
  bindEvents();
  await refreshTree();
  showEmptyState("Choose a thread, run a search, or load a day context.");
}

function bindEvents() {
  elements.reloadTree.addEventListener("click", refreshTree);
  elements.runSearch.addEventListener("click", runSearch);
  elements.loadDayContext.addEventListener("click", loadDayContext);
  [elements.project, elements.family, elements.product, elements.vendor, elements.surface].forEach((element) => {
    element.addEventListener("change", refreshTree);
  });
  elements.query.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      await runSearch();
    }
  });
}

async function loadOptions() {
  const payload = await getJson("/api/options");
  state.options = payload;
  populateSelect(elements.project, payload.projects, "All projects");
  populateSelect(elements.family, payload.platforms, "All families");
  populateSelect(elements.product, payload.source_products, "All products");
  populateSelect(elements.vendor, payload.runtime_vendors, "All vendors");
  populateSelect(elements.surface, payload.source_surfaces, "All surfaces");
  populateSelect(elements.day, payload.days, "Choose day");
}

function populateSelect(select, values, label) {
  select.innerHTML = "";
  const first = document.createElement("option");
  first.value = "";
  first.textContent = label;
  select.appendChild(first);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

async function refreshTree() {
  const payload = await getJson(`/api/tree?${buildCommonParams().toString()}`);
  renderTree(payload.projects);
}

async function runSearch() {
  const query = elements.query.value.trim();
  if (!query) {
    showEmptyState("Enter a search phrase to look through saved messages.");
    return;
  }
  state.currentSearchTerms = buildSearchTerms(query);

  const params = buildCommonParams();
  params.set("query", query);
  params.set("scope", elements.scope.value);

  const scope = elements.scope.value;
  if (scope === "all") {
    params.delete("project");
    params.delete("family");
  }
  if (scope === "project") {
    params.delete("family");
  }
  if (scope === "family") {
    params.delete("project");
  }

  const payload = await getJson(`/api/search?${params.toString()}`);
  renderSearchResults(payload);
}

async function loadDayContext() {
  const project = elements.project.value;
  const date = elements.day.value;
  if (!project || !date) {
    showEmptyState("Choose a project and a day before loading day context.");
    return;
  }
  const params = buildCommonParams();
  params.set("project", project);
  params.set("date", date);
  const payload = await getJson(`/api/day-context?${params.toString()}`);
  renderContextPayload(payload, `Day Context: ${project} / ${date}`);
}

function buildCommonParams() {
  const params = new URLSearchParams();
  maybeSet(params, "project", elements.project.value);
  maybeSet(params, "family", elements.family.value);
  maybeSet(params, "product", elements.product.value);
  maybeSet(params, "vendor", elements.vendor.value);
  maybeSet(params, "surface", elements.surface.value);
  return params;
}

function maybeSet(params, key, value) {
  if (value) {
    params.set(key, value);
  }
}

function renderTree(projects) {
  elements.treeRoot.innerHTML = "";
  const totalProjects = projects.length;
  const totalThreads = projects.reduce((sum, item) => sum + item.thread_count, 0);
  elements.treeSummary.textContent = `${totalProjects} project(s) / ${totalThreads} thread(s)`;

  if (!projects.length) {
    elements.treeRoot.appendChild(emptyNode("No chats match the current filters."));
    return;
  }

  projects.forEach((project) => {
    const projectDetails = document.createElement("details");
    projectDetails.className = "tree-project";
    projectDetails.open = true;

    const summary = document.createElement("summary");
    summary.innerHTML = `
      <span>${escapeHtml(project.project_id)}</span>
      <span class="pill">${project.thread_count} thread(s)</span>
    `;
    projectDetails.appendChild(summary);

    const productList = document.createElement("div");
    productList.className = "product-list";

    project.products.forEach((product) => {
      const productDetails = document.createElement("details");
      productDetails.className = "tree-product";
      productDetails.open = true;

      const productSummary = document.createElement("summary");
      const title = product.source_product || product.platform || "unknown";
      productSummary.innerHTML = `
        <div>
          <div class="product-title">${escapeHtml(title)}</div>
          <div class="product-meta">
            ${badge(product.platform)}
            ${badge(product.runtime_vendor)}
            ${badge(product.source_surface)}
          </div>
        </div>
        <span class="pill">${product.thread_count} thread(s)</span>
      `;
      productDetails.appendChild(productSummary);

      const threadList = document.createElement("div");
      threadList.className = "thread-list";
      product.threads.forEach((thread) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "tree-thread";
        button.innerHTML = `
          <div class="thread-title">${escapeHtml(thread.thread_id)}</div>
          <div class="thread-meta">
            ${badge(`${thread.message_count} msg`)}
            ${badge(thread.started_at)}
            ${badge(thread.ended_at)}
          </div>
        `;
        button.addEventListener("click", () => loadThreadContext(project.project_id, thread));
        threadList.appendChild(button);
      });

      productDetails.appendChild(threadList);
      productList.appendChild(productDetails);
    });

    projectDetails.appendChild(productList);
    elements.treeRoot.appendChild(projectDetails);
  });
}

async function loadThreadContext(projectId, thread) {
  const params = new URLSearchParams();
  params.set("project", projectId);
  params.set("thread", thread.thread_id);
  maybeSet(params, "family", thread.platform);
  maybeSet(params, "product", thread.source_product);
  maybeSet(params, "vendor", thread.runtime_vendor);
  maybeSet(params, "surface", thread.source_surface);
  const payload = await getJson(`/api/thread-context?${params.toString()}`);
  renderContextPayload(payload, `Thread Context: ${thread.thread_id}`);
}

function renderSearchResults(payload) {
  elements.resultsTitle.textContent = "Search Results";
  elements.resultsMeta.textContent = `${payload.result_count} hit(s)`;
  elements.resultsRoot.innerHTML = "";

  if (!payload.results.length) {
    elements.resultsRoot.appendChild(emptyNode("No messages matched the current search."));
    return;
  }

  payload.results.forEach((result) => {
    const card = document.createElement("article");
    card.className = "result-card";
    card.innerHTML = `
      <h3>${escapeHtml(result.thread_id)}</h3>
      <div class="meta-line">
        ${badge(result.project_id)}
        ${badge(result.platform)}
        ${badge(result.source_product)}
        ${badge(result.runtime_vendor)}
        ${badge(result.source_surface)}
        ${badge(`score ${result.score.toFixed(2)}`)}
      </div>
    `;
    result.window.forEach((entry) => {
      card.appendChild(
        renderEntry(
          entry.role,
          entry.timestamp_observed,
          entry.content_markdown,
          entry.event_type,
          {
            isMatch: entry.event_id === result.matched_event_id,
            highlightTerms: state.currentSearchTerms,
          }
        )
      );
    });
    elements.resultsRoot.appendChild(card);
  });
}

function renderContextPayload(payload, title) {
  elements.resultsTitle.textContent = title;
  elements.resultsMeta.textContent = `${payload.thread_count} thread group(s)`;
  elements.resultsRoot.innerHTML = "";

  if (!payload.threads.length) {
    elements.resultsRoot.appendChild(emptyNode("No context matched the current filters."));
    return;
  }

  payload.threads.forEach((group) => {
    const card = document.createElement("section");
    card.className = "context-group";
    card.innerHTML = `
      <h3>${escapeHtml(group.thread_id)}</h3>
      <div class="meta-line">
        ${badge(group.project_id)}
        ${badge(group.platform)}
        ${badge(group.source_product)}
        ${badge(group.runtime_vendor)}
        ${badge(group.source_surface)}
        ${badge(`${group.message_count} msg`)}
      </div>
    `;
    group.events.forEach((event) => {
      card.appendChild(
        renderEntry(
          event.role,
          event.timestamp_observed,
          event.content_markdown,
          event.event_type,
          {
            isMatch: false,
            highlightTerms: [],
          }
        )
      );
    });
    elements.resultsRoot.appendChild(card);
  });
}

function renderEntry(role, timestamp, content, eventType, options) {
  const node = document.createElement("div");
  node.className = `context-event role-${escapeClass(role)}`;
  if (options.isMatch) {
    node.classList.add("is-match");
  }
  node.innerHTML = `
    <div class="entry-head">
      <span class="entry-role">${escapeHtml(role)} / ${escapeHtml(eventType)}</span>
      <span>${escapeHtml(timestamp || "")}</span>
    </div>
    <div class="entry-content">${renderMarkdown(content || "")}</div>
  `;
  if (options.highlightTerms.length) {
    highlightTerms(node.querySelector(".entry-content"), options.highlightTerms);
  }
  return node;
}

function showEmptyState(message) {
  elements.resultsTitle.textContent = "Results";
  elements.resultsMeta.textContent = "";
  elements.resultsRoot.innerHTML = "";
  elements.resultsRoot.appendChild(emptyNode(message));
}

function emptyNode(message) {
  const node = document.createElement("div");
  node.className = "empty-state";
  node.textContent = message;
  return node;
}

function badge(value) {
  if (!value) {
    return "";
  }
  return `<span class="pill">${escapeHtml(String(value))}</span>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeClass(value) {
  return String(value || "unknown").replace(/[^a-z0-9_-]+/gi, "-");
}

function renderMarkdown(markdown) {
  const normalized = String(markdown || "").replace(/\r/g, "");
  const lines = normalized.split("\n");
  const html = [];
  let paragraph = [];
  let listType = null;
  let listItems = [];
  let codeFence = false;
  let codeLines = [];
  let tableBuffer = [];

  function flushParagraph() {
    if (!paragraph.length) {
      return;
    }
    html.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  }

  function flushList() {
    if (!listType || !listItems.length) {
      listType = null;
      listItems = [];
      return;
    }
    const items = listItems.map((item) => `<li>${renderInline(item)}</li>`).join("");
    html.push(`<${listType}>${items}</${listType}>`);
    listType = null;
    listItems = [];
  }

  function flushTable() {
    if (!tableBuffer.length) {
      return;
    }
    if (tableBuffer.length >= 2 && /^\|\s*[-:| ]+\|?$/.test(tableBuffer[1])) {
      const header = splitTableRow(tableBuffer[0]);
      const bodyRows = tableBuffer.slice(2).map(splitTableRow);
      const headHtml = `<thead><tr>${header.map((cell) => `<th>${renderInline(cell)}</th>`).join("")}</tr></thead>`;
      const bodyHtml = bodyRows.length
        ? `<tbody>${bodyRows
            .map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join("")}</tr>`)
            .join("")}</tbody>`
        : "";
      html.push(`<table>${headHtml}${bodyHtml}</table>`);
    } else {
      tableBuffer.forEach((row) => paragraph.push(row));
    }
    tableBuffer = [];
  }

  for (const line of lines) {
    if (codeFence) {
      if (line.startsWith("```")) {
        html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeFence = false;
        codeLines = [];
      } else {
        codeLines.push(line);
      }
      continue;
    }

    if (line.startsWith("```")) {
      flushParagraph();
      flushList();
      flushTable();
      codeFence = true;
      codeLines = [];
      continue;
    }

    if (/^\|.*\|$/.test(line.trim())) {
      flushParagraph();
      flushList();
      tableBuffer.push(line.trim());
      continue;
    }

    if (tableBuffer.length) {
      flushTable();
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      html.push(`<h${headingMatch[1].length}>${renderInline(headingMatch[2])}</h${headingMatch[1].length}>`);
      continue;
    }

    const blockquoteMatch = line.match(/^>\s?(.*)$/);
    if (blockquoteMatch) {
      flushParagraph();
      flushList();
      html.push(`<blockquote>${renderInline(blockquoteMatch[1])}</blockquote>`);
      continue;
    }

    const unorderedMatch = line.match(/^\s*-\s+(.*)$/);
    if (unorderedMatch) {
      flushParagraph();
      if (listType && listType !== "ul") {
        flushList();
      }
      listType = "ul";
      listItems.push(unorderedMatch[1]);
      continue;
    }

    const orderedMatch = line.match(/^\s*\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType && listType !== "ol") {
        flushList();
      }
      listType = "ol";
      listItems.push(orderedMatch[1]);
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  if (codeFence) {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  flushTable();
  flushParagraph();
  flushList();
  return html.join("");
}

function renderInline(text) {
  let value = escapeHtml(text);
  value = value.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  value = value.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  value = value.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  value = value.replace(/`([^`]+)`/g, "<code>$1</code>");
  return value;
}

function splitTableRow(row) {
  return row
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function buildSearchTerms(query) {
  return Array.from(
    new Set(
      query
        .replaceAll('"', " ")
        .split(/\s+/)
        .map((term) => term.trim())
        .filter((term) => term.length >= 2)
    )
  );
}

function highlightTerms(root, terms) {
  if (!root || !terms.length) {
    return;
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    nodes.push(walker.currentNode);
  }

  nodes.forEach((textNode) => {
    const text = textNode.textContent;
    if (!text || !terms.some((term) => text.toLowerCase().includes(term.toLowerCase()))) {
      return;
    }

    const fragment = document.createDocumentFragment();
    let cursor = 0;
    while (cursor < text.length) {
      const match = findNextMatch(text, cursor, terms);
      if (!match) {
        fragment.appendChild(document.createTextNode(text.slice(cursor)));
        break;
      }
      if (match.index > cursor) {
        fragment.appendChild(document.createTextNode(text.slice(cursor, match.index)));
      }
      const mark = document.createElement("mark");
      mark.textContent = text.slice(match.index, match.index + match.term.length);
      fragment.appendChild(mark);
      cursor = match.index + match.term.length;
    }
    textNode.parentNode.replaceChild(fragment, textNode);
  });
}

function findNextMatch(text, startIndex, terms) {
  let best = null;
  terms.forEach((term) => {
    const index = text.toLowerCase().indexOf(term.toLowerCase(), startIndex);
    if (index === -1) {
      return;
    }
    if (!best || index < best.index) {
      best = { index, term };
    }
  });
  return best;
}

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

bootstrap().catch((error) => {
  console.error(error);
  showEmptyState(`Shell failed to load: ${error.message}`);
});
