#!/usr/bin/env python3
"""
Validate every internal link and fragment in a built site.

    python3 docs-site/check_links.py _site

External links are not fetched; this only proves the site is self-consistent,
which is what the cross-chapter anchors in the Markdown actually depend on.
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

EXTERNAL = ("http://", "https://", "mailto:", "//", "data:")


class Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.refs: list[str] = []

    def handle_starttag(self, tag, attrs):
        got = dict(attrs)
        if got.get("id"):
            self.ids.add(got["id"])
        if tag == "a" and got.get("href"):
            self.refs.append(got["href"])
        elif tag in ("link", "script", "img") and (got.get("href") or got.get("src")):
            self.refs.append(got.get("href") or got.get("src"))


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    if not root.is_dir():
        print(f"no such directory: {root}", file=sys.stderr)
        return 2

    pages: dict[Path, Scan] = {}
    for path in sorted(root.rglob("*.html")):
        scan = Scan()
        scan.feed(path.read_text(encoding="utf-8"))
        pages[path] = scan

    broken: list[str] = []
    refs = 0
    for path, scan in pages.items():
        here = path.relative_to(root)
        for ref in scan.refs:
            if ref.startswith(EXTERNAL):
                continue
            refs += 1
            target, _, fragment = ref.partition("#")
            if not target:
                if fragment and fragment not in scan.ids:
                    broken.append(f"{here}: #{fragment} — no such heading")
                continue
            dest = (path.parent / target).resolve()
            if not dest.exists():
                broken.append(f"{here}: {ref} — no such file")
            elif fragment and dest in pages and fragment not in pages[dest].ids:
                broken.append(f"{here}: {ref} — no such heading in target")

    if broken:
        print(f"{len(broken)} broken internal reference(s):", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"{len(pages)} pages, {refs} internal references, all resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
