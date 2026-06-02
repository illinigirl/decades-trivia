"""Pre-generated + cached question bank in DynamoDB.

Serving a stored question is a single fast query (no LLM call), which is the
speed win. Items are keyed by slice = "<decade>#<category>" (the requested
slice, so year-scoped variants like '80s#This Week' vs 'tdih#This Week' stay
separate), with sk = a content hash for dedup.
"""
import hashlib
import json
import os
import random
import re

import boto3

_YEAR_RE = re.compile(r"(?<!\d)(1[789]\d\d|20\d\d)(?!\d)")  # 1700s–2099


def _in_range(text: str, rng) -> bool:
    """A banked question is OK for the view if it names no year, or any named
    year falls in range. Drops legacy off-decade questions (e.g. a 1960 fact
    that leaked into an 80s slice before corpus year-scoping)."""
    if not rng:
        return True
    years = {int(y) for y in _YEAR_RE.findall(text)}
    return (not years) or any(rng[0] <= y <= rng[1] for y in years)


def _gives_away(qd: dict) -> bool:
    """True if the correct answer appears in the question text (a giveaway)."""
    try:
        ans = qd["choices"][qd["answer_index"]]
    except (KeyError, IndexError, TypeError):
        return False
    a = re.sub(r"^(the|a|an)\s+", "", ans.strip().lower())
    return len(a) >= 3 and a in qd.get("question", "").lower()

TABLE = os.environ.get("QUESTIONS_TABLE")
_ddb = boto3.resource("dynamodb").Table(TABLE) if TABLE else None


def slice_key(decade: str, category: str) -> str:
    return f"{decade}#{category}"


def shuffle_choices(q: dict) -> dict:
    """Randomize option order so the correct answer isn't position-biased (LLMs
    tend to put it first). Fixes the bank's existing questions at serve time."""
    choices = q.get("choices")
    if not choices:
        return q
    order = list(range(len(choices)))
    random.shuffle(order)
    q["choices"] = [choices[i] for i in order]
    q["answer_index"] = order.index(q.get("answer_index", 0))
    return q


def qid(question: str) -> str:
    """Stable short id from the question text (used for live/topic questions)."""
    return hashlib.sha1(question.strip().lower().encode()).hexdigest()[:12]


def item_key(q: dict) -> str:
    """Bank key for a question, so the same subject/fact can't produce multiple
    near-duplicate questions in a slice. Prefer source fact, then subject tag,
    then question hash."""
    if q.get("source_fact_id"):
        return f"f:{q['source_fact_id']}"
    if q.get("subject"):
        slug = re.sub(r"[^a-z0-9]+", "-", q["subject"].lower()).strip("-")
        return f"s:{slug}" if slug else f"q:{qid(q['question'])}"
    return f"q:{qid(q['question'])}"


def put(decade: str, category: str, q: dict) -> str:
    """Store a question keyed by its source fact (dedups near-duplicates).
    Returns the item key."""
    sk = item_key(q)
    if _ddb is None:               # no table configured (local)
        return sk
    _ddb.put_item(Item={
        "pk": slice_key(decade, category),
        "sk": sk,
        "q": json.dumps({
            "question": q["question"], "choices": q["choices"],
            "answer_index": q["answer_index"], "explanation": q["explanation"],
            "category": q["category"], "source": q["source"], "decade": decade,
        }),
    })
    return sk


def random_question(decade: str, category: str, recent: list | None = None,
                    rng=None) -> dict | None:
    """Return a random stored question for the slice.

    `recent` is the player's recently-seen qids. `rng` is the (lo, hi) year
    bound for the view: banked questions naming only out-of-range years are
    skipped (legacy off-decade questions). Returns None if nothing servable,
    so the caller generates a fresh question instead of repeating.
    """
    if _ddb is None:
        return None
    resp = _ddb.query(
        KeyConditionExpression="pk = :p",
        ExpressionAttributeValues={":p": slice_key(decade, category)},
    )
    items = resp.get("Items", [])
    if not items:
        return None
    seen = set(recent or [])
    pool = []
    for it in items:
        if it["sk"] in seen:
            continue
        qd = json.loads(it["q"])
        if not _in_range(qd.get("question", ""), rng) or _gives_away(qd):
            continue
        pool.append(it)
    if not pool:
        # Nothing new in this slice — return None so the caller generates a
        # fresh question instead of repeating one you've already seen.
        return None
    chosen = random.choice(pool)
    q = json.loads(chosen["q"])
    q["id"] = chosen["sk"]
    return shuffle_choices(q)


def count(decade: str, category: str) -> int:
    if _ddb is None:
        return 0
    resp = _ddb.query(
        Select="COUNT",
        KeyConditionExpression="pk = :p",
        ExpressionAttributeValues={":p": slice_key(decade, category)},
    )
    return resp.get("Count", 0)
