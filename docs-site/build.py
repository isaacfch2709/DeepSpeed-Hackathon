#!/usr/bin/env python3
"""
Render the hackathon documentation into a static site.

The prose lives on the track branches (`README.md` + `docs/*.md`); this script
is checked out from `main` and renders whatever it is pointed at, so the docs
stay plain Markdown that reads fine on GitHub and the site is a build artefact.

    python3 docs-site/build.py --out _site \
        --src track1=/path/to/track1/checkout \
        --src track2=/path/to/track2/checkout

Styling comes from the DeepSpeed design system (see docs-site/theme/).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

import markdown
from markdown.extensions.toc import TocExtension
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# Anchors
#
# The Markdown sources already cross-link to GitHub-rendered anchors such as
# `#24-ground-truth-odometry--use-it`. GitHub keeps a dash per space and drops
# punctuation without collapsing the gap, which Python-Markdown's own slugify
# does not do. Match GitHub so every existing deep link keeps working.
# --------------------------------------------------------------------------
def gh_slugify(text: str, _sep: str = "-") -> str:
    slug = html.unescape(text).strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    return re.sub(r"\s", "-", slug, flags=re.UNICODE)


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------
def load_template(name: str) -> str:
    return (HERE / "templates" / name).read_text(encoding="utf-8")


def fill(template: str, **slots: str) -> str:
    out = template
    for key, value in slots.items():
        out = out.replace("{{%s}}" % key.upper(), value)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if leftover:
        raise SystemExit(f"unfilled template slots: {sorted(set(leftover))}")
    return out


# --------------------------------------------------------------------------
# Markdown post-processing
# --------------------------------------------------------------------------
CODE_RE = re.compile(
    r'<pre><code(?: class="language-(?P<lang>[^"]+)")?>(?P<body>.*?)</code></pre>',
    re.DOTALL,
)

LANG_LABEL = {
    "sh": "shell", "bash": "shell", "console": "shell", "shell": "shell",
    "powershell": "powershell", "ps1": "powershell",
    "py": "python", "python": "python",
    "yml": "yaml", "yaml": "yaml",
    "json": "json", "xml": "xml", "cpp": "c++", "c": "c",
    "text": "", "": "",
}


def render_code_blocks(body: str) -> str:
    """Swap Markdown's bare <pre><code> for a highlighted, labelled panel."""

    def one(match: re.Match) -> str:
        lang = (match.group("lang") or "").strip()
        source = html.unescape(match.group("body"))
        marked = html.escape(source)
        if lang:
            try:
                lexer = get_lexer_by_name(lang, stripall=False)
                marked = highlight(source, lexer, HtmlFormatter(nowrap=True))
            except ClassNotFound:
                pass
        label = LANG_LABEL.get(lang.lower(), lang.lower())
        tag = f'<span class="code-lang">{html.escape(label)}</span>' if label else ""
        return f'<div class="code"><pre><code>{marked}</code></pre>{tag}</div>'

    return CODE_RE.sub(one, body)


def wrap_tables(body: str) -> str:
    """Tables get a scroll container so wide spec tables survive on phones."""
    return body.replace("<table>", '<div class="tbl"><table>').replace(
        "</table>", "</table></div>"
    )


HREF_RE = re.compile(r'(<a\b[^>]*?\bhref=")([^"]+)(")')
EXTERNAL = ("http://", "https://", "mailto:", "//")


def link_rewriter(repo: str, branch: str):
    """
    Turn the repository-relative links in the Markdown into site links (for
    other chapters) or GitHub links (for source files that are not rendered).
    """
    base = f"https://github.com/{repo}"

    def to_github(path: str) -> str:
        kind = "tree" if path.endswith("/") else "blob"
        return f"{base}/{kind}/{branch}/{path.rstrip('/')}"

    def resolve(href: str) -> tuple[str, bool]:
        if href.startswith("#") or href.startswith(EXTERNAL):
            return href, href.startswith(EXTERNAL)

        target, _, anchor = href.partition("#")
        anchor = f"#{anchor}" if anchor else ""

        # Up one level: the chapter files live in docs/, so `../x` is repo-root.
        if target.startswith("../"):
            rest = target[3:]
            if rest in ("README.md", ""):
                return f"index.html{anchor}", False
            return to_github(rest) + anchor, True

        # Sibling chapter, or the README pointing into docs/.
        stem = target[len("docs/"):] if target.startswith("docs/") else target
        if stem.endswith(".md") and "/" not in stem:
            if stem == "README.md":
                return f"index.html{anchor}", False
            return f"{stem[:-3]}.html{anchor}", False

        if not target:
            return href, False
        return to_github(target) + anchor, True

    def apply(body: str) -> str:
        def one(match: re.Match) -> str:
            href, external = resolve(match.group(2))
            attrs = match.group(1) + html.escape(href, quote=True) + match.group(3)
            return attrs + (' data-ext="1"' if external else "")

        return HREF_RE.sub(one, body)

    return apply


# --------------------------------------------------------------------------
# Platforms
#
# The setup instructions differ by host OS, and the Markdown says so in two
# ways: `install/<platform>/…` in the commands, and a run of per-platform
# headings under "Install Docker". Both are turned into one switch here.
#
# Nothing is rewritten at run time. Every variant is emitted and CSS shows the
# one matching `<html data-platform>`, which means the page is correct before
# the JavaScript runs, and a copy button lifts the right command because
# innerText skips what is `display: none`.
# --------------------------------------------------------------------------
PLATFORMS = (
    ("linux", "Linux", ("linux", "ubuntu", "debian")),
    ("macos", "macOS", ("macos", "mac os", "osx", "apple silicon")),
    ("windows", "Windows", ("windows", "wsl", "powershell")),
)
PLATFORM_IDS = tuple(p[0] for p in PLATFORMS)
PLATFORM_LABEL = {p[0]: p[1] for p in PLATFORMS}


def platform_of(text: str) -> str | None:
    """The single platform a heading is about, or None if it is not about one."""
    low = re.sub(r"<[^>]+>", " ", text).lower()
    hits = {pid for pid, _, words in PLATFORMS if any(w in low for w in words)}
    return hits.pop() if len(hits) == 1 else None


def platforms_in(text: str) -> list:
    low = re.sub(r"<[^>]+>", " ", text).lower()
    return [pid for pid, _, words in PLATFORMS if any(w in low for w in words)]


def platform_switch(extra: str = "") -> str:
    buttons = "".join(
        f'<button type="button" data-set-pf="{pid}">{e(label)}</button>'
        for pid, label, _ in PLATFORMS
    )
    return (
        f'<div class="pf-switch {extra}" role="group" aria-label="Platform">{buttons}</div>'
    )


PLATFORM_PATH_RE = re.compile(r"install/(%s)/" % "|".join(PLATFORM_IDS))
TEXT_NODE_RE = re.compile(r">([^<]+)<")


def swap_platform_paths(body: str) -> str:
    """`install/linux/` follows the reader's platform wherever it is written."""

    def variants(_match: re.Match) -> str:
        return "install/" + "".join(
            f'<span class="pf" data-pf="{pid}">{pid}</span>' for pid in PLATFORM_IDS
        ) + "/"

    def in_text(match: re.Match) -> str:
        return ">" + PLATFORM_PATH_RE.sub(variants, match.group(1)) + "<"

    # Only text nodes — never an href, so the GitHub links keep their branch path.
    return TEXT_NODE_RE.sub(in_text, body)


# "# or install/macos, or install/windows from WSL" is there for GitHub, where
# there is no switch. On the site the path above it is already correct.
ALT_COMMENT_RE = re.compile(
    r'(?:<span class="w">\s*</span>|\s)*<span class="c[^"]*">#\s*or install/[^<]*</span>'
)


def hide_platform_alternatives(body: str) -> str:
    return ALT_COMMENT_RE.sub(lambda m: f'<span class="pf-alt">{m.group(0)}</span>', body)


HEADING_RE = re.compile(r"^<(h2|h3|hr)\b([^>]*)>(.*?)(?:</\1>)?$", re.IGNORECASE)
HEADING_ID_RE = re.compile(r'id="([^"]+)"')


def group_platform_sections(body: str) -> tuple:
    """
    Fold a run of consecutive per-platform <h3> sections into one switchable
    group. Returns the rewritten body and {heading id: platform} so the
    contents list can hide the entries it no longer shows.
    """
    lines = body.split("\n")

    # Where each top-level h2/h3/hr starts, so a section is a line range.
    marks = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            marks.append((i, m.group(1).lower(), m.group(3)))

    # A run is >= 2 adjacent h3 marks, each about exactly one platform, with
    # nothing but their own bodies in between.
    runs, current = [], []
    for index, (line_no, tag, text) in enumerate(marks):
        pid = platform_of(text) if tag == "h3" else None
        if pid:
            current.append((index, line_no, pid))
        else:
            if len(current) >= 2:
                runs.append(current)
            current = []
    if len(current) >= 2:
        runs.append(current)

    owned = {}
    edits = []
    for run in runs:
        for position, (index, line_no, pid) in enumerate(run):
            end = marks[index + 1][0] if index + 1 < len(marks) else len(lines)
            ident = HEADING_ID_RE.search(lines[line_no])
            if ident:
                owned[ident.group(1)] = pid
            edits.append((line_no, end, pid, position == 0))

    for start, end, pid, first in sorted(edits, reverse=True):
        opener = f'<div class="pf-block" data-pf="{pid}">'
        if first:
            opener = (
                '<div class="pf-tabs"><span class="eyebrow">Your platform</span>'
                + platform_switch()
                + "</div>\n"
                + opener
            )
        lines[start:end] = [opener] + lines[start:end] + ["</div>"]

    return "\n".join(lines), owned


SCOPE_RE = re.compile(r"^(<h[23]\b[^>]*>)(.*?)(</h[23]>)$", re.IGNORECASE)


def annotate_platform_scope(body: str) -> str:
    """
    A heading like "1.6 Running the simulator on your host (macOS, Windows)"
    names who it is for. Say so to everyone else rather than hiding it — the
    prose cross-references these sections by number.
    """
    out = []
    for line in body.split("\n"):
        match = SCOPE_RE.match(line)
        out.append(line)
        if not match:
            continue
        # Drop the permalink anchor first — it would sit after the bracket.
        heading = re.sub(r'<a class="hl".*?</a>', "", match.group(2))
        tail = re.search(r"\(([^)]*)\)\s*$", re.sub(r"<[^>]+>", "", heading).strip())
        if not tail:
            continue
        named = platforms_in(tail.group(1))
        if not named or len(named) == len(PLATFORM_IDS):
            continue
        others = [p for p in PLATFORM_IDS if p not in named]
        listed = " and ".join(PLATFORM_LABEL[p] for p in named)
        out.append(
            f'<p class="pf-scope" data-pf="{" ".join(others)}">'
            f"This section is for {e(listed)}. You can skip it on "
            f'{e(" and ".join(PLATFORM_LABEL[p] for p in others))}.</p>'
        )
    return "\n".join(out)


# --------------------------------------------------------------------------
# Page model
# --------------------------------------------------------------------------
class Page:
    def __init__(self, slug: str, title: str, body: str, toc: list, source: str,
                 platform_headings: dict | None = None):
        self.slug = slug          # "index" or "04-algorithms"
        self.title = title        # "4. Algorithms to start from"
        self.body = body
        self.toc = toc
        self.source = source      # path within the branch, for the "edit" link
        # {heading id: platform} for headings inside a per-platform section,
        # so the contents list hides what the page is not showing.
        self.platform_headings = platform_headings or {}

    @property
    def href(self) -> str:
        return f"{self.slug}.html"

    @property
    def number(self) -> str:
        match = re.match(r"(\d+)", self.slug)
        return match.group(1) if match else "00"

    @property
    def short(self) -> str:
        """'4. Algorithms to start from' -> 'Algorithms to start from'."""
        if self.slug == "index":
            return "Overview"
        return re.sub(r"^\d+\.\s*", "", self.title)


def first_heading(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Untitled"


def convert(md_text: str, repo: str, branch: str, source: str) -> Page:
    md = markdown.Markdown(
        extensions=[
            "extra",
            "sane_lists",
            TocExtension(
                slugify=gh_slugify,
                toc_depth="2-3",
                permalink="#",
                permalink_class="hl",
                permalink_title="Link to this section",
            ),
        ],
        output_format="html5",
    )
    title = first_heading(md_text)

    # The <h1> is rendered by the template, not by the body.
    stripped = re.sub(r"^#\s+.*?$\n?", "", md_text, count=1, flags=re.MULTILINE)
    body = md.convert(stripped)
    body = render_code_blocks(body)
    body = wrap_tables(body)
    body = link_rewriter(repo, branch)(body)

    # Platform passes run last: grouping walks top-level headings line by line,
    # so it has to see the finished block structure.
    body, platform_headings = group_platform_sections(body)
    body = annotate_platform_scope(body)
    body = hide_platform_alternatives(body)
    body = swap_platform_paths(body)

    slug = Path(source).stem
    if slug == "README":
        slug = "index"
    return Page(slug, title, body, getattr(md, "toc_tokens", []), source, platform_headings)


def render_toc(tokens: list, owned: dict | None = None) -> str:
    if not tokens:
        return ""
    owned = owned or {}
    out = ["<ul>"]
    for node in tokens:
        pid = owned.get(node["id"])
        attr = f' data-pf="{pid}"' if pid else ""
        out.append(
            f'<li{attr}><a href="#{html.escape(node["id"])}">{html.escape(node["name"])}</a>'
        )
        if node.get("children"):
            out.append(render_toc(node["children"], owned))
        out.append("</li>")
    out.append("</ul>")
    return "".join(out)


# --------------------------------------------------------------------------
# Site assembly
# --------------------------------------------------------------------------
def e(text: str) -> str:
    return html.escape(str(text), quote=True)


def header(cfg: dict, *, active: str, prefix: str) -> str:
    repo_url = f"https://github.com/{cfg['repo']}"
    links = []
    for track in cfg["tracks"]:
        on = " on" if active == track["id"] else ""
        links.append(
            f'<a class="{on.strip()}" href="{prefix}{track["id"]}/index.html">{e(track["name"])}</a>'
        )
    nav = "".join(links)
    return f"""<header class="hdr">
  <a class="hdr-brand" href="{prefix}index.html">
    <span class="wm">DeepSpeed</span>
    <span class="sub">Hackathon 26/27</span>
  </a>
  <nav class="hdr-nav" aria-label="Tracks">{nav}</nav>
  <div class="hdr-right">
    <span class="hdr-meta">Deadline <b>{e(cfg['deadline'])}</b></span>
    <a class="hdr-meta" href="{repo_url}">GitHub</a>
    {platform_switch("pf-switch--hdr")}
    <button class="toggle" type="button" aria-label="Switch theme">
      <span class="t-light">Light</span><span class="t-dark">Dark</span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none"/></svg>
    </button>
    <button class="navbtn" type="button" aria-label="Contents" aria-expanded="false" aria-controls="sidenav">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
    </button>
  </div>
</header>"""


def footer(cfg: dict, *, prefix: str) -> str:
    repo_url = f"https://github.com/{cfg['repo']}"
    return f"""<footer class="ft"><div class="ft-in">
  <span>NTU DeepSpeed &middot; Recruitment Hackathon 26/27</span>
  <nav>
    <a href="{prefix}track1/index.html">Track 1</a>
    <a href="{prefix}track2/index.html">Track 2</a>
    <a href="{repo_url}">Repository</a>
    <a href="mailto:{e(cfg['contact'])}">{e(cfg['contact'])}</a>
  </nav>
</div></footer>"""


def sidebar(cfg: dict, track: dict, pages: list, current: Page) -> str:
    switch = []
    for other in cfg["tracks"]:
        on = ' aria-current="true"' if other["id"] == track["id"] else ""
        switch.append(
            f'<a href="../{other["id"]}/index.html"{on}>'
            f'<span class="n">{e(other["num"])}</span><span>{e(other["short"])}</span></a>'
        )

    items = []
    for page in pages:
        on = ' aria-current="page"' if page.slug == current.slug else ""
        label = "00" if page.slug == "index" else page.number
        items.append(
            f'<li><a href="{page.href}"{on}><span class="n">{label}</span>'
            f"<span>{e(page.short)}</span></a></li>"
        )

    repo_url = f"https://github.com/{cfg['repo']}"
    return f"""<aside class="nav" id="sidenav">
  <div class="nav-lbl">Select track</div>
  <div class="nav-switch">{''.join(switch)}</div>
  <div class="nav-lbl">Your platform</div>
  {platform_switch("pf-switch--nav")}
  <div class="nav-lbl">{e(track['name'])} &middot; Contents</div>
  <ul class="nav-list">{''.join(items)}</ul>
  <div class="nav-lbl">Elsewhere</div>
  <div class="nav-out">
    <a href="{repo_url}/tree/{e(track['branch'])}">Branch <code>{e(track['branch'])}</code></a>
    <a href="mailto:{e(cfg['contact'])}">Ask a question</a>
  </div>
</aside>"""


def pager(pages: list, current: Page) -> str:
    index = pages.index(current)
    parts = []
    if index > 0:
        prev = pages[index - 1]
        parts.append(
            f'<a class="prev" href="{prev.href}">'
            f'<span class="arw">&larr;</span>'
            f'<span><span class="k">Previous</span>'
            f'<span class="t">{e(prev.short)}</span></span></a>'
        )
    if index < len(pages) - 1:
        nxt = pages[index + 1]
        parts.append(
            f'<a class="next" href="{nxt.href}">'
            f'<span><span class="k">Next</span>'
            f'<span class="t">{e(nxt.short)}</span></span>'
            f'<span class="arw">&rarr;</span></a>'
        )
    return f'<nav class="pager">{"".join(parts)}</nav>' if parts else ""


def build_track(cfg: dict, track: dict, src: Path, out: Path, tpl: str, assets: dict) -> list:
    repo, branch = cfg["repo"], track["branch"]

    sources = [("README.md", src / "README.md")]
    for path in sorted((src / "docs").glob("*.md")):
        sources.append((f"docs/{path.name}", path))

    pages = [
        convert(path.read_text(encoding="utf-8"), repo, branch, rel)
        for rel, path in sources
        if path.exists()
    ]
    if not pages:
        raise SystemExit(f"no Markdown found for {track['id']} under {src}")

    dest = out / track["id"]
    dest.mkdir(parents=True, exist_ok=True)

    for page in pages:
        toc = render_toc(page.toc, page.platform_headings)
        crumb = (
            f'<span class="red">{e(track["name"])}</span><span class="sep">/</span>'
            + (
                "<span>Overview</span>"
                if page.slug == "index"
                else f'<a href="index.html">Overview</a><span class="sep">/</span>'
                f"<span>Chapter {page.number}</span>"
            )
        )
        source_url = f"https://github.com/{repo}/blob/{branch}/{page.source}"
        html_out = fill(
            tpl,
            lang="en",
            title=f"{page.title} &middot; {track['name']} &middot; DeepSpeed Hackathon 26/27",
            description=e(track["lede"]),
            prefix="../",
            tokens_css=assets["tokens.css"],
            docs_css=assets["docs.css"],
            app_js=assets["app.js"],
            header=header(cfg, active=track["id"], prefix="../"),
            sidebar=sidebar(cfg, track, pages, page),
            crumb=crumb,
            heading=e(page.title),
            body=page.body,
            toc=f'<div class="nav-lbl">On this page</div>{toc}' if toc else "",
            pager=pager(pages, page),
            source_url=source_url,
            source_path=e(page.source),
            footer=footer(cfg, prefix="../"),
        )
        (dest / f"{page.slug}.html").write_text(html_out, encoding="utf-8")

    return pages


def deck(cfg: dict, assets: dict) -> str:
    """
    The info-talk slides: a viewer that loads on demand, and the file itself.

    The plate is the deck's own title slide, rendered out of the PDF, so the
    talk names itself and nothing here repeats what the picture already says.
    The PDF behind it weighs more than the rest of the landing page put
    together, so nothing fetches it until a reader asks: `app.js` swaps the
    plate for an inline viewer on a wide screen, and with JavaScript off, or
    on a phone — where an embedded PDF is unreadable in every browser worth
    naming — the same link opens the file in a tab of its own instead.
    """
    talk = cfg["talk"]
    cover = talk["cover"]
    src = assets[talk["file"]]

    facts = "".join(
        f'<div class="row"><span class="k">{e(k)}</span><span class="v">{v}</span></div>'
        for k, v in talk["facts"]
    )
    agenda = "".join(
        f'<li><span class="n">{e(num)}</span>'
        f'<span class="t">{e(title)}</span><span class="d">{e(note)}</span></li>'
        for num, title, note in talk["agenda"]
    )

    return f"""<div class="deck">
  <div class="deck-main">
    <div class="deck-view" data-pdf="{src}" data-pdf-title="{e(talk['title'])}">
      <a class="deck-plate" href="{src}" target="_blank" rel="noopener">
        <img class="deck-cover" src="{assets[cover['src']]}" alt="{e(cover['alt'])}"
             width="{cover['w']}" height="{cover['h']}" loading="lazy" decoding="async">
        <span class="deck-bar">
          <span class="deck-bar__c">View the slides <span class="arw" aria-hidden="true">&rarr;</span></span>
          <span class="deck-bar__f">PDF &middot; {e(talk['size'])} &middot; {e(talk['slides'])} slides</span>
        </span>
      </a>
    </div>
    <div class="deck-act">
      <a class="btn accent" href="{src}" target="_blank" rel="noopener">Open in a new tab</a>
      <a class="btn ghost" href="{src}" download>Download the PDF</a>
    </div>
  </div>
  <aside class="deck-side">
    <div class="spec">{facts}</div>
    <ol class="deck-ag">{agenda}</ol>
  </aside>
</div>"""


def build_landing(cfg: dict, tracks_pages: dict, out: Path, assets: dict) -> None:
    cards = []
    for track in cfg["tracks"]:
        specs = "".join(
            f'<div class="row"><span class="k">{e(k)}</span><span class="v">{v}</span></div>'
            for k, v in track["specs"]
        )
        # `paper` marks a map drawn as dark ink on white, which the dark theme
        # has to flip; a screenshot of the simulator is already dark.
        m = track["map"]
        cls = "tmap-fig paper" if m.get("paper") else "tmap-fig"
        circuit = (
            f'<div class="{cls}">'
            f'<img src="{assets[m["src"]]}" alt="{e(m["alt"])}"'
            f' width="{m["w"]}" height="{m["h"]}" loading="lazy" decoding="async">'
            f"</div>"
        )
        cards.append(
            f"""<a class="tcard" href="{track['id']}/index.html">
  <span class="tcard-n" aria-hidden="true">{e(track['num'])}</span>
  <div class="eyebrow">{e(track['name'])} &middot; {e(track['tag'])}</div>
  <h3>{e(track['title'])}</h3>
  <p class="lede">{e(track['lede'])}</p>
  {circuit}
  <div class="spec">{specs}</div>
  <div class="tcard-foot"><span>{e(track['cta'])}</span><span class="arw">&rarr;</span></div>
</a>"""
        )

    shared = "".join(
        f'<div class="row-item"><span class="k">{e(row[0])}</span>'
        f'<span class="v{" red" if len(row) > 2 and row[2] else ""}">{row[1]}</span>'
        f'<span class="n">{row[3] if len(row) > 3 else ""}</span></div>'
        for row in cfg["shared"]
    )

    stats = "".join(
        f'<div class="stat-panel{" hot" if s.get("hot") else ""}">'
        f'<div class="k">{e(s["k"])}</div>'
        f'<div class="v">{s["v"]}</div>'
        f'<div class="foot">{e(s["foot"])}</div></div>'
        for s in cfg["stats"]
    )

    # One row per chapter, with a link into each track's version of it.
    first = cfg["tracks"][0]["id"]
    numbers = [p.number for p in tracks_pages[first] if p.slug != "index"]
    chapters = []
    for number in numbers:
        links = []
        title = ""
        for track in cfg["tracks"]:
            match = next(
                (p for p in tracks_pages[track["id"]] if p.number == number and p.slug != "index"),
                None,
            )
            if not match:
                continue
            title = title or match.short
            links.append(f'<a href="{track["id"]}/{match.href}">{e(track["name"])}</a>')
        blurb = cfg["chapter_notes"].get(number, "")
        chapters.append(
            f'<div class="row-item"><span class="k">Chapter {e(number)}</span>'
            f'<span class="v">{e(title)}<br><span style="color:var(--fg-muted);font-weight:400">{e(blurb)}</span></span>'
            f'<span class="n">{" &middot; ".join(links)}</span></div>'
        )

    quickstart = []
    for track in cfg["tracks"]:
        lines = []
        for line in track["quickstart"]:
            escaped = e(line)
            if line.lstrip().startswith("#"):
                escaped = f'<span class="c">{escaped}</span>'
            lines.append(escaped)
        quickstart.append(
            f'<div><div class="eyebrow" style="margin-bottom:var(--s-3)">'
            f'{e(track["name"])} &middot; branch <span class="r">{e(track["branch"])}</span></div>'
            f'<pre>{chr(10).join(lines)}</pre></div>'
        )
    quick_html = swap_platform_paths("".join(quickstart))

    tpl = load_template("index.html")
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(
        fill(
            tpl,
            lang="en",
            title=f"{cfg['org']} &middot; {cfg['title']}",
            description=e(cfg["description"]),
            prefix="",
            tokens_css=assets["tokens.css"],
            docs_css=assets["docs.css"],
            app_js=assets["app.js"],
            header=header(cfg, active="", prefix=""),
            hero_lede=e(cfg["description"]),
            hero_switch=platform_switch("pf-switch--hero"),
            deadline_full=e(cfg["deadline_full"]),
            register_url=e(cfg["register"]["url"]),
            register_cta=e(cfg["register"]["cta"]),
            register_deadline_full=e(cfg["register"]["deadline_full"]),
            stats=stats,
            tracks="".join(cards),
            talk_lede=e(cfg["talk"]["lede"]),
            talk=deck(cfg, assets),
            shared=shared,
            chapters="".join(chapters),
            quick_switch=platform_switch("pf-switch--quick"),
            quickstart=quick_html,
            repo_url=f"https://github.com/{cfg['repo']}",
            contact=e(cfg["contact"]),
            footer=footer(cfg, prefix=""),
        ),
        encoding="utf-8",
    )


def build_404(cfg: dict, out: Path, assets: dict) -> None:
    (out / "404.html").write_text(
        fill(
            load_template("404.html"),
            lang="en",
            title="Off track &middot; DeepSpeed Hackathon 26/27",
            description="Page not found.",
            prefix="",
            tokens_css=assets["tokens.css"],
            docs_css=assets["docs.css"],
            app_js=assets["app.js"],
            header=header(cfg, active="", prefix=""),
            footer=footer(cfg, prefix=""),
        ),
        encoding="utf-8",
    )


def copy_assets(out: Path) -> dict:
    """
    Copy the theme out, fingerprinting the stylesheet and the script.

    GitHub Pages serves everything with `Cache-Control: max-age=600`, so for ten
    minutes after a deploy a returning reader can hold a stale stylesheet while
    already having the new HTML — which is exactly how a feature driven by CSS
    and JS appears broken. A content hash in the filename makes that impossible:
    new markup can only ever reference the assets it was built against.

    Returns {source name: published path relative to the site root}.
    """
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    published = {}
    for name in ("tokens.css", "docs.css", "app.js"):
        source = HERE / "theme" / name
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()[:10]
        stem, _, suffix = name.partition(".")
        target = f"{stem}.{digest}.{suffix}"
        (assets / target).write_bytes(data)
        published[name] = f"assets/{target}"

    for item in (HERE / "static").glob("*"):
        # README.md in there documents the assets; it is not one of them.
        if item.is_file() and item.name != "README.md":
            shutil.copy2(item, assets / item.name)
            published[item.name] = f"assets/{item.name}"

    # GitHub Pages must serve the tree as-is, not run Jekyll over it.
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return published


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="_site", type=Path)
    parser.add_argument(
        "--src",
        action="append",
        default=[],
        metavar="TRACK=DIR",
        help="checkout of a track branch, e.g. track1=/tmp/track1",
    )
    parser.add_argument("--config", default=HERE / "site.json", type=Path)
    args = parser.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    roots = dict(pair.split("=", 1) for pair in args.src)
    missing = [t["id"] for t in cfg["tracks"] if t["id"] not in roots]
    if missing:
        parser.error(f"no --src given for: {', '.join(missing)}")

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    assets = copy_assets(out)

    page_tpl = load_template("page.html")
    pages = {}
    for track in cfg["tracks"]:
        src = Path(roots[track["id"]])
        pages[track["id"]] = build_track(cfg, track, src, out, page_tpl, assets)
        print(f"  {track['id']}: {len(pages[track['id']])} pages", file=sys.stderr)

    build_landing(cfg, pages, out, assets)
    build_404(cfg, out, assets)

    total = sum(len(p) for p in pages.values()) + 2
    print(f"built {total} pages into {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
