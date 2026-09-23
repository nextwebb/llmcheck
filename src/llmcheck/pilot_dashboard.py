from __future__ import annotations

import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .pilot import summarize_pilot
from .storage.sqlite import list_knowledge_entries, list_pilot_reviews


def _build_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LLMCheck Pilot Dashboard</title>
  <style>
    :root {
      --bg: #f6efe5;
      --panel: #fffdf9;
      --ink: #1f2937;
      --muted: #6b7280;
      --edge: #dfd3c3;
      --accent: #a63d40;
      --ok: #166534;
      --warn: #92400e;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Georgia, 'Times New Roman', serif; color: var(--ink); background: linear-gradient(180deg, #f7f2ea, #efe5d6); }
    .wrap { max-width: 1240px; margin: 0 auto; padding: 28px 20px 48px; }
    .hero { margin-bottom: 18px; }
    h1 { margin: 0 0 8px; font-size: 44px; }
    .lead { font-size: 18px; line-height: 1.5; max-width: 880px; color: #243241; }
    .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 16px; }
    .card, .panel { background: var(--panel); border: 1px solid var(--edge); border-radius: 18px; box-shadow: 0 10px 24px rgba(0,0,0,0.05); }
    .card { padding: 16px; }
    .card .k { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
    .card .v { font-size: 28px; font-weight: 700; margin-top: 8px; }
    .panel { padding: 18px; margin-top: 16px; }
    h2 { margin: 0 0 12px; color: var(--accent); }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { border-bottom: 1px solid var(--edge); text-align: left; padding: 10px 8px; vertical-align: top; }
    th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font: 12px/1 ui-monospace, monospace; }
    .ok { background: #dcfce7; color: var(--ok); }
    .warn { background: #fef3c7; color: var(--warn); }
    code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .small { color: var(--muted); font-size: 13px; }
    .split { display: grid; grid-template-columns: 1.3fr .7fr; gap: 16px; }
    @media (max-width: 900px) { .split { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="badge warn">Pilot mode: measure the thesis before scaling the product</div>
      <h1>LLMCheck Pilot Dashboard</h1>
      <div class="lead">This dashboard is intentionally narrow. It shows whether reviewed incidents are actually missing-context problems, whether they repeat, and whether the approved knowledge loop is worth keeping.</div>
    </div>

    <div class="grid" id="summary"></div>

    <div class="split">
      <div class="panel">
        <h2>Recent Pilot Reviews</h2>
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Workflow</th>
              <th>Root Cause</th>
              <th>Outcome</th>
              <th>Reusable</th>
              <th>Knowledge</th>
            </tr>
          </thead>
          <tbody id="reviews"></tbody>
        </table>
      </div>

      <div class="panel">
        <h2>Knowledge Entries</h2>
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Title</th>
              <th>Usage</th>
            </tr>
          </thead>
          <tbody id="knowledge"></tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h2>Kill Test</h2>
      <div class="small" id="killtest"></div>
    </div>
  </div>
  <script>
    const summaryNode = document.getElementById('summary');
    const reviewsNode = document.getElementById('reviews');
    const knowledgeNode = document.getElementById('knowledge');
    const killNode = document.getElementById('killtest');

    const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[ch]));
    const pct = (v) => `${Math.round((v || 0) * 100)}%`;
    const card = (k, v) => `<div class="card"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(v)}</div></div>`;

    async function refresh() {
      const res = await fetch('/api/pilot', { cache: 'no-store' });
      const data = await res.json();
      const summary = data.summary || {};
      summaryNode.innerHTML = [
        card('Total Reviews', summary.total_reviews ?? 0),
        card('Confirmed Failures', summary.confirmed_failures ?? 0),
        card('Missing Context Share', pct(summary.missing_context_share)),
        card('Reusable Pattern Share', pct(summary.reusable_pattern_share)),
        card('Knowledge Approval Rate', pct(summary.knowledge_approval_rate)),
        card('Repeat Pattern Share', pct(summary.repeat_pattern_share)),
      ].join('');

      const reviews = data.reviews || [];
      reviewsNode.innerHTML = reviews.length ? reviews.map(r => `
        <tr>
          <td><code>${escapeHtml(r.run_id)}</code><div class="small">${escapeHtml(r.created_at)}</div></td>
          <td>${escapeHtml(r.workflow)}</td>
          <td>${escapeHtml(r.root_cause)}${r.missing_context_subtype ? `<div class="small">${escapeHtml(r.missing_context_subtype)}</div>` : ''}</td>
          <td>${escapeHtml(r.review_outcome)}</td>
          <td>${r.reusable_pattern ? '<span class="badge ok">yes</span>' : 'no'}</td>
          <td>${escapeHtml(r.candidate_knowledge_type)}${r.knowledge_approved ? '<div class="small">approved</div>' : ''}</td>
        </tr>`).join('') : '<tr><td colspan="6" class="small">No pilot reviews yet.</td></tr>';

      const knowledge = data.knowledge || [];
      knowledgeNode.innerHTML = knowledge.length ? knowledge.map(k => `
        <tr>
          <td>${escapeHtml(k.knowledge_type)}</td>
          <td><strong>${escapeHtml(k.title)}</strong><div class="small">${escapeHtml(k.confidence)}</div></td>
          <td>${escapeHtml((k.usage_modes || []).join(', '))}</td>
        </tr>`).join('') : '<tr><td colspan="3" class="small">No approved knowledge entries yet.</td></tr>';

      killNode.innerHTML = `
        <div>- Missing context share should be meaningfully high or the memory story is weak.</div>
        <div>- Reusable pattern share should be high enough to justify operationalization.</div>
        <div>- Knowledge approval rate should stay high, or reviewer output is too noisy.</div>
        <div class="small">Updated ${escapeHtml(data.generated_at || 'unknown')}</div>
      `;
    }

    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>"""


def serve_pilot_dashboard(storage_path: Path, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _write_json(
            self,
            payload: dict[str, Any],
            status: HTTPStatus = HTTPStatus.OK,
            *,
            body: bool = True,
        ) -> None:
            encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(encoded)

        def _write_html(self, html: str, status: HTTPStatus = HTTPStatus.OK, *, body: bool = True) -> None:
            encoded = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(encoded)

        def _pilot_payload(self) -> dict[str, Any]:
            reviews = list_pilot_reviews(storage_path, limit=200)
            knowledge = list_knowledge_entries(storage_path, limit=200)
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": summarize_pilot(reviews),
                "reviews": [review.__dict__ for review in reviews],
                "knowledge": [entry.__dict__ for entry in knowledge],
            }

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                self._write_html(_build_index_html())
                return
            if self.path == "/api/pilot":
                self._write_json(self._pilot_payload())
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_HEAD(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                self._write_html(_build_index_html(), body=False)
                return
            if self.path == "/api/pilot":
                self._write_json(self._pilot_payload(), body=False)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"LLMCheck pilot dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping LLMCheck pilot dashboard.")
    finally:
        server.server_close()
