"""Corpus loading + vector search (numpy-optional, so Lambda needs no layer).

A corpus is two aligned files per decade, written by the ingestion script:
  <decade>.json  -> list of chunk dicts {id, decade, category, title, url, text}
  <decade>.f32   -> raw little-endian float32, row-major [N, 1024] Titan vectors

Uses numpy when available (local CLI / ingestion) for fast search; falls back
to pure-Python cosine in Lambda. Loads lazily and caches per-decade.
"""
import json
import math
import os
import random
import re
import struct

try:
    import numpy as np
except ImportError:  # Lambda without a numpy layer
    np = None

DIM = 1024
DECADE_LABEL = {"60s": "1960s", "70s": "1970s", "80s": "1980s",
                "90s": "1990s", "00s": "2000s"}
DECADE_START = {"60s": 1960, "70s": 1970, "80s": 1980,
                "90s": 1990, "00s": 2000}
TDIH_KEY = "tdih"          # cross-cutting "This Week in History" corpus
ALL_KEY = "all"            # virtual decade spanning every ingested decade

# Local default; Lambda overrides via env to a /tmp path it syncs from S3.
CORPUS_DIR = os.environ.get("CORPUS_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "corpus"))

_base_cache: dict = {}     # single corpus file -> (chunks, vecs)
_cache: dict = {}          # composed view (decade / all) -> (chunks, vecs)


def _present_decades() -> list[str]:
    """Ingested decade corpora actually on disk (oldest -> newest)."""
    if not os.path.isdir(CORPUS_DIR):
        return []
    have = {f[:-4] for f in os.listdir(CORPUS_DIR) if f.endswith(".f32")}
    return [d for d in DECADE_LABEL if d in have]


def _tdih_present() -> bool:
    return os.path.exists(os.path.join(CORPUS_DIR, TDIH_KEY + ".f32"))


def _load_base(key: str):
    """Load one corpus file -> (chunks, L2-normalized vectors)."""
    if key in _base_cache:
        return _base_cache[key]
    base = os.path.join(CORPUS_DIR, key)
    with open(base + ".json") as f:
        chunks = json.load(f)
    with open(base + ".f32", "rb") as f:
        buf = f.read()
    n = len(chunks)
    if np is not None:
        vecs = np.frombuffer(buf, dtype="<f4").reshape(n, DIM).astype("float32")
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
    else:
        flat = struct.unpack(f"<{n * DIM}f", buf)
        vecs = []
        for i in range(n):
            row = flat[i * DIM:(i + 1) * DIM]
            norm = math.sqrt(sum(x * x for x in row)) or 1.0
            vecs.append([x / norm for x in row])
    _base_cache[key] = (chunks, vecs)
    return _base_cache[key]


def year_range(decade: str):
    """Year bounds for a view (used to scope facts AND banked questions):
      a specific decade -> just that decade's years (decade-aligned questions)
      'all'             -> the span of all decades (1960–2009)
      'tdih' mode       -> None (no filter: every year, incl. Juneteenth 1865)"""
    if decade == ALL_KEY:
        return (min(DECADE_START.values()), max(DECADE_START.values()) + 9)
    if decade in DECADE_START:
        s = DECADE_START[decade]
        return (s, s + 9)
    return None


def _filter_pred(chunks, vecs, pred):
    """Keep chunks where pred(chunk) is True, dropping aligned vector rows."""
    idx = [i for i, c in enumerate(chunks) if pred(c)]
    fc = [chunks[i] for i in idx]
    if np is not None:
        fv = vecs[idx] if idx else np.empty((0, DIM), dtype="float32")
    else:
        fv = [vecs[i] for i in idx]
    return fc, fv


def _filter_by_year(chunks, vecs, lo: int, hi: int):
    return _filter_pred(chunks, vecs, lambda c: lo <= c.get("year", -1) <= hi)


_YEAR_RE = re.compile(r"(?<!\d)(1[789]\d\d|20\d\d)(?!\d)")  # 1700s–2099


def _chunk_in_range(chunk: dict, lo: int, hi: int) -> bool:
    """Year-scope a chunk to a decade so off-era facts don't leak into a quiz
    (e.g. The Flintstones (1960) mentioned on the '1980s in television' page).

    Keep if: it has a year field in range, OR (no year field) it names no year,
    OR it names at least one year inside the decade. Drop only chunks whose
    every named year is outside the decade."""
    if "year" in chunk:
        return lo <= chunk["year"] <= hi
    years = {int(y) for y in _YEAR_RE.findall(chunk["text"])}
    return (not years) or any(lo <= y <= hi for y in years)


def _load(decade: str):
    """Return composed (chunks, vectors). 'all' spans every ingested decade;
    every view folds in This-Week-in-History, year-scoped to the view's decade
    (so an 80s quiz gets 1980s on-this-week facts, not all of history)."""
    if decade in _cache:
        return _cache[decade]

    if decade == TDIH_KEY:
        base_keys: list = []                 # tdih is the sole source below
    elif decade == ALL_KEY:
        base_keys = _present_decades()
    else:
        base_keys = [decade]

    rng = year_range(decade)                 # decade/all -> range; tdih mode -> None

    # Decade bases, with Rowing prose year-scoped to the view's decade.
    base_chunks: list = []
    base_parts: list = []
    for key in base_keys:
        chunks, vecs = _load_base(key)
        base_chunks.extend(chunks)
        base_parts.append(vecs)
    if np is not None:
        base_vecs = np.vstack(base_parts) if base_parts else np.empty((0, DIM))
    else:
        base_vecs = [row for part in base_parts for row in part]
    if rng:
        base_chunks, base_vecs = _filter_pred(
            base_chunks, base_vecs, lambda c: _chunk_in_range(c, *rng))

    segments = [(base_chunks, base_vecs)]

    if _tdih_present():                       # This-Week, year-scoped to the view
        tc, tv = _load_base(TDIH_KEY)
        if rng:
            tc, tv = _filter_by_year(tc, tv, *rng)
        segments.append((tc, tv))

    all_chunks = [c for chunks, _ in segments for c in chunks]
    if np is not None:
        vectors = np.vstack([v for _, v in segments])
    else:
        vectors = [row for _, v in segments for row in v]
    _cache[decade] = (all_chunks, vectors)
    return _cache[decade]


def categories(decade: str) -> list[str]:
    chunks, _ = _load(decade)
    return sorted({c["category"] for c in chunks})


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def search(decade: str, query: str, *, k: int = 6,
           category: str | None = None) -> list[dict]:
    """Semantic search: return top-k chunks most relevant to `query`."""
    from . import bedrock
    chunks, vecs = _load(decade)
    q = bedrock.embed(query)

    if np is not None:
        qv = np.asarray(_normalize(q), dtype="float32")
        scores = vecs @ qv
        order = sorted(range(len(chunks)), key=lambda i: -scores[i])
    else:
        qv = _normalize(q)
        scores = [sum(a * b for a, b in zip(vecs[i], qv)) for i in range(len(chunks))]
        order = sorted(range(len(chunks)), key=lambda i: -scores[i])

    out = []
    for i in order:
        if category and chunks[i]["category"] != category:
            continue
        out.append({**chunks[i], "score": float(scores[i])})
        if len(out) >= k:
            break
    return out


def sample(decade: str, *, n: int = 4, category: str | None = None,
           rng: random.Random | None = None) -> list[dict]:
    """Random chunks from the corpus — drives variety in general quizzes."""
    chunks, _ = _load(decade)
    pool = [c for c in chunks if not category or c["category"] == category]
    rng = rng or random
    return rng.sample(pool, min(n, len(pool)))
