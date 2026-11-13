"""ATO reference library shipped with the code: ATO guides (PDF, HTML, text) kept in the
repo's ato-library/ folder, their text extracted once into library.json, which the release
build bundles into every plugin. Offline word search and exact-quote checks for citations."""

import hashlib
import html.parser
import json
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import date
from pathlib import Path

SUFFIXES = (".pdf", ".html", ".htm", ".txt", ".md")
STALE_DAYS = 365
SNIPPET_TOKENS = 40
MANIFEST = "library.json"


def library_dir():
    """<code>/ato-library: the repo folder next to accounting_core/, or the copy bundled
    next to a plugin's scripts/. AI_ACCOUNTING_LIBRARY overrides it (tests)."""
    if os.environ.get("AI_ACCOUNTING_LIBRARY"):
        return Path(os.environ["AI_ACCOUNTING_LIBRARY"])
    return Path(__file__).resolve().parent.parent / "ato-library"


def load():
    path = library_dir() / MANIFEST
    if not path.exists():
        return []
    return json.loads(path.read_text())["guides"]


def _save(guides):
    folder = library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    guides = sorted(guides, key=lambda g: (g["title"].lower(), g["sha256"]))
    tmp = folder / (MANIFEST + ".tmp")
    tmp.write_text(json.dumps({"version": 1, "guides": guides}, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(folder / MANIFEST)


def normalise(text):
    """Compare quotes ignoring line wraps, hyphenation at line ends, curly quotes and case."""
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")
    text = re.sub(r"-\s*\n\s*", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


class _HTMLText(html.parser.HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header"}
    BLOCK = {"p", "div", "li", "br", "tr", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3", "h4"):
            self.parts.append("# ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def _pdf_pages(path):
    try:
        import pdfplumber  # suite venv
    except ImportError:
        pdfplumber = None
    if pdfplumber:
        with pdfplumber.open(path) as pdf:
            return [page.extract_text() or "" for page in pdf.pages]
    tool = shutil.which("pdftotext")
    if not tool:
        raise ValueError("Cannot read PDFs: install the suite dependencies (pdfplumber) or poppler's pdftotext")
    out = subprocess.run([tool, "-enc", "UTF-8", str(path), "-"], capture_output=True, check=True).stdout
    pages = out.decode("utf-8", "replace").split("\f")
    return pages[:-1] if pages and not pages[-1].strip() else pages


def read_pages(path):
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pages = _pdf_pages(path)
    elif suffix in (".html", ".htm"):
        parser = _HTMLText()
        parser.feed(path.read_text(errors="replace"))
        pages = ["".join(parser.parts)]
    elif suffix in (".txt", ".md"):
        pages = [path.read_text(errors="replace")]
    else:
        raise ValueError(f"Unsupported guide type {suffix}; use {', '.join(SUFFIXES)}")
    if not any(p.strip() for p in pages):
        raise ValueError(f"{path.name}: no readable text (a scanned PDF needs OCR first)")
    return pages


def _is_heading(line):
    line = line.strip()
    if line.startswith("#"):
        return True
    words = line.split()
    return 0 < len(words) <= 12 and len(line) <= 90 and not line.endswith((".", ",", ";", ":")) \
        and line[0].isupper() and not re.search(r"\$\d|\d{3,}", line)


def passages(page_text, heading=""):
    """Split a page into heading-led paragraphs; carries the last heading across pages."""
    out, body = [], []

    def flush():
        text = re.sub(r"\s+", " ", " ".join(body)).strip()
        if text:
            out.append((heading, text))
        body.clear()

    for block in re.split(r"\n\s*\n", page_text):
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        if len(lines) == 1 and _is_heading(lines[0]):
            flush()
            heading = lines[0].strip().lstrip("#").strip()
            continue
        body.extend(lines)
        if sum(len(b) for b in body) > 1200:
            flush()
    flush()
    return out, heading


def _iso(value, name):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"{name} must be YYYY-MM-DD") from None


def add(file, title=None, url=None, issued=None, applies_from=None, applies_to=None):
    """Maintainer command: copy a guide into the code's ato-library/ and extract its pages
    into library.json. Re-adding the same file updates its details."""
    source = Path(file).expanduser().resolve(strict=True)
    if url and not url.startswith("https://"):
        raise ValueError("url must be the https address the guide came from")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / source.name
    if stored.exists() and hashlib.sha256(stored.read_bytes()).hexdigest() != digest:
        stored = folder / f"{digest[:12]}-{source.name}"
    if not stored.exists():
        shutil.copy2(source, stored)
    pages = read_pages(stored)
    guides = [g for g in load() if g["sha256"] != digest]
    old = next((g for g in load() if g["sha256"] == digest), {})
    guide = {"sha256": digest, "title": title or old.get("title") or source.stem.replace("_", " "),
             "file": stored.name, "url": url or old.get("url"),
             "issued": _iso(issued, "issued") or old.get("issued"),
             "applies_from": _iso(applies_from, "applies_from") or old.get("applies_from"),
             "applies_to": _iso(applies_to, "applies_to") or old.get("applies_to"),
             "added": old.get("added") or date.today().isoformat(), "pages": pages}
    _save(guides + [guide])
    return {"sha256": digest, "title": guide["title"], "pages": len(pages),
            "passages": sum(len(passages(p)[0]) for p in pages), "file": str(stored)}


def sync():
    """Maintainer command: extract every guide file in ato-library/ not yet in library.json."""
    folder = library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    known = {g["sha256"] for g in load()}
    added, failed = [], []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in SUFFIXES or f.name.lower() == "readme.md":
            continue
        if hashlib.sha256(f.read_bytes()).hexdigest() in known:
            continue
        try:
            added.append(add(f))
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            failed.append({"file": f.name, "error": str(exc)})
    return {"library": str(folder), "added": added, "failed": failed, "guides": len(known) + len(added)}


def _index(guides):
    """Build the search index in memory from the bundled text; fast for hundreds of pages."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE VIRTUAL TABLE passages USING fts5(heading, body, sha256 UNINDEXED, page UNINDEXED, "
               "tokenize='porter unicode61')")
    for g in guides:
        heading = ""
        for number, text in enumerate(g["pages"], 1):
            chunks, heading = passages(text, heading)
            db.executemany("INSERT INTO passages VALUES (?,?,?,?)",
                           [(h, body, g["sha256"], number) for h, body in chunks])
    return db


def _warnings(guide, period_end=None):
    out = []
    if guide.get("applies_to") and period_end and period_end > guide["applies_to"]:
        out.append(f"applies only to {guide['applies_to']}; period ends {period_end}")
    if guide.get("applies_from") and period_end and period_end < guide["applies_from"]:
        out.append(f"applies from {guide['applies_from']}; period ends {period_end}")
    dated = guide.get("issued") or guide.get("added")
    if dated and (date.today() - date.fromisoformat(dated)).days > STALE_DAYS:
        out.append(f"dated {dated}, over 12 months old: check the ATO site for a newer version")
    if not guide.get("url"):
        out.append("no ATO source address recorded")
    return out


def _fts_query(terms):
    """Plain words must all match; quoted phrases, OR, AND, NOT and NEAR pass through."""
    if re.search(r'"|\bOR\b|\bNEAR\b|\bAND\b|\bNOT\b', terms):
        return terms
    return " ".join('"' + w + '"' for w in re.findall(r"[\w$.]+", terms))


def search(terms, limit=5, period_end=None):
    if not terms or not terms.strip():
        raise ValueError("Give search terms")
    guides = {g["sha256"]: g for g in load()}
    if not guides:
        return {"results": [], "note": "The ATO library has no guides. Research ato.gov.au instead."}
    query = _fts_query(terms)
    db = _index(guides.values())
    try:
        rows = db.execute(
            f"SELECT sha256,page,heading,snippet(passages,1,'[',']','\u2026',{SNIPPET_TOKENS}) AS snippet "
            "FROM passages WHERE passages MATCH ? ORDER BY bm25(passages,2.0,1.0) LIMIT ?",
            (query, int(limit))).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"Bad search terms: {exc}") from None
    finally:
        db.close()
    results = [{"guide": guides[r["sha256"]]["title"], "sha256": r["sha256"], "page": r["page"],
                "heading": r["heading"], "passage": r["snippet"], "url": guides[r["sha256"]].get("url"),
                "warnings": _warnings(guides[r["sha256"]], period_end)} for r in rows]
    out = {"query": query, "results": results}
    if not results:
        out["note"] = "Nothing in the ATO library. Research ato.gov.au."
    return out


def _guide(sha256):
    if not isinstance(sha256, str) or len(sha256) < 12:
        raise ValueError("Name the guide by its sha256 (at least 12 characters)")
    found = [g for g in load() if g["sha256"].startswith(sha256)]
    if len(found) != 1:
        raise ValueError(f"Guide {sha256} is not in the ATO library")
    return found[0]


def read_page(sha256, page):
    g = _guide(sha256)
    if not 1 <= int(page) <= len(g["pages"]):
        raise ValueError(f"'{g['title']}' has pages 1-{len(g['pages'])}")
    return {"title": g["title"], "url": g.get("url"), "page": int(page), "text": g["pages"][int(page) - 1]}


def guides():
    return {"library": str(library_dir()),
            "guides": [{k: v for k, v in g.items() if k != "pages"} | {"page_count": len(g["pages"]),
                                                                        "warnings": _warnings(g)}
                       for g in load()]}


def verify_quote(citation):
    """A library citation {sha256, page, quote} must quote that page word for word.
    Returns the guide details used to store the citation."""
    if not isinstance(citation, dict):
        raise ValueError("Library source needs sha256, page and quote")
    page, quote = citation.get("page"), citation.get("quote")
    if type(page) is not int:
        raise ValueError("Library source needs the page number")
    if not isinstance(quote, str) or len(normalise(quote)) < 20:
        raise ValueError("Library source needs an exact quote of at least 20 characters")
    g = _guide(citation.get("sha256"))
    if not 1 <= page <= len(g["pages"]):
        raise ValueError(f"'{g['title']}' has no page {page}")
    if normalise(quote) not in normalise(g["pages"][page - 1]):
        raise ValueError(f"Quote not found on page {page} of '{g['title']}': cite the exact wording")
    return {"sha256": g["sha256"], "title": g["title"], "page": page, "url": g.get("url"),
            "quote": quote.strip(), "warnings": _warnings(g)}


def add_commands(sub):
    a = sub.add_parser("ato-add", help="Maintainer: add an ATO guide to the code's library")
    a.add_argument("--file", type=Path, required=True)
    for name in ("title", "url", "issued", "applies-from", "applies-to"):
        a.add_argument(f"--{name}")
    sub.add_parser("ato-sync", help="Maintainer: extract guides dropped into ato-library/")
    s = sub.add_parser("ato-search", help="Search the ATO library")
    s.add_argument("terms")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--period-end")
    p = sub.add_parser("ato-page", help="Read one page of a library guide")
    p.add_argument("--guide", required=True)
    p.add_argument("--page", type=int, required=True)
    sub.add_parser("ato-guides", help="List guides in the ATO library")


LIBRARY_COMMANDS = ("ato-add", "ato-sync", "ato-search", "ato-page", "ato-guides")


def dispatch(args):
    if args.command == "ato-add":
        return add(args.file, args.title, args.url, args.issued, args.applies_from, args.applies_to)
    if args.command == "ato-sync":
        return sync()
    if args.command == "ato-search":
        return search(args.terms, args.limit, args.period_end)
    if args.command == "ato-page":
        return read_page(args.guide, args.page)
    return guides()
