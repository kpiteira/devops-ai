# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown-it-py>=3.0", "mdit-py-plugins>=0.4"]
# ///
"""Build one self-contained HTML page from a set of Markdown files: a tab per file,
mermaid diagrams with a zoom view, and comment threads kept in the artifact's database.

    uv run --script build.py --title "kspec · reminders" --out page.html SPEC.md

Prints one line per document, `<slug>\t<path>`: a comment thread's `doc` field is that
slug, which is how the session that published the page finds the file a comment is on.
Slugs come from the file's path inside its repository, so they survive rebuilds.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import html
import os
import pathlib
import re
import subprocess
import sys
from typing import Any

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

ASSETS = pathlib.Path(__file__).parent / "assets"
FONTS = (
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Source+Sans+3:wght@400;600"
    '&family=IBM+Plex+Mono:wght@400;500&display=swap">'
)
TAGS = re.compile(r"<[^>]+>")


@dataclasses.dataclass
class Doc:
    path: pathlib.Path  # resolved
    shown: str  # repo/relative/path.md, as a reader knows it
    slug: str  # tab id, and the `doc` field of comment threads on it
    label: str  # tab label: the file name without .md


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def shown_path(path: pathlib.Path) -> str:
    """The path relative to its repository root, prefixed by the repository name."""
    try:
        top = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return f"{pathlib.Path(top).name}/{path.relative_to(top)}"
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return os.path.relpath(path)


def markdown(slug: str) -> MarkdownIt:
    # raw HTML is shown as text: a reviewed file puts no markup or script on the page
    md = (
        MarkdownIt("commonmark", {"html": False})
        .enable(["table", "strikethrough"])
        .use(footnote_plugin)
        .use(tasklists_plugin)
        .use(
            anchors_plugin,
            min_level=1,
            max_level=4,
            slug_func=lambda s: f"{slug}--{slugify(s)}",
        )
    )
    default_fence = md.renderer.rules["fence"]  # type: ignore[attr-defined]

    def fence(self: Any, tokens: Any, idx: int, options: Any, env: Any) -> str:
        # the viewer renders <pre class="mermaid"> natively
        if tokens[idx].info.strip() == "mermaid":
            return f'<pre class="mermaid">{html.escape(tokens[idx].content)}</pre>\n'
        return str(default_fence(tokens, idx, options, env))

    md.add_render_rule("fence", fence)
    return md


def render(doc: Doc, docs: list[Doc]) -> str:
    out = markdown(doc.slug).render(doc.path.read_text(encoding="utf-8"))
    # footnote ids are per document in Markdown but share one page here
    out = re.sub(r'(id="|href="#)(fn(?:ref)?\d+(?::\d+)?)"', rf'\1{doc.slug}--\2"', out)
    # tables scroll sideways instead of widening the page
    out = out.replace("<table>", '<div class="tablewrap"><table>')
    out = out.replace("</table>", "</table></div>")

    by_path = {d.path: d.slug for d in docs}

    def target(ref: str) -> str | None:
        """The tab a .md reference names: resolved from this document's folder,
        else the one document whose path ends with it."""
        hit = by_path.get((doc.path.parent / ref).resolve())
        if hit:
            return hit
        tail = [d.slug for d in docs if str(d.path).endswith("/" + ref.lstrip("./"))]
        return tail[0] if len(tail) == 1 else None

    def href(m: re.Match[str]) -> str:
        ref, _, frag = html.unescape(m.group(1)).partition("#")
        slug = target(ref)
        if not slug:
            return m.group(0)
        return f'href="#{slug}--{slugify(frag)}"' if frag else f'href="#{slug}"'

    def mention(m: re.Match[str]) -> str:
        if m.group(1):  # already a link: leave it, never nest one inside another
            return m.group(1)
        slug = target(m.group(2))
        return (
            f'<a href="#{slug}"><code>{m.group(2)}</code></a>' if slug else m.group(0)
        )

    # links between the documents, then bare `FILE.md` mentions, open the matching tab
    out = re.sub(r'href="(?![a-z]+:)([^"#]+\.md(?:#[^"]*)?)"', href, out)
    return re.sub(
        r"(<a\b[^>]*>.*?</a>)|<code>([A-Za-z0-9._/-]+\.md)</code>",
        mention,
        out,
        flags=re.S,
    )


def toc(fragment: str) -> str:
    items = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', fragment, flags=re.S)
    if len(items) < 2:
        return ""
    lis = "".join(f'<li><a href="#{i}">{TAGS.sub("", t)}</a></li>' for i, t in items)
    return (
        '<nav class="toc" aria-label="Contents"><span class="eyebrow">Contents</span>'
        f"<ol>{lis}</ol></nav>"
    )


def panel(doc: Doc, docs: list[Doc]) -> str:
    frag = render(doc, docs)
    m = re.search(r"<h1[^>]*>(.*?)</h1>\s*", frag, flags=re.S)
    title = html.unescape(TAGS.sub("", m.group(1))) if m else doc.label
    if m:
        frag = frag[: m.start()] + frag[m.end() :]
    mtime = datetime.datetime.fromtimestamp(doc.path.stat().st_mtime)
    changed = mtime.strftime("%-d %B %Y, %H:%M")
    return (
        f'<article id="p-{doc.slug}" class="panel doc" data-slug="{doc.slug}" hidden>\n'
        f'<div class="doc-head"><h1 class="doc-title">{html.escape(title)}</h1>'
        f'<span class="path">{html.escape(doc.shown)} · last changed {changed}</span>'
        f'</div>\n{toc(frag)}<div class="prose">\n{frag}</div>\n</article>'
    )


def page(title: str, reviewer: str, docs: list[Doc]) -> str:
    tabs = "".join(
        f'<button type="button" role="tab" data-doc="{d.slug}" aria-selected="false">'
        f"{html.escape(d.label)}</button>"
        for d in docs
    )
    nav = (
        '<nav class="tabs" aria-label="Documents" '
        f'data-reviewer="{html.escape(reviewer)}"><div class="row" role="tablist">'
        f'<span class="name">{html.escape(title)}</span>{tabs}</div></nav>'
    )
    css = "".join(
        (ASSETS / n).read_text() for n in ("page.css", "comments.css", "zoom.css")
    )
    js = "".join(
        (ASSETS / n).read_text() for n in ("tabs.js", "comments.js", "zoom.js")
    )
    panels = "\n".join(panel(d, docs) for d in docs)
    return (
        f"<title>{html.escape(title)}</title>\n{FONTS}\n<style>\n{css}</style>\n"
        f"{nav}\n{panels}\n{js}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--title", required=True, help="names the page: keep it unique")
    ap.add_argument(
        "--reviewer",
        default="Reviewer",
        help="name a person comments under until they set their own",
    )
    ap.add_argument("--out", required=True, type=pathlib.Path, help="HTML to write")
    ap.add_argument(
        "files", nargs="+", type=pathlib.Path, help="one tab each, in order"
    )
    args = ap.parse_args()

    docs: list[Doc] = []
    for f in args.files:
        path = f.resolve()
        if not path.is_file():
            print(f"kpage: not a file: {f}", file=sys.stderr)
            return 2
        if any(d.path == path for d in docs):
            continue
        shown = shown_path(path)
        slug = slugify(shown.split("/", 1)[-1])
        if any(d.slug == slug for d in docs):  # same path in two repositories
            slug = slugify(shown)
        base, n = slug, 2
        while any(d.slug == slug for d in docs):  # paths that slugify alike
            slug, n = f"{base}-{n}", n + 1
        docs.append(Doc(path, shown, slug, path.stem))

    out = page(args.title, args.reviewer, docs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding="utf-8")
    for d in docs:
        print(f"{d.slug}\t{d.path}")
    size = len(out.encode()) / 1024
    print(
        f"kpage: wrote {args.out} ({size:.0f} KB, {len(docs)} documents)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
