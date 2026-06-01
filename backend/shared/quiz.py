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
    "You write questions for an American pub trivia night — the fun, social kind "
    "at a bar. Questions should feel like real pub trivia: about NOTABLE, "
    "memorable people, songs, albums, films, TV shows, athletes, inventions, and "
    "major events that a general crowd has plausibly heard of, with a satisfying "
    "'oh yeah!' answer.\n\n"
    "Ground every question ONLY in the source facts provided; the correct answer "
    "must be verifiable from them. Never invent details.\n\n"
    "PICK WELL — you are given several candidate facts:\n"
    "- Choose the ONE that is most notable and memorable (a famous person, work, "
    "team, invention, or major event).\n"
    "- SKIP incidental minutiae even when present: exact margins / scores / counts "
    "/ measurements, precise dates beyond the year, names of non-famous "
    "individuals, administrative or procedural details. Those are too obscure to "
    "know or remember and make bad pub questions.\n"
    "- Where possible make the ANSWER the recognizable thing, with fair clues in "
    "the question.\n\n"
    "WRITE WELL — the player only ever sees your question, never the source:\n"
    "- Fully self-contained. NEVER say 'the source', 'the facts', 'mentioned', "
    "'described', 'above', or 'provided'. Bake the context (year, event, person) "
    "into the question.\n"
    "- If the fact has a specific year, use that exact year — never vague 'in the "
    "1980s'. Only ask about this era; ignore incidental other-era mentions.\n"
    "- Ask ONE thing with ONE unambiguous answer (no two-part questions).\n"
    "- EVERY claim in the question (team, place, role, year, etc.) must come from "
    "the chosen fact. Never add or change an attribute — e.g. do not call someone "
    "a Phillies player if the fact says Pirates.\n"
    "- Four options: exactly one correct, three plausible and clearly wrong (real "
    "same-category options). Vary which option is correct.\n\n"
    "GOOD:  'Which 1982 Michael Jackson album became the best-selling album of all "
    "time?' -> Thriller\n"
    "BAD (minutiae): 'By how many pounds per rower was the 1984 Oxford Boat Race "
    "crew heavier than Cambridge?'  /  'What was the name of the cox who steered "
    "Oxford in the 1987 Boat Race?'"
)


VERIFY_SYSTEM = (
    "You check ONE trivia question for consistency with a source fact. Treat the "
    "SOURCE FACT as ground truth — do NOT critique it or use outside knowledge. "
    "Your only job: does the QUESTION contradict the fact, or does the marked "
    "CORRECT ANSWER disagree with the fact? Flag a wrong team, place, year, "
    "person, or role. Ignore anything the question does not actually claim. If "
    "the question and correct answer are consistent with the fact, it is ok."
)


def _verify(fact_text: str, q: dict) -> tuple[bool, str]:
    """True if the question + correct answer are fully supported by the fact."""
    try:
        ans = q["choices"][q["answer_index"]]
    except (KeyError, IndexError, TypeError):
        return False, "malformed question"
    prompt = f"""SOURCE FACT:
{fact_text}

QUESTION: {q.get('question','')}
STATED CORRECT ANSWER: {ans}

Is every factual claim in the QUESTION and the CORRECT ANSWER supported by the
SOURCE FACT, with no contradiction (wrong team/place/year/person/role)?
Return ONLY JSON: {{"ok": true, "problem": ""}}"""
    try:
        v = bedrock.generate_json(prompt, system=VERIFY_SYSTEM,
                                  temperature=0, max_tokens=120)
        return bool(v.get("ok")), str(v.get("problem", ""))
    except Exception:
        return True, ""   # never block question generation on a verifier hiccup


def make_question(decade: str, *, category: str | None = None,
                  topic: str | None = None, difficulty: str = "medium") -> dict:
    """Generate one grounded multiple-choice question.

    topic    -> semantic search for relevant facts (focused study)
    no topic -> random sample for variety (general quiz)
    """
    # Wider candidate pool for general quizzes so the model can pick a notable
    # fact rather than being stuck with one random (often obscure) chunk.
    if topic:
        facts = retrieval.search(decade, topic, k=6, category=category)
    else:
        facts = retrieval.sample(decade, n=9, category=category)
    if not facts:
        raise ValueError(f"no facts for decade={decade} category={category}")

    by_id = {f["id"]: f for f in facts}
    fact_block = "\n\n".join(f"[{f['id']}] ({f['category']}) {f['text']}"
                             for f in facts)

    prompt = f"""Candidate facts about the {DECADE_LABEL.get(decade, decade)} —
pick the most NOTABLE and pub-worthy one and ignore the obscure/minutiae ones:

{fact_block}

Write ONE {difficulty}-difficulty multiple-choice pub-trivia question from the
most notable fact, following all the rules. Set source_id to the [id] you used.

Return ONLY JSON:
{{"question": "...", "choices": ["...","...","...","..."],
  "answer_index": 0, "explanation": "...", "source_id": "{facts[0]['id']}"}}"""

    # Generate, then retry if the question leaks its source context OR fails the
    # fact-check (a claim in the stem/answer contradicts the chosen fact).
    guidance = ""
    for attempt in range(3):
        q = bedrock.generate_json(prompt + guidance, system=QUIZ_SYSTEM,
                                  temperature=0.7 if attempt == 0 else 0.4,
                                  max_tokens=600)
        if _LEAK_RE.search(q.get("question", "")):
            guidance = ("\n\nThe question must be fully self-contained — never "
                        "reference the source/facts.")
            continue
        src = by_id.get(q.get("source_id"), facts[0])
        ok, problem = _verify(src["text"], q)
        if ok:
            break
        guidance = (f"\n\nA previous attempt was factually wrong: {problem}. "
                    "Every claim in the question and answer must match the chosen "
                    "fact exactly (correct team, place, year, person, role).")

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
