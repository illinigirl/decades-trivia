"""Build the trivia corpus for one or more decades.

For each decade:
  1. Fetch plain-text Wikipedia articles (by category) via the action API.
  2. Chunk into paragraph-sized facts with source metadata.
  3. Embed each chunk with Titan v2 (concurrently).
  4. Write corpus/<decade>.json (chunks) + corpus/<decade>.npy (vectors).

Run from the repo root with the venv:
  ./venv/bin/python ingestion/ingest.py 80s          # one decade
  ./venv/bin/python ingestion/ingest.py all           # everything

Re-run anytime to refresh; output files are overwritten atomically.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from shared import bedrock  # noqa: E402
from sources import (DECADES, TDIH_DATES, TDIH_KEY, TDIH_LABEL,  # noqa: E402
                     TIMELINE_SOURCES, pages_for)

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "corpus")
WIKI_API = "https://en.wikipedia.org/w/api.php"
UA = "DecadesTrivia/1.0 (personal study project; meganschott12@gmail.com)"
FETCH_DELAY = 0.4    # polite spacing between Wikipedia requests (seconds)

MIN_CHUNK = 200      # drop fragments shorter than this
MAX_CHUNK = 1100     # split paragraphs longer than this
MAX_CHUNKS_PER_PAGE = 60
EMBED_WORKERS = 4


def fetch_plaintext(title: str) -> str | None:
    """Full plain-text extract of an article, or None if it doesn't exist."""
    params = {
        "action": "query", "format": "json", "prop": "extracts",
        "explaintext": "1", "redirects": "1", "titles": title,
    }
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    # Polite pacing + exponential backoff on rate limits (HTTP 429).
    for attempt in range(5):
        time.sleep(FETCH_DELAY)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                wait = 2 ** attempt
                print(f"    429 rate-limited; backing off {wait}s")
                time.sleep(wait)
                continue
            raise
    pages = data.get("query", {}).get("pages", {})
    for pid, page in pages.items():
        if pid == "-1" or "missing" in page:
            return None
        return page.get("extract") or None
    return None


def chunk_text(text: str, cap: int = MAX_CHUNKS_PER_PAGE) -> list[str]:
    """Split plain text into fact-sized chunks, skipping section headers."""
    chunks: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        # explaintext renders headings as "== Heading =="; skip them + stubs.
        if not para or para.startswith("==") or len(para) < MIN_CHUNK:
            continue
        while len(para) > MAX_CHUNK:
            cut = para.rfind(". ", 0, MAX_CHUNK)
            cut = cut + 1 if cut > MIN_CHUNK else MAX_CHUNK
            chunks.append(para[:cut].strip())
            para = para[cut:].strip()
        if len(para) >= MIN_CHUNK:
            chunks.append(para)
    return chunks[:cap]


def title_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


# "1981 – ...", "1981: ...", "c. 1962 — ..." — a year-prefixed timeline entry.
_TIMELINE_LINE = re.compile(r"^(?:c\.?\s*)?(\d{4})\s*[–—:\-]\s+(.+)$")
_timeline_cache: dict[str, str | None] = {}


def _fetch_timeline(title: str) -> str | None:
    """Fetch a timeline page once and reuse it across decades."""
    if title not in _timeline_cache:
        _timeline_cache[title] = fetch_plaintext(title)
    return _timeline_cache[title]


def build_decade(decade: str) -> None:
    print(f"\n=== Building corpus for {decade} ({DECADES[decade]}s) ===")
    chunks: list[dict] = []
    for category, title, cap in pages_for(decade):
        text = fetch_plaintext(title)
        if not text:
            print(f"  skip (missing): {title}")
            continue
        # Year-titled pages ("1986 in science", "1986") list facts under the
        # year heading, so the line itself often omits the year. Prefix it so
        # each fact is self-dating (and add a year field). Skip "1980s"-style.
        ym = re.match(r"(\d{4})(?![\ds])", title)
        page_year = int(ym.group(1)) if ym else None
        page_chunks = chunk_text(text, cap or MAX_CHUNKS_PER_PAGE)
        for j, body in enumerate(page_chunks):
            chunk = {
                "id": f"{decade}-{len(chunks)}",
                "decade": decade,
                "category": category,
                "title": title,
                "url": title_url(title),
                "text": f"{page_year}: {body}" if page_year else body,
            }
            if page_year:
                chunk["year"] = page_year
            chunks.append(chunk)
        print(f"  {title:38s} [{category:16s}] -> {len(page_chunks)} chunks")

    # Year-indexed timeline pages -> dedicated Inventions / Medicine categories,
    # keeping only the lines whose year falls inside this decade.
    start = DECADES[decade]
    for category, title in TIMELINE_SOURCES:
        text = _fetch_timeline(title)
        if not text:
            print(f"  skip (missing): {title}")
            continue
        added = 0
        for raw in text.split("\n"):
            m = _TIMELINE_LINE.match(raw.strip())
            if not m:
                continue
            year, body = int(m.group(1)), m.group(2).strip()
            if not (start <= year <= start + 9) or len(body) < 40:
                continue
            chunks.append({
                "id": f"{decade}-{len(chunks)}",
                "decade": decade,
                "category": category,
                "title": title,
                "url": title_url(title),
                "text": f"{year}: {body}",
                "year": year,
            })
            added += 1
        print(f"  {title:38s} [{category:16s}] -> {added} chunks")

    print(f"  embedding {len(chunks)} chunks with Titan...")
    with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as pool:
        vectors = list(pool.map(lambda c: bedrock.embed(c["text"]), chunks))
    arr = np.asarray(vectors, dtype="float32")

    os.makedirs(CORPUS_DIR, exist_ok=True)
    base = os.path.join(CORPUS_DIR, decade)
    with open(base + ".json", "w") as f:
        json.dump(chunks, f, ensure_ascii=False)
    # Raw little-endian float32, row-major [N, 1024]. Readable with numpy
    # (np.frombuffer) AND pure Python (array('f', ...)) — so Lambda needs no
    # numpy layer. Shape is implied: len(chunks) x 1024.
    with open(base + ".f32", "wb") as f:
        f.write(arr.astype("<f4").tobytes())
    cats = sorted({c["category"] for c in chunks})
    print(f"  wrote {len(chunks)} chunks ({arr.shape}) across: {', '.join(cats)}")


_TDIH_SECTIONS = {"Events": "", "Births": "Born", "Deaths": "Died"}
_TDIH_LINE = re.compile(r"^(\d{3,4})\s*[–—-]\s*(.+)$")


def _parse_date_page(date: str, text: str, chunks: list[dict]) -> None:
    """Parse one date page's events/births/deaths into year-prefixed facts."""
    section = None
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("=="):
            name = line.strip("= ").strip()
            level = (len(line) - len(line.lstrip("=")))  # 2 == top section
            if name in _TDIH_SECTIONS:
                section = name              # entering Events/Births/Deaths
            elif level <= 2:
                section = None             # a different top section (See also, etc.)
            # level >= 3 (e.g. "=== 1901–present ===") keeps the current section
            continue
        if not section:
            continue
        m = _TDIH_LINE.match(line)
        if not m:
            continue
        year, body = m.group(1), m.group(2).strip()
        prefix = _TDIH_SECTIONS[section]
        fact = f"{date}, {year}: {prefix + ' — ' if prefix else ''}{body}"
        chunks.append({
            "id": f"tdih-{len(chunks)}",
            "decade": TDIH_KEY,
            "category": TDIH_LABEL,
            "title": f"{date} (Wikipedia)",
            "url": title_url(date),
            "text": fact,
            "year": int(year),
        })


def build_tdih() -> None:
    """Build the 'This Week in History' corpus from the week's date pages.

    Date pages are year-prefixed one-liners that the paragraph chunker would
    drop, so we parse each line into its own fact: '<date>, <year>: <event>'.
    Stored decade-agnostic under TDIH_KEY; surfaced as a category in every mode.
    """
    print(f"\n=== Building '{TDIH_LABEL}' for {TDIH_DATES[0]}–{TDIH_DATES[-1]} ===")
    chunks: list[dict] = []
    for date in TDIH_DATES:
        text = fetch_plaintext(date)
        if not text:
            print(f"  could not fetch '{date}'"); continue
        before = len(chunks)
        _parse_date_page(date, text, chunks)
        print(f"  {date:10s} -> {len(chunks) - before} facts")
    print(f"  parsed {len(chunks)} dated facts total; embedding...")
    with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as pool:
        vectors = list(pool.map(lambda c: bedrock.embed(c["text"]), chunks))
    arr = np.asarray(vectors, dtype="float32")
    os.makedirs(CORPUS_DIR, exist_ok=True)
    base = os.path.join(CORPUS_DIR, TDIH_KEY)
    with open(base + ".json", "w") as f:
        json.dump(chunks, f, ensure_ascii=False)
    with open(base + ".f32", "wb") as f:
        f.write(arr.astype("<f4").tobytes())
    print(f"  wrote {len(chunks)} '{TDIH_LABEL}' facts")


def main() -> None:
    targets = sys.argv[1:] or ["80s"]
    if targets == ["all"]:
        targets = list(DECADES) + [TDIH_KEY]
    for decade in targets:
        if decade == TDIH_KEY:
            build_tdih()
        elif decade in DECADES:
            build_decade(decade)
        else:
            print(f"unknown target '{decade}'; choices: {', '.join(DECADES)} | tdih | all")
    print("\nDone.")


if __name__ == "__main__":
    main()
