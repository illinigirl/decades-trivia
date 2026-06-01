"""Sync corpus files from S3 to the Lambda's /tmp on demand.

No-op locally (when CORPUS_BUCKET is unset) since the files are already on disk.
Downloaded files persist across warm invocations, so this runs once per decade
per cold container.
"""
import os

import boto3

from . import retrieval

BUCKET = os.environ.get("CORPUS_BUCKET")
PREFIX = os.environ.get("CORPUS_PREFIX", "corpus/")

_s3 = boto3.client("s3") if BUCKET else None
_synced: set[str] = set()


def _fetch(key: str) -> None:
    if not BUCKET or key in _synced:
        return
    os.makedirs(retrieval.CORPUS_DIR, exist_ok=True)
    for ext in (".json", ".f32"):
        _s3.download_file(BUCKET, f"{PREFIX}{key}{ext}",
                          os.path.join(retrieval.CORPUS_DIR, f"{key}{ext}"))
    _synced.add(key)


def ensure(decade: str) -> None:
    """Make sure the corpus files needed for `decade` are on local disk.
    'all' pulls every ingested decade; every view also needs This-Day-in-History."""
    if not BUCKET:
        return
    targets = available() if decade == retrieval.ALL_KEY else [decade]
    for t in targets:
        _fetch(t)
    _fetch(retrieval.TDIH_KEY)


def available() -> list[str]:
    """Decades that have an ingested corpus (ordered oldest->newest)."""
    order = list(retrieval.DECADE_LABEL)   # excludes tdih/all by construction
    if BUCKET:
        resp = _s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX)
        found = {os.path.basename(o["Key"])[:-4]
                 for o in resp.get("Contents", []) if o["Key"].endswith(".f32")}
    else:
        found = {f[:-4] for f in os.listdir(retrieval.CORPUS_DIR)
                 if f.endswith(".f32")} if os.path.isdir(retrieval.CORPUS_DIR) else set()
    return [d for d in order if d in found]
