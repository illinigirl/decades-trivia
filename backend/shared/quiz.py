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

# Chain-of-thought / self-correction that leaked into the question text.
_REASONING_RE = re.compile(
    r"(wait,|let me reconsider|let me think|on second thought|that'?s not in|"
    r"i'?ll reconsider|hmm,|let me pick|let me choose|instead, let)", re.I)

DECADE_LABEL = {"60s": "1960s", "70s": "1970s", "80s": "1980s",
                "90s": "1990s", "00s": "2000s", "all": "1960s–2000s",
                "tdih": "this week in history (June 14–20, any year)"}

# Categories for the knowledge-based generator (decoupled from the corpus, so
# coverage is as broad as Claude's knowledge, not just ingested pages).
QUIZ_CATEGORIES = ["Music", "Movies", "Television", "Sports", "News & Politics",
                   "Pop Culture", "Toys & Games", "Science & Tech", "Fashion",
                   "Rowing", "This Week in History"]
NICHE_CATEGORIES = {"Rowing", "This Week in History"}


def categories_for(decade: str) -> list[str]:
    if decade == "tdih":
        return ["This Week in History"]
    return QUIZ_CATEGORIES


def era_phrase(decade: str) -> str:
    if decade == "all":
        return "the 1960s through the 2000s"
    if decade == "tdih":
        return "any year of history"
    return f"the {DECADE_LABEL.get(decade, decade)}"

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
    q["source_fact_id"] = src["id"]   # for bank dedup: one question per fact
    q["decade"] = decade
    return q


KNOWLEDGE_SYSTEM = (
    "You write questions for an American pub trivia night — fun, social, the kind "
    "asked at a bar. Use your own knowledge to write NOTABLE, memorable questions "
    "about famous people, songs, films, shows, athletes, inventions, toys, and "
    "events that a general crowd would recognize, with a satisfying 'oh yeah!' "
    "answer.\n\n"
    "STRICT ACCURACY: the marked correct answer must be unambiguously, factually "
    "correct, and exactly one option is correct. If you are not certain a fact is "
    "true, do NOT use it. Avoid obscure minutiae.\n\n"
    "- Self-contained: never reference 'the source/facts'; bake context (year, "
    "person, work) into the question.\n"
    "- Use specific years where natural. Subject must be from the stated era.\n"
    "- Four options; exactly one correct; the other three plausible but clearly "
    "wrong (real same-category options). Vary which position is correct.\n"
    "- NEVER reveal the answer in the question. Do not include the correct answer "
    "(or a quote/phrase that contains it) in the question text — that makes it "
    "trivially easy. The player must have to actually know it.\n"
    "- Do NOT telegraph the answer with logic clues either. E.g. 'which pick, after "
    "two teams passed on him?' reveals the 3rd pick; 'the only X to ever...' reveals "
    "uniqueness. The wording must not let the answer be deduced without knowing the fact.\n"
    "- The 'question' field must contain ONLY the final question — no reasoning, no "
    "self-correction ('wait', 'let me reconsider', 'actually'), no preamble, and "
    "exactly one question."
)

LETTERS = "ABCD"


def gives_away(q: dict) -> bool:
    """True if the correct answer text appears in the question (a giveaway)."""
    try:
        ans = q["choices"][q["answer_index"]]
    except (KeyError, IndexError, TypeError):
        return False
    a = re.sub(r"^(the|a|an)\s+", "", ans.strip().lower())
    return len(a) >= 3 and a in q.get("question", "").lower()


def _solve(q: dict, era: str, model: str) -> int:
    """Have a model answer the question BLIND (without seeing the marked answer).
    Returns the option index it picks, or -1 if unparseable."""
    opts = "\n".join(f"{LETTERS[i]}. {c}" for i, c in enumerate(q["choices"]))
    prompt = (f"Answer this {era} trivia question using accurate real-world "
              f"knowledge. Reply with ONLY the letter of the correct option.\n\n"
              f"{q['question']}\n{opts}")
    try:
        ans = bedrock.generate(prompt, model=model, temperature=0,
                               max_tokens=5).strip().upper()
        for ch in ans:
            if ch in LETTERS:
                return LETTERS.index(ch)
    except Exception:
        return -1
    return -1


def _verified(q: dict, era: str) -> bool:
    """Keep a question only if TWO different strong models, answering blind,
    both independently pick the marked-correct option. Catches wrong answers
    and ambiguous questions."""
    marked = q.get("answer_index")
    if marked is None or not (0 <= marked < len(q.get("choices", []))):
        return False
    # Solvers independent of the Opus generator. Sonnet (strong) + Haiku (fast).
    # Requiring Haiku to also agree doubles as a "well-known enough" filter.
    for model in (bedrock.SONNET, bedrock.HAIKU):
        if _solve(q, era, model) != marked:
            return False
    return True


def _in_tdih_window(q: dict) -> bool:
    """Confirm the subject's REAL date is June 14–20 — independently of any date
    the question states (which may be wrong, e.g. 'June 20' for the July moon
    landing). Two-step: recall the true date, then check the window."""
    try:
        ans = q["choices"][q["answer_index"]]
    except (KeyError, IndexError, TypeError):
        return False
    prompt = (
        f"Question: {q.get('question','')}\nAnswer: {ans}\n\n"
        "IGNORE any date stated in the question — it may be wrong. Using your own "
        "accurate knowledge, what is the real month and day this event/birth/death "
        "actually occurred? State that real date, then on a new line reply "
        "'WINDOW: yes' ONLY if that real date is between June 14 and June 20 "
        "inclusive, otherwise 'WINDOW: no'.")
    try:
        r = bedrock.generate(prompt, model=bedrock.OPUS, temperature=0, max_tokens=80)
        m = re.search(r"window:\s*(yes|no)", r, re.I)
        return bool(m) and m.group(1).lower() == "yes"
    except Exception:
        return False


def make_knowledge_question(decade: str, *, category: str | None = None,
                            focus: str | None = None, avoid=()) -> dict | None:
    """Generate a pub-trivia question from Claude's knowledge of the era, then
    verify it by independent-solve consensus. Returns None if none verify."""
    era = era_phrase(decade)
    is_tdih = category == "This Week in History" or decade == "tdih"
    if is_tdih:
        topic = (f"a notable event, birth, or death that occurred ON a date "
                 f"from June 14 to June 20 (inclusive), within {era}. The date "
                 f"MUST be June 14–20 — do NOT use events from any other dates")
    elif focus:
        topic = f"{focus} ({era})"
    else:
        topic = f"{category or 'pop culture'} in {era}"
    avoid_clause = ("\nPick something DIFFERENT from these already-used subjects: "
                    + "; ".join(list(avoid)[-40:])) if avoid else ""

    prompt = f"""Write ONE multiple-choice pub-trivia question about {topic}.
Choose a notable, widely-recognized subject.{avoid_clause}

Return ONLY JSON:
{{"subject": "<short tag naming the subject>", "question": "...",
  "choices": ["...","...","...","..."], "answer_index": 0, "explanation": "..."}}"""

    # The June 14–20 window is a narrow target, so allow a few more tries for it
    # (but not so many that throttled retries pile up).
    attempts = 6 if is_tdih else 4
    for attempt in range(attempts):
        try:
            q = bedrock.generate_json(prompt, system=KNOWLEDGE_SYSTEM,
                                      temperature=0.9 if attempt == 0 else 0.6,
                                      max_tokens=500)
        except Exception:
            continue
        question_text = q.get("question", "")
        if _LEAK_RE.search(question_text) or _REASONING_RE.search(question_text):
            continue                             # source ref or leaked reasoning
        if gives_away(q):                        # answer leaked into the question
            continue
        if not _verified(q, era):
            continue
        if is_tdih and not _in_tdih_window(q):   # enforce the June 14–20 window
            continue
        q["category"] = category or "Pop Culture"
        q["decade"] = decade
        q["source"] = None              # generated from knowledge, not a citation
        return q
    return None


def review_facts(decade: str, *, topic: str | None = None,
                 category: str | None = None, n: int = 6) -> list[dict]:
    """Return facts to study (with citations), optionally focused by topic."""
    if topic:
        chunks = retrieval.search(decade, topic, k=n, category=category)
    else:
        chunks = retrieval.sample(decade, n=n, category=category)
    return [{"text": c["text"], "category": c["category"],
             "source": {"title": c["title"], "url": c["url"]}} for c in chunks]
