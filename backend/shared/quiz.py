"""Quiz + fact-review generation, grounded in the retrieved corpus.

The grounding contract: every question's correct answer must be verifiable
from the source facts we hand the model. We pass real Wikipedia chunks and
return the citation alongside, so nothing is hallucinated.
"""
import json
import re

from . import retrieval
from . import bedrock

# Phrases that mean the model leaked its grounding context into the question.
# If a generated question contains one, we regenerate (the player never sees
# the source, so these make questions vague/self-referential).
_LEAK_RE = re.compile(
    r"\b(the source|these facts|the facts|this fact|the passage|the text|"
    r"mentioned|described above|as described|provided|listed above|stated above|"
    r"according to the (?:source|passage|text|facts))\b", re.I)

DECADE_LABEL = {"60s": "1960s", "70s": "1970s", "80s": "1980s",
                "90s": "1990s", "00s": "2000s", "all": "1960s–2000s",
                "tdih": "this week in history (June 14–20, any year)"}

QUIZ_SYSTEM = (
    "You are a trivia question writer for a decades study app. You write "
    "factually accurate multiple-choice questions grounded ONLY in the source "
    "facts provided. The correct answer must be directly verifiable from the "
    "facts. Distractors must be plausible but clearly wrong. Never invent "
    "details not present in the sources.\n\n"
    "CRITICAL — the player only ever sees your question, never the source text:\n"
    "- The question MUST be fully self-contained. NEVER refer to 'the source', "
    "'the facts', 'the passage', 'the text', 'mentioned', 'described', 'above', "
    "or 'provided' — the player has no such context.\n"
    "- Put the needed context INSIDE the question (name the year, event, person, "
    "etc.) so it is answerable on its own.\n"
    "- Ask about exactly ONE thing with ONE unambiguous answer. Never combine "
    "two asks (e.g. 'by what margin AND in what time').\n"
    "- If the fact gives a specific year or date, state that exact year in the "
    "question. Never vaguely say 'in the 1980s' or 'the summer of the decade' "
    "when a precise year is available.\n"
    "- Prefer concrete, well-known facts over obscure incidental details."
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
- Self-contained: do NOT mention "the source", "the facts", "mentioned",
  "described", or "above". Bake the context (year/event/person) into the question.
- Only ask about events from this period. If a fact incidentally mentions a year
  from another era, do NOT build the question around that other-era detail.
- Ask ONE thing with ONE clear answer (no two-part questions).
- 4 options; exactly one correct and verifiable from the facts.
- The other 3 are plausible but wrong.
- Vary which option is correct (don't always pick A).
- One-sentence explanation, also without referring to "the source".
- Set source_id to the [id] of the fact the question is based on.

Return ONLY JSON:
{{"question": "...", "choices": ["...","...","...","..."],
  "answer_index": 0, "explanation": "...", "source_id": "{facts[0]['id']}"}}"""

    # Generate, and retry once if the model leaks its source context.
    q = bedrock.generate_json(prompt, system=QUIZ_SYSTEM, temperature=0.7,
                              max_tokens=600)
    if _LEAK_RE.search(q.get("question", "")):
        q = bedrock.generate_json(prompt, system=QUIZ_SYSTEM, temperature=0.5,
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
