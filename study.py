"""Local terminal study tool — quiz yourself and review facts offline.

Uses the same grounded-generation logic as the AWS app, so it's a faithful
preview. Stats persist to study_stats.json and bias future questions toward
weak categories.

Run from repo root:
  AWS_PROFILE=watchtower ./venv/bin/python study.py            # 80s
  AWS_PROFILE=watchtower ./venv/bin/python study.py 90s
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from shared import quiz, retrieval  # noqa: E402

STATS_FILE = os.path.join(os.path.dirname(__file__), "study_stats.json")
LETTERS = "ABCD"


def load_stats() -> dict:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE) as f:
            return json.load(f)
    return {}


def save_stats(stats: dict) -> None:
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def weak_category(stats: dict, decade: str, cats: list[str]) -> str | None:
    """Pick a category to focus on: prefer unseen, then lowest accuracy."""
    d = stats.get(decade, {})
    scored = []
    for c in cats:
        s = d.get(c, {"hit": 0, "miss": 0})
        total = s["hit"] + s["miss"]
        acc = s["hit"] / total if total else -1   # unseen sorts first
        scored.append((acc, total, c))
    scored.sort()
    # 70% of the time drill the weakest; otherwise keep it varied.
    return scored[0][2] if random.random() < 0.7 else None


def record(stats: dict, decade: str, category: str, hit: bool) -> None:
    d = stats.setdefault(decade, {})
    s = d.setdefault(category, {"hit": 0, "miss": 0})
    s["hit" if hit else "miss"] += 1


def print_stats(stats: dict, decade: str) -> None:
    d = stats.get(decade, {})
    if not d:
        print("No stats yet — go take some questions!")
        return
    print(f"\n  Your {decade} stats:")
    th = tm = 0
    for cat in sorted(d):
        s = d[cat]
        tot = s["hit"] + s["miss"]
        th += s["hit"]; tm += s["miss"]
        pct = round(100 * s["hit"] / tot) if tot else 0
        print(f"    {cat:18s} {s['hit']:3d}/{tot:<3d}  {pct:3d}%")
    tot = th + tm
    print(f"    {'OVERALL':18s} {th:3d}/{tot:<3d}  "
          f"{round(100*th/tot) if tot else 0:3d}%\n")


def run_quiz(decade: str, stats: dict) -> None:
    cats = retrieval.categories(decade)
    print("\nQuiz mode — type the letter of your answer, or 'q' to stop.\n")
    while True:
        cat = weak_category(stats, decade, cats)
        try:
            q = quiz.make_question(decade, category=cat)
        except Exception as e:
            print(f"  (skipping a question: {e})")
            continue
        print(f"[{q['category']}]  {q['question']}")
        for i, choice in enumerate(q["choices"]):
            print(f"   {LETTERS[i]}. {choice}")
        ans = input("> ").strip().upper()
        if ans == "Q":
            break
        correct = LETTERS[q["answer_index"]]
        hit = ans == correct
        record(stats, decade, q["category"], hit)
        save_stats(stats)
        if hit:
            print("   ✅ Correct!")
        else:
            print(f"   ❌ Answer: {correct}. {q['choices'][q['answer_index']]}")
        print(f"   {q['explanation']}")
        print(f"   ↪ {q['source']['title']}\n")


def run_review(decade: str) -> None:
    topic = input("\nReview — topic to focus on (blank = random facts): ").strip()
    facts = quiz.review_facts(decade, topic=topic or None, n=6)
    print()
    for f in facts:
        print(f"[{f['category']}] {f['text']}")
        print(f"   ↪ {f['source']['title']}\n")


def main() -> None:
    decade = sys.argv[1] if len(sys.argv) > 1 else "80s"
    stats = load_stats()
    print(f"\n=== Decades Trivia — studying the {quiz.DECADE_LABEL.get(decade, decade)} ===")
    while True:
        choice = input("\n(q)uiz  (r)eview facts  (s)tats  (x)quit > ").strip().lower()
        if choice == "q":
            run_quiz(decade, stats)
        elif choice == "r":
            run_review(decade)
        elif choice == "s":
            print_stats(stats, decade)
        elif choice in ("x", "quit", "exit"):
            break
    print("Good luck on the 19th! 🎉")


if __name__ == "__main__":
    main()
