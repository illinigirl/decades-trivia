"""Unit tests for the serve/generation safety guards.

Pure functions only — no AWS, no network. Run from the repo root:

    pip install boto3            # quiz.py imports bedrock -> boto3 (client is lazy)
    python -m pytest tests/

`is_clean` is the guard applied both at generation time and at serve time, so a
question that leaks its reasoning/source or gives its own answer away is never
shown — including stale entries already sitting in the bank.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from shared import quiz  # noqa: E402


# The exact failure from the live screenshot: the model's self-correction leaked
# into the question text ("Wait, that's not in the range. Let me reconsider...").
LEAKED = {
    "question": (
        "On June 27, 1988, Mike Tyson knocked out Michael Spinks in just 91 "
        "seconds. Wait, that's not in the June 14-20 range. Let me reconsider. "
        "Actually, on June 20, 1987, which professional golfer won the U.S. Open "
        "at the Olympic Club in San Francisco?"
    ),
    "choices": ["Larry Mize", "Curtis Strange", "Tom Watson", "Scott Simpson"],
    "answer_index": 3,
}

CLEAN = {
    "question": "Which golfer won the 1987 U.S. Open at the Olympic Club?",
    "choices": ["Larry Mize", "Curtis Strange", "Tom Watson", "Scott Simpson"],
    "answer_index": 3,
}

# Answer text appears verbatim in the question -> giveaway.
GIVEAWAY = {
    "question": "Did Scott Simpson win the 1987 U.S. Open?",
    "choices": ["Larry Mize", "Curtis Strange", "Tom Watson", "Scott Simpson"],
    "answer_index": 3,
}

SOURCE_LEAK = {
    "question": "According to the source, which golfer won the 1987 U.S. Open?",
    "choices": ["Larry Mize", "Curtis Strange", "Tom Watson", "Scott Simpson"],
    "answer_index": 3,
}


def test_leaked_reasoning_is_rejected():
    assert quiz.is_clean(LEAKED) is False


def test_clean_question_passes():
    assert quiz.is_clean(CLEAN) is True


def test_giveaway_is_rejected():
    assert quiz.is_clean(GIVEAWAY) is False


def test_source_leak_is_rejected():
    assert quiz.is_clean(SOURCE_LEAK) is False
