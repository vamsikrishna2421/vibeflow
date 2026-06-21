"""Optional, local, capped dictation history.

Off by default. When the user turns it on, each delivered dictation is appended
to a small JSON file in the per-user app-data folder, capped to the most recent N
entries. Nothing leaves the machine; the user can open a searchable view or clear
it at any time — the same privacy posture as VibeFlow's other learning features
(opt-in, disclosed, local, capped, clearable).

The storage + HTML rendering are kept pure/parameterised (a ``path`` argument and
plain data in/out) so they're easy to unit-test without touching the real
profile directory.
"""

from __future__ import annotations

import html
import json
import time
from pathlib import Path

HISTORY_FILENAME = "dictation_history.json"
DEFAULT_MAX = 500


def history_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    from .config import config_dir

    return config_dir() / HISTORY_FILENAME


def load(path: Path | None = None) -> list[dict]:
    """Return the stored entries (newest last). Never raises."""
    p = history_path(path)
    try:
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append(text: str, app: str = "", *, max_entries: int = DEFAULT_MAX,
           path: Path | None = None) -> None:
    """Append one dictation, keeping only the most recent ``max_entries``.

    Never raises — history must never interfere with delivering a dictation.
    """
    text = (text or "").strip()
    if not text:
        return
    p = history_path(path)
    try:
        entries = load(p)
        entries.append({"ts": int(time.time()), "app": app or "", "text": text})
        if max_entries and len(entries) > max_entries:
            entries = entries[-max_entries:]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def clear(path: Path | None = None) -> None:
    """Delete all stored history. Never raises."""
    p = history_path(path)
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def render_html(entries: list[dict]) -> str:
    """Render a self-contained, searchable HTML page (no external assets).

    User text is HTML-escaped. The search box filters rows client-side.
    """
    rows = []
    for e in reversed(entries or []):  # newest first
        when = ""
        try:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(e.get("ts", 0))))
        except Exception:
            when = ""
        app = html.escape(str(e.get("app") or ""))
        text = html.escape(str(e.get("text") or ""))
        rows.append(
            f'<tr class="row"><td class="when">{when}</td>'
            f'<td class="app">{app}</td><td class="text">{text}</td></tr>'
        )
    body = "\n".join(rows) or (
        '<tr><td colspan="3" class="empty">No dictations recorded yet.</td></tr>'
    )
    count = len(entries or [])
    return _PAGE.replace("{{ROWS}}", body).replace("{{COUNT}}", str(count))


_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>VibeFlow — dictation history</title>
<style>
  :root{--bg:#faf7f2;--card:#fffdfa;--ink:#241f2b;--muted:#7a7385;--line:#ece4d8;--accent:#5b54e6}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .wrap{max-width:1000px;margin:0 auto;padding:32px 22px 60px}
  h1{font-size:26px;margin:0 0 2px;letter-spacing:-.01em}
  .sub{color:var(--muted);font-size:13px;margin-bottom:18px}
  #q{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:12px;
    font-size:15px;background:var(--card);margin-bottom:16px}
  #q:focus{outline:none;border-color:var(--accent)}
  table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
    border-radius:14px;overflow:hidden}
  th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #f4eee4;vertical-align:top}
  th{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
  td.when{white-space:nowrap;color:var(--muted);font-size:12.5px;width:120px}
  td.app{white-space:nowrap;color:#5a5366;font-size:13px;width:120px}
  td.text{white-space:pre-wrap;word-break:break-word}
  tr.row:hover td{background:#fbf8f3}
  .empty{color:var(--muted);text-align:center;padding:26px}
  .count{color:var(--muted);font-size:12.5px;margin-top:10px}
</style></head>
<body><div class="wrap">
  <h1>Dictation history</h1>
  <div class="sub">Private and local — stored only on this PC. Clear it anytime from the VibeFlow tray.</div>
  <input id="q" type="search" placeholder="Search your dictations…" autofocus/>
  <table><thead><tr><th>When</th><th>App</th><th>Text</th></tr></thead>
  <tbody id="rows">
{{ROWS}}
  </tbody></table>
  <div class="count"><span id="shown">{{COUNT}}</span> of {{COUNT}} shown</div>
<script>
  var q=document.getElementById('q'),rows=[].slice.call(document.querySelectorAll('#rows tr.row')),shown=document.getElementById('shown');
  q.addEventListener('input',function(){var t=q.value.toLowerCase(),n=0;
    rows.forEach(function(r){var m=r.textContent.toLowerCase().indexOf(t)>=0;r.style.display=m?'':'none';if(m)n++;});
    shown.textContent=n;});
</script>
</div></body></html>"""
