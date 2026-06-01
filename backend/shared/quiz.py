"""Quiz + fact-review generation, grounded in the retrieved corpus.

The grounding contract: every question's correct answer must be verifiable
from the source facts we hand the model. We pass real Wikipedia chunks and
return the citation alongside, so nothing is hallucinated.
"""
import json

from . import retrieval
from . import bedrock

DECADE_LABEL = {"60s": "1960s", "70s": "1970s", "80s": "1980s",
                "90s": "1990s", "00s": "2000s", "all": "1960s–2000s",
                "tdih": "this week in history (June 14–20, any year)"}

QUIZ_SYSTEM = (
    "You are a trivia question writer for a decades study app. You write "
    "factually accurate multiple-choice questions grounded ONLY in the source "
    "facts provided. The correct answer must be directly verifiable from the "
    "facts. Distractors must be plausible but clearly wrong. Never invent "
    "details not present in the sources."
)


def make_question(decade: str, *, category: str | None = None,
                  topic: str | None = None, difficulty: str = "medium") -> dict:
    """Generate one grounded multiple-choice question.

    topic    -> semantic search for relevant facts (focused study)
    no topic -> random sample for variety (general quiz)
    """
    if topic:
        facts = retrieval.search(decade, topic, k=5, category=category)
    else:
        facts = retrieval.sample(decade, n=5, category=category)
    if not facts:
        raise ValueError(f"no facts for decade={decade} category={category}")

    by_id = {f["id"]: f for f in facts}
    fact_block = "\n\n".join(f"[{f['id']}] ({f['category']}) {f['text']}"
                             for f in facts)

    prompt = f"""Source facts about the {DECADE_LABEL.get(decade, decade)}:

{fact_block}

Write ONE {difficulty}-difficulty multiple-choice trivia question based on the
most interesting, specific fact above. Requirements:
- 4 options; exactly one correct and verifiable from the facts.
- The other 3 are plausible but wrong.
- Vary which option is correct (don't always pick A).
- Include a one-sentence explanation of the answer.
- Set source_id to the [id] of the fact the question is based on.

Return ONLY JSON:
{{"question": "...", "choices": ["...","...","...","..."],
  "answer_index": 0, "explanation": "...", "source_id": "{facts[0]['id']}"}}"""

    q = bedrock.generate_json(prompt, system=QUIZ_SYSTEM, temperature=0.8,
                              max_tokens=600)
    src = by_id.get(q.get("source_id"), facts[0])
    q["category"] = src["category"]
    q["source"] = {"title": src["title"], "url": src["url"]}
    q["decade"] = decade
    return q


def review_facts(decade: str, *, topic: str | None = None,
                 category: str | None = None, n: int = 6) -> list[dict]:
    """Return facts to study (with citations), optionally focused by topic."""
    if topic:
        chunks = retrieval.search(decade, topic, k=n, category=category)
    else:
        chunks = retrieval.sample(decade, n=n, category=category)
    return [{"text": c["text"], "category": c["category"],
             "source": {"title": c["title"], "url": c["url"]}} for c in chunks]
