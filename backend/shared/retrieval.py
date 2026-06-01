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
import struct

try:
    import numpy as np
except ImportError:  # Lambda without a numpy layer
    np = None

DIM = 1024
DECADE_LABEL = {"60s": "1960s", "70s": "1970s", "80s": "1980s",
                "90s": "1990s", "00s": "2000s"}

# Local default; Lambda overrides via env to a /tmp path it syncs from S3.
CORPUS_DIR = os.environ.get("CORPUS_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "corpus"))

_cache: dict = {}


def _load(decade: str):
    """Return (chunks, vectors). vectors is an ndarray (numpy) or list[list]
    of L2-normalized rows (pure Python)."""
    if decade in _cache:
        return _cache[decade]
    base = os.path.join(CORPUS_DIR, decade)
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
    _cache[decade] = (chunks, vecs)
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
