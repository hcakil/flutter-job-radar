"""HTML report renderer."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Sequence

from store import JobRow

BUCKET_COLOR = {
    "GREEN": "#1a7f37",
    "YELLOW": "#9a6700",
    "RED": "#cf222e",
}


def render_html(
    jobs: Sequence[JobRow],
    *,
    output_path: str | Path,
    title: str = "Flutter Job Radar",
    run_note: str = "",
) -> Path:
    path = Path(output_path)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = []
    for job in jobs:
        color = BUCKET_COLOR.get(job.bucket, "#666")
        snippet = escape(job.snippet or "")
        rows.append(
            f"""
            <article class="job" data-bucket="{escape(job.bucket)}">
              <div class="badge" style="background:{color}">{escape(job.bucket)} · {job.score}</div>
              <h2><a href="{escape(job.url)}" rel="noopener noreferrer">{escape(job.title)}</a></h2>
              <p class="meta">{escape(job.source)}{" · " + escape(job.age) if job.age else ""}</p>
              <p class="snippet">{snippet}</p>
              <p class="matched"><code>{escape(job.matched)}</code></p>
            </article>
            """
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f6f4ef;
      --ink: #1c1917;
      --muted: #57534e;
      --card: #fffdf8;
      --line: #e7e5e4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
      background:
        radial-gradient(1200px 600px at 10% -10%, #dde8df 0%, transparent 55%),
        radial-gradient(900px 500px at 100% 0%, #efe6d8 0%, transparent 50%),
        var(--bg);
      color: var(--ink);
      line-height: 1.45;
    }}
    main {{
      max-width: 820px;
      margin: 0 auto;
      padding: 2.5rem 1.25rem 4rem;
    }}
    header h1 {{
      font-size: clamp(2rem, 4vw, 2.75rem);
      letter-spacing: -0.02em;
      margin: 0 0 0.35rem;
    }}
    header p {{ color: var(--muted); margin: 0 0 1.75rem; }}
    .job {{
      padding: 1.1rem 0 1.25rem;
      border-top: 1px solid var(--line);
    }}
    .badge {{
      display: inline-block;
      color: #fff;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.75rem;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      margin-bottom: 0.4rem;
    }}
    h2 {{
      font-size: 1.2rem;
      margin: 0 0 0.35rem;
      font-weight: 650;
    }}
    h2 a {{ color: inherit; text-decoration: none; }}
    h2 a:hover {{ text-decoration: underline; }}
    .meta, .matched {{ color: var(--muted); font-size: 0.92rem; margin: 0.2rem 0; }}
    .snippet {{ margin: 0.45rem 0; }}
    code {{ font-size: 0.8rem; word-break: break-word; }}
    footer {{ margin-top: 2rem; color: var(--muted); font-size: 0.9rem; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(title)}</h1>
      <p>Generated {escape(generated)}{(" — " + escape(run_note)) if run_note else ""}</p>
    </header>
    {"".join(rows) if rows else "<p>No jobs matched this run.</p>"}
    <footer>{len(jobs)} listings · Flutter Job Radar V1</footer>
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path
