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

import boto3

TABLE = os.environ.get("QUESTIONS_TABLE")
_ddb = boto3.resource("dynamodb").Table(TABLE) if TABLE else None


def slice_key(decade: str, category: str) -> str:
    return f"{decade}#{category}"


def qid(question: str) -> str:
    """Stable short id from the question text (dedup + client 'seen' tracking)."""
    return hashlib.sha1(question.strip().lower().encode()).hexdigest()[:12]


def put(decade: str, category: str, q: dict) -> str:
    """Store a question in its slice (idempotent on qid). Returns the qid."""
    qq = qid(q["question"])
    if _ddb is None:               # no table configured (local) -> just hash
        return qq
    _ddb.put_item(Item={
        "pk": slice_key(decade, category),
        "sk": qq,
        "q": json.dumps({
            "question": q["question"], "choices": q["choices"],
            "answer_index": q["answer_index"], "explanation": q["explanation"],
            "category": q["category"], "source": q["source"], "decade": decade,
        }),
    })
    return qq


def random_question(decade: str, category: str, exclude: set | None = None) -> dict | None:
    """Return a random stored question for the slice, avoiding `exclude` qids."""
    if _ddb is None:
        return None
    resp = _ddb.query(
        KeyConditionExpression="pk = :p",
        ExpressionAttributeValues={":p": slice_key(decade, category)},
    )
    items = resp.get("Items", [])
    exclude = exclude or set()
    pool = [it for it in items if it["sk"] not in exclude] or items
    if not pool:
        return None
    chosen = random.choice(pool)
    q = json.loads(chosen["q"])
    q["id"] = chosen["sk"]
    return q


def count(decade: str, category: str) -> int:
    if _ddb is None:
        return 0
    resp = _ddb.query(
        Select="COUNT",
        KeyConditionExpression="pk = :p",
        ExpressionAttributeValues={":p": slice_key(decade, category)},
    )
    return resp.get("Count", 0)
