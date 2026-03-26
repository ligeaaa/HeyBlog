const actionStatus = document.getElementById("action-status");
const bootstrapButton = document.getElementById("bootstrap-button");
const crawlButton = document.getElementById("crawl-button");
const refreshButton = document.getElementById("refresh-button");
const maxNodesInput = document.getElementById("max-nodes-input");
const statusCards = document.getElementById("status-cards");
const statsBlock = document.getElementById("stats-block");
const blogsTableBody = document.getElementById("blogs-table-body");
const logsPanel = document.getElementById("logs-panel");
const graphSummary = document.getElementById("graph-summary");

function clearChildren(element) {
  element.replaceChildren();
}

function textElement(tagName, text, className = "") {
  const element = document.createElement(tagName);
  element.textContent = text;
  if (className) {
    element.className = className;
  }
  return element;
}

function setActionStatus(message, tone = "neutral") {
  actionStatus.textContent = message;
  actionStatus.className = "action-status";
  if (tone === "success" || tone === "error") {
    actionStatus.classList.add(tone);
  }
}

function setBusy(isBusy) {
  bootstrapButton.disabled = isBusy;
  crawlButton.disabled = isBusy;
  refreshButton.disabled = isBusy;
  maxNodesInput.disabled = isBusy;
}

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function renderCards(status) {
  const cards = [
    ["Blogs", status.total_blogs],
    ["Edges", status.total_edges],
    ["Pending", status.pending_tasks],
    ["Processing", status.processing_tasks],
    ["Finished", status.finished_tasks],
    ["Failed", status.failed_tasks],
  ];
  clearChildren(statusCards);
  for (const [label, value] of cards) {
    const card = document.createElement("article");
    card.className = "card metric-card";
    card.append(textElement("h3", label));
    card.append(textElement("strong", String(value ?? 0)));
    statusCards.append(card);
  }
}

function renderStats(stats) {
  const distribution = Object.entries(stats.status_counts || {})
    .map(([key, value]) => `${key}: ${value}`)
    .join(", ") || "No data";
  clearChildren(statsBlock);
  for (const [label, value] of [
    ["Max Depth", stats.max_depth ?? 0],
    ["Average Friend Links", Number(stats.average_friend_links ?? 0).toFixed(2)],
    ["Status Distribution", distribution],
  ]) {
    const row = document.createElement("div");
    row.className = "stats-row";
    row.append(textElement("span", label));
    row.append(textElement("strong", String(value)));
    statsBlock.append(row);
  }
}

function renderBlogs(blogs) {
  clearChildren(blogsTableBody);
  if (!blogs.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "empty-state";
    cell.textContent = "No blogs yet.";
    row.append(cell);
    blogsTableBody.append(row);
    return;
  }

  for (const blog of blogs) {
    const row = document.createElement("tr");
    row.append(textElement("td", String(blog.id)));
    row.append(textElement("td", blog.domain));

    const statusCell = document.createElement("td");
    statusCell.append(textElement("span", blog.crawl_status, "status-pill"));
    row.append(statusCell);

    row.append(textElement("td", String(blog.depth)));
    row.append(textElement("td", blog.status_code == null ? "—" : String(blog.status_code)));
    row.append(textElement("td", String(blog.friend_links_count)));
    row.append(textElement("td", formatDate(blog.updated_at)));
    blogsTableBody.append(row);
  }
}

function renderLogs(logs) {
  clearChildren(logsPanel);
  if (!logs.length) {
    logsPanel.append(textElement("p", "No logs yet.", "empty-state"));
    return;
  }

  for (const log of logs.slice(0, 10)) {
    const item = document.createElement("article");
    item.className = "log-line";
    item.append(textElement("strong", `${log.stage} · ${log.result}`));
    item.append(textElement("div", log.message));
    item.append(textElement("small", formatDate(log.created_at)));
    logsPanel.append(item);
  }
}

function renderGraph(graph) {
  const recentEdges = (graph.edges || []).slice(-5).reverse();
  clearChildren(graphSummary);

  for (const [label, value] of [
    ["Node Count", graph.nodes.length],
    ["Edge Count", graph.edges.length],
  ]) {
    const row = document.createElement("div");
    row.className = "graph-row";
    row.append(textElement("span", label));
    row.append(textElement("strong", String(value)));
    graphSummary.append(row);
  }

  if (!recentEdges.length) {
    graphSummary.append(textElement("p", "No edges yet.", "empty-state"));
    return;
  }

  for (const edge of recentEdges) {
    const row = document.createElement("div");
    row.className = "graph-row";
    row.append(textElement("span", `${edge.from_blog_id} → ${edge.to_blog_id}`));
    row.append(textElement("strong", edge.link_text || edge.link_url_raw));
    graphSummary.append(row);
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function refreshDashboard() {
  const [status, stats, blogs, logs, graph] = await Promise.all([
    fetchJson("/api/status"),
    fetchJson("/api/stats"),
    fetchJson("/api/blogs"),
    fetchJson("/api/logs"),
    fetchJson("/api/graph"),
  ]);

  renderCards(status);
  renderStats(stats);
  renderBlogs(blogs);
  renderLogs(logs);
  renderGraph(graph);
}

async function handleAction(label, requestFactory) {
  try {
    setBusy(true);
    setActionStatus(`${label} in progress...`);
    const result = await requestFactory();
    await refreshDashboard();
    setActionStatus(`${label} complete: ${JSON.stringify(result)}`, "success");
  } catch (error) {
    setActionStatus(`${label} failed: ${error.message}`, "error");
  } finally {
    setBusy(false);
  }
}

bootstrapButton.addEventListener("click", () =>
  handleAction("Bootstrap", () =>
    fetchJson("/api/crawl/bootstrap", { method: "POST" }),
  ),
);

crawlButton.addEventListener("click", () =>
  handleAction("Crawl", () => {
    const maxNodes = maxNodesInput.value.trim();
    const query = maxNodes ? `?max_nodes=${encodeURIComponent(maxNodes)}` : "";
    return fetchJson(`/api/crawl/run${query}`, { method: "POST" });
  }),
);

refreshButton.addEventListener("click", async () => {
  try {
    setBusy(true);
    await refreshDashboard();
    setActionStatus("Dashboard refreshed.", "success");
  } catch (error) {
    setActionStatus(`Refresh failed: ${error.message}`, "error");
  } finally {
    setBusy(false);
  }
});

refreshDashboard()
  .then(() => setActionStatus("Ready."))
  .catch((error) => setActionStatus(`Initial load failed: ${error.message}`, "error"));
