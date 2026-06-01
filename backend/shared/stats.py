"""Per-user hit/miss tracking in DynamoDB.

Table schema (single table):
  pk = user id            (anonymous browser uuid for now; Cognito sub later)
  sk = "<decade>#<category>"
  hit, miss = counters

Mirrors the local study.py logic so the AWS app behaves identically.
"""
import os
import random

import boto3

TABLE = os.environ.get("STATS_TABLE")
_ddb = boto3.resource("dynamodb").Table(TABLE) if TABLE else None


def record(user: str, decade: str, category: str, correct: bool) -> None:
    _ddb.update_item(
        Key={"pk": user, "sk": f"{decade}#{category}"},
        UpdateExpression="ADD #f :one",
        ExpressionAttributeNames={"#f": "hit" if correct else "miss"},
        ExpressionAttributeValues={":one": 1},
    )


def get(user: str, decade: str) -> dict:
    """Return {category: {"hit": n, "miss": n}} for a user+decade."""
    resp = _ddb.query(
        KeyConditionExpression="pk = :u AND begins_with(sk, :d)",
        ExpressionAttributeValues={":u": user, ":d": f"{decade}#"},
    )
    out: dict[str, dict] = {}
    for item in resp.get("Items", []):
        cat = item["sk"].split("#", 1)[1]
        out[cat] = {"hit": int(item.get("hit", 0)),
                    "miss": int(item.get("miss", 0))}
    return out


def recent_served(user: str, decade: str) -> list[str]:
    """Recently-served question ids for a user+decade (oldest -> newest).
    Strongly consistent so a just-served question is always seen, preventing
    near-repeats under rapid clicking."""
    if _ddb is None:
        return []
    item = _ddb.get_item(Key={"pk": user, "sk": f"served#{decade}"},
                         ConsistentRead=True).get("Item")
    return list(item.get("ids", [])) if item else []


def record_served(user: str, decade: str, qid: str, cap: int = 50) -> None:
    """Append a served question id, keeping the last `cap`. Server-side dedup
    so repeats are prevented even if the client doesn't send its seen list."""
    if _ddb is None or not qid:
        return
    ids = [i for i in recent_served(user, decade) if i != qid] + [qid]
    _ddb.put_item(Item={"pk": user, "sk": f"served#{decade}", "ids": ids[-cap:]})


def weak_category(user: str, decade: str, cats: list[str]) -> str | None:
    """Pick a focus category with a lean toward weak areas but plenty of spread,
    so the quiz doesn't lock onto one category. Half the time pick randomly among
    the few weakest (unseen/lowest accuracy); otherwise None (caller goes random)."""
    d = get(user, decade)
    scored = []
    for c in cats:
        s = d.get(c, {"hit": 0, "miss": 0})
        total = s["hit"] + s["miss"]
        acc = s["hit"] / total if total else -1.0   # unseen sorts first
        scored.append((acc, total, c))
    scored.sort()
    if random.random() < 0.5:
        weakest = [c for _, _, c in scored[:3]]      # spread across the 3 weakest
        return random.choice(weakest)
    return None
