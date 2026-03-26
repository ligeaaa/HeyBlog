"""Serve the in-app operator HTML panel."""

from __future__ import annotations

from fastapi.responses import HTMLResponse


PANEL_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HeyBlog Panel</title>
    <link rel="icon" href="data:," />
    <link rel="stylesheet" href="/static/panel.css" />
  </head>
  <body>
    <main class="layout">
      <header class="hero">
        <div>
          <p class="eyebrow">HeyBlog Operator Console</p>
          <h1>Observe crawl behavior without leaving the browser</h1>
          <p class="lede">
            Trigger seed import and crawl runs, then inspect status, blogs, logs,
            and graph totals in one place.
          </p>
        </div>
        <a class="docs-link" href="/docs">Open API Docs</a>
      </header>

      <section class="controls card">
        <div class="control-row">
          <button id="bootstrap-button" class="action primary">Bootstrap Seeds</button>
          <label class="field">
            <span>Max nodes</span>
            <input id="max-nodes-input" type="number" min="1" placeholder="10" />
          </label>
          <button id="crawl-button" class="action">Run Crawl</button>
          <button id="refresh-button" class="ghost">Refresh</button>
        </div>
        <p id="action-status" class="action-status">Ready.</p>
      </section>

      <section class="cards" id="status-cards"></section>

      <section class="grid">
        <article class="card">
          <div class="section-head">
            <h2>Stats</h2>
            <span class="section-note">From <code>/api/stats</code></span>
          </div>
          <div id="stats-block" class="stats-block"></div>
        </article>

        <article class="card">
          <div class="section-head">
            <h2>Graph Summary</h2>
            <span class="section-note">Client-derived from <code>/api/graph</code></span>
          </div>
          <div id="graph-summary" class="graph-summary"></div>
        </article>
      </section>

      <section class="grid logs-and-table">
        <article class="card table-card">
          <div class="section-head">
            <h2>Blogs</h2>
            <span class="section-note">From <code>/api/blogs</code></span>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Domain</th>
                  <th>Status</th>
                  <th>Depth</th>
                  <th>Status Code</th>
                  <th>Friend Links</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody id="blogs-table-body"></tbody>
            </table>
          </div>
        </article>

        <article class="card logs-card">
          <div class="section-head">
            <h2>Recent Logs</h2>
            <span class="section-note">From <code>/api/logs</code></span>
          </div>
          <div id="logs-panel" class="logs-panel"></div>
        </article>
      </section>
    </main>

    <script src="/static/panel.js"></script>
  </body>
</html>
"""


def panel_response() -> HTMLResponse:
    """Return the static operator panel HTML response."""
    return HTMLResponse(PANEL_HTML)
