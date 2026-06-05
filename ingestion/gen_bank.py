"""Seed the question bank from Claude's knowledge of each decade.

Every question is verified by independent-solve consensus (Opus + Haiku both
answer it blind; kept only if both pick the marked answer) — so the bank holds
trustworthy questions, not hallucinations. Deduped by subject for breadth, with
an accumulating "avoid" list pushing coverage across many subjects.

Run from repo root with venv + AWS creds:
  AWS_PROFILE=watchtower AWS_REGION=us-east-2 ./venv/bin/python ingestion/gen_bank.py
  ... ingestion/gen_bank.py 80s tdih          # only some views
  ... N=40 NICHE_N=25 ingestion/gen_bank.py   # bigger bank
Re-run anytime to top up (slices already at target are skipped).
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

STACK = os.environ.get("STACK", "decades-trivia")
REGION = os.environ.get("AWS_REGION", "us-east-2")
MAINSTREAM = int(os.environ.get("N", "45"))
NICHE_N = int(os.environ.get("NICHE_N", "30"))
# This Week in History: per-decade June 14–20 events are genuinely scarce, so
# keep that target small (the early-exit below stops once it runs dry). The
# standalone "any year" mode has lots of history to draw on.
TWIH_DECADE_N = int(os.environ.get("TWIH_N", "15"))
TWIH_ANY_N = int(os.environ.get("TDIH_ANY_N", "45"))
WORKERS = 3   # account Bedrock throughput is limited; fewer workers = fewer throttle spikes
VIEWS = ["60s", "70s", "80s", "90s", "00s", "all", "tdih"]


def target_for(decade: str, category: str) -> int:
    if decade == "tdih":
        return TWIH_ANY_N
    if category == "This Week in History":
        return TWIH_DECADE_N
    if category in quiz.NICHE_CATEGORIES:
        return NICHE_N
    return MAINSTREAM

_cf = boto3.client("cloudformation", region_name=REGION)
_outs = _cf.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
os.environ["QUESTIONS_TABLE"] = next(
    o["OutputValue"] for o in _outs if o["OutputKey"] == "QuestionsTable")
os.environ.setdefault("AWS_REGION", REGION)

from shared import bank, quiz  # noqa: E402


def seed_slice(decade: str, category: str) -> None:
    target = target_for(decade, category)
    have = bank.count(decade, category)
    if have >= target:
        print(f"  {decade:4s} {category:20s} has {have} (skip)")
        return
    need = target - have
    added, dry, avoid, seen = 0, 0, [], set()

    # Stop when we hit the target OR after 2 consecutive rounds that add nothing
    # new (the subject pool is exhausted) — prevents stalling on unreachable
    # targets like per-decade This Week.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while added < need and dry < 2:
            batch = list(pool.map(
                lambda _: quiz.make_knowledge_question(
                    decade, category=category, avoid=avoid),
                range(WORKERS)))
            new_this_round = 0
            for q in batch:
                if not q:
                    continue
                key = bank.item_key(q)
                if key in seen:
                    continue
                seen.add(key)
                avoid.append(q.get("subject", ""))
                bank.put(decade, category, q)
                added += 1
                new_this_round += 1
                if added >= need:
                    break
            dry = dry + 1 if new_this_round == 0 else 0
    print(f"  {decade:4s} {category:20s} +{added} (now ~{have + added}/{target})")


def main() -> None:
    targets = sys.argv[1:] or VIEWS
    for decade in targets:
        cats = quiz.categories_for(decade)
        print(f"\n=== {decade} ({len(cats)} categories) ===")
        for category in cats:
            seed_slice(decade, category)
    print("\nDone.")


if __name__ == "__main__":
    main()
