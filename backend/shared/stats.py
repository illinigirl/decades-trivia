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


def weak_category(user: str, decade: str, cats: list[str]) -> str | None:
    """Pick a focus category: prefer unseen, then lowest accuracy. 70% of the
    time drill the weakest; otherwise return None for variety."""
    d = get(user, decade)
    scored = []
    for c in cats:
        s = d.get(c, {"hit": 0, "miss": 0})
        total = s["hit"] + s["miss"]
        acc = s["hit"] / total if total else -1.0   # unseen sorts first
        scored.append((acc, total, c))
    scored.sort()
    return scored[0][2] if random.random() < 0.7 else None
