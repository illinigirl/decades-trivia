"""Seed the question bank: pre-generate vetted questions per decade x category.

Each question goes through the same pub-style generation + fact-check pipeline
as live serving, then is stored (deduped by content hash) in DynamoDB. The app
serves these instantly and also caches newly generated ones, so this is just a
head start — re-run anytime to top up (slices already at target are skipped).

Run from repo root with the venv + AWS creds:
  AWS_PROFILE=watchtower AWS_REGION=us-east-2 ./venv/bin/python ingestion/gen_bank.py
  ... ingestion/gen_bank.py 80s tdih        # only some decades
  ... N=10 ingestion/gen_bank.py            # smaller target per slice
"""
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

STACK = os.environ.get("STACK", "decades-trivia")
REGION = os.environ.get("AWS_REGION", "us-east-2")
MAINSTREAM = int(os.environ.get("N", "25"))
NICHE_N = int(os.environ.get("NICHE_N", "15"))
NICHE = {"Rowing", "This Week in History", "Medicine", "Film", "Video Games"}
WORKERS = 5

# Resolve the table name from the stack and expose it before importing bank.
_cf = boto3.client("cloudformation", region_name=REGION)
_outs = _cf.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
os.environ["QUESTIONS_TABLE"] = next(
    o["OutputValue"] for o in _outs if o["OutputKey"] == "QuestionsTable")
os.environ.setdefault("AWS_REGION", REGION)

from shared import bank, quiz, retrieval  # noqa: E402
from sources import DECADES, TDIH_KEY  # noqa: E402


def seed_slice(decade: str, category: str) -> None:
    target = NICHE_N if category in NICHE else MAINSTREAM
    have = bank.count(decade, category)
    if have >= target:
        print(f"  {decade:4s} {category:20s} already has {have} (skip)")
        return
    need = target - have
    attempts = math.ceil(need * 1.6)   # over-generate to survive dedup

    def gen(_):
        try:
            return quiz.make_question(decade, category=category)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(gen, range(attempts)))

    added, seen = 0, set()
    for q in results:
        if not q:
            continue
        qid = bank.qid(q["question"])
        if qid in seen:
            continue
        seen.add(qid)
        bank.put(decade, category, q)
        added += 1
        if added >= need:
            break
    print(f"  {decade:4s} {category:20s} +{added} (now ~{have + added}/{target})")


def main() -> None:
    targets = sys.argv[1:] or (list(DECADES) + [TDIH_KEY])
    for decade in targets:
        cats = retrieval.categories(decade)
        print(f"\n=== {decade} ({len(cats)} categories) ===")
        for category in cats:
            seed_slice(decade, category)
    print("\nDone.")


if __name__ == "__main__":
    main()
