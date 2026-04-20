from __future__ import annotations

import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _list_report_files(report_dir: Path) -> list[dict[str, Any]]:
    if not report_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob("*.json"), reverse=True):
        stat = path.stat()
        results.append(
            {
                "name": path.name,
                "path": str(path),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return results


def _build_index_html() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>LLMCheck Dashboard</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #111827;
      --ok: #16a34a;
      --bad: #dc2626;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --edge: #1f2937;
      --accent: #0ea5e9;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      color: var(--text);
      background: radial-gradient(circle at 10% 10%, #12213f, var(--bg));
      min-height: 100vh;
      padding: 18px;
    }
    .wrap {
      max-width: 1100px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }
    .panel {
      background: color-mix(in srgb, var(--panel) 92%, black);
      border: 1px solid var(--edge);
      border-radius: 10px;
      padding: 14px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    h1 { margin: 0; font-size: 18px; }
    .badge {
      padding: 3px 9px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 12px;
    }
    .ok { background: color-mix(in srgb, var(--ok) 22%, transparent); color: #86efac; }
    .bad { background: color-mix(in srgb, var(--bad) 22%, transparent); color: #fca5a5; }
    .muted { color: var(--muted); font-size: 12px; }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
    }
    .stat {
      border: 1px solid var(--edge);
      border-radius: 8px;
      padding: 10px;
      background: #0b1222;
    }
    .stat .k { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
    .stat .v { font-size: 20px; font-weight: 700; margin-top: 4px; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--edge);
      text-align: left;
      padding: 8px;
      vertical-align: top;
    }
    th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
    code {
      font-size: 12px;
      background: #0b1222;
      border: 1px solid var(--edge);
      border-radius: 6px;
      padding: 1px 6px;
    }
    a { color: var(--accent); }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <div class=\"header\">
        <h1>LLMCheck Dashboard</h1>
        <div id=\"status\" class=\"badge bad\">NO DATA</div>
      </div>
      <div class=\"muted\" id=\"meta\">Waiting for report...</div>
    </div>

    <div class=\"panel\">
      <div class=\"stats\" id=\"stats\"></div>
    </div>

    <div class=\"panel\">
      <h1 style=\"font-size:15px; margin-bottom:8px;\">Failed Checks</h1>
      <table>
        <thead>
          <tr><th>Suite</th><th>Case</th><th>Check</th><th>Message</th></tr>
        </thead>
        <tbody id=\"failures\"></tbody>
      </table>
    </div>

    <div class=\"panel\">
      <h1 style=\"font-size:15px; margin-bottom:8px;\">Report Files</h1>
      <div id=\"files\" class=\"muted\"></div>
    </div>
  </div>

  <script>
    const statsNode = document.getElementById('stats');
    const failuresNode = document.getElementById('failures');
    const metaNode = document.getElementById('meta');
    const statusNode = document.getElementById('status');
    const filesNode = document.getElementById('files');

    function setStatus(pass) {
      if (pass) {
        statusNode.textContent = 'PASS';
        statusNode.className = 'badge ok';
      } else {
        statusNode.textContent = 'FAIL';
        statusNode.className = 'badge bad';
      }
    }

    function statCard(key, value) {
      return `<div class=\"stat\"><div class=\"k\">${key}</div><div class=\"v\">${value}</div></div>`;
    }

    async function refresh() {
      try {
        const latestRes = await fetch('/api/latest', { cache: 'no-store' });
        const latest = await latestRes.json();

        if (!latest.exists || !latest.report) {
          setStatus(false);
          metaNode.textContent = 'No report yet. Run `llmcheck run` first.';
          statsNode.innerHTML = '';
          failuresNode.innerHTML = '<tr><td colspan="4" class="muted">No data</td></tr>';
        } else {
          const report = latest.report;
          const counts = report.counts || {};
          setStatus(Boolean(report.passed));
          metaNode.textContent = `Updated: ${latest.generated_at || 'unknown'} | Source: ${latest.path}`;

          const safe = (v) => (v === undefined || v === null ? 0 : v);
          statsNode.innerHTML = [
            statCard('Total Cases', safe(counts.total_cases)),
            statCard('Passed Cases', safe(counts.passed_cases)),
            statCard('Failed Cases', safe(counts.failed_cases)),
            statCard('Total Checks', safe(counts.total_checks)),
            statCard('Failed Checks', safe(counts.failed_checks)),
            statCard('Runtime Errors', safe(counts.runtime_error_cases)),
          ].join('');

          const rows = [];
          for (const [suite, cases] of Object.entries(report.suites || {})) {
            for (const c of cases) {
              for (const chk of c.checks || []) {
                if (!chk.passed) {
                  rows.push(`<tr><td><code>${suite}</code></td><td><code>${c.case_id}</code></td><td><code>${chk.check_type}</code></td><td>${chk.message}</td></tr>`);
                }
              }
            }
          }
          failuresNode.innerHTML = rows.length ? rows.join('') : '<tr><td colspan="4" class="muted">No failed checks</td></tr>';
        }

        const filesRes = await fetch('/api/reports', { cache: 'no-store' });
        const files = await filesRes.json();
        const list = files.files || [];
        filesNode.innerHTML = list.length
          ? list.map(f => `<div><code>${f.name}</code> <span class=\"muted\">(${f.size} bytes, ${f.modified})</span></div>`).join('')
          : 'No report files found.';
      } catch (e) {
        setStatus(false);
        metaNode.textContent = `Dashboard error: ${String(e)}`;
      }
    }

    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


def serve_dashboard(report_dir: Path, host: str, port: int) -> None:
    latest_path = report_dir / "latest.json"

    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _write_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/?"):
                self._write_html(_build_index_html())
                return

            if self.path == "/api/latest":
                payload = _read_json(latest_path)
                if payload is None:
                    self._write_json({"exists": False, "path": str(latest_path), "report": None})
                    return
                self._write_json(
                    {
                        "exists": True,
                        "path": str(latest_path),
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "report": payload,
                    }
                )
                return

            if self.path == "/api/reports":
                self._write_json({"files": _list_report_files(report_dir)})
                return

            self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"LLMCheck dashboard running at http://{host}:{port}")
    print(f"Watching reports in: {report_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
