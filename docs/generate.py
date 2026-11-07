"""Render the docs/*.md pages to committed .html files with a shared shell.

Markdown is the single source of truth: edit the ``.md`` file, run
``uv run python docs/generate.py``, and commit the regenerated ``.html``.
Stdlib + the ``markdown`` dev dependency only (``fenced_code`` and ``tables``
extensions); the shell (title, sidebar nav, stylesheet reference) is injected
around the rendered body. The output is deterministic — regenerating from
unchanged Markdown produces byte-identical HTML.
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

import markdown

DOCS_DIR = Path(__file__).resolve().parent

# (nav label, markdown path, output path) — the landing page first, then the
# 12 Python module pages (flat), the 3 static UI pages (static/), the 2
# deployment config pages (deploy/), and the provider config template page.
PAGES = [
    ("index", "index.md", "index.html"),
    ("app/__init__.py", "__init__.md", "__init__.html"),
    ("app/main.py", "main.md", "main.html"),
    ("app/chain.py", "chain.md", "chain.html"),
    ("app/fetchers.py", "fetchers.md", "fetchers.html"),
    ("app/urls.py", "urls.md", "urls.html"),
    ("app/errors.py", "errors.md", "errors.html"),
    ("app/persist.py", "persist.md", "persist.html"),
    ("app/library.py", "library.md", "library.html"),
    ("app/providers.py", "providers.md", "providers.html"),
    ("app/summarize.py", "summarize.md", "summarize.html"),
    ("app/log.py", "log.md", "log.html"),
    ("app/logbus.py", "logbus.md", "logbus.html"),
    ("app/static/app.js", "static/app-js.md", "static/app-js.html"),
    ("app/static/index.html", "static/index-html.md", "static/index-html.html"),
    ("app/static/style.css", "static/style-css.md", "static/style-css.html"),
    # Deployment configs — 2 entries under deploy/
    ("Dockerfile", "deploy/Dockerfile.md", "deploy/Dockerfile.html"),
    ("docker-compose.yml", "deploy/compose-yml.md", "deploy/compose-yml.html"),
    # Config artifacts
    ("providers.json.example", "providers-json-example.md", "providers-json-example.html"),
]

EXTENSIONS = ["fenced_code", "tables"]

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title} — yt-transcript code docs</title>
<link rel="stylesheet" href="{css}" />
</head>
<body>
<nav class="sidebar">
<h1>yt-transcript docs</h1>
<ul>
{nav}
</ul>
</nav>
<main class="content">
{body}
</main>
</body>
</html>
"""


def _rel(href_source: str, href_target: str) -> str:
    """Relative link from one generated file under docs/ to another."""
    source_dir = (DOCS_DIR / href_source).parent
    return os.path.relpath(DOCS_DIR / href_target, start=source_dir).replace(
        os.sep, "/"
    )


def render_page(label: str, md_rel: str, html_rel: str) -> str:
    """Render one .md file wrapped in the shared shell."""
    md_path = DOCS_DIR / md_rel
    body = markdown.markdown(
        md_path.read_text(encoding="utf-8"), extensions=EXTENSIONS
    )
    nav_items = []
    for nav_label, _nav_md, nav_html in PAGES:
        href = _rel(html_rel, nav_html)
        current = ' aria-current="page"' if nav_html == html_rel else ""
        nav_items.append(
            f'  <li><a href="{href}"{current}>{html.escape(nav_label)}</a></li>'
        )
    return PAGE_TEMPLATE.format(
        title=html.escape(label),
        css=_rel(html_rel, "style.css"),
        nav="\n".join(nav_items),
        body=body,
    )


def main() -> None:
    rendered = 0
    for label, md_rel, html_rel in PAGES:
        if not (DOCS_DIR / md_rel).exists():
            print(f"skipped (no {md_rel} yet): {html_rel}", file=sys.stderr)
            continue
        out_path = DOCS_DIR / html_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_page(label, md_rel, html_rel), encoding="utf-8")
        rendered += 1
    print(f"rendered {rendered} of {len(PAGES)} pages under {DOCS_DIR}")


if __name__ == "__main__":
    main()
