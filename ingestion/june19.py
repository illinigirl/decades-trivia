"""Insert curated June 19 questions (Juneteenth + the day's observances).

These are authored from a trusted source (nationaltoday.com) and inserted
directly — the quirky national days (Martini, Sauntering, Box Day) would fail
the two-model consensus check because the models don't reliably know them, but
they're exactly the kind of "it's June 19" question the quizmaster may ask.

Goes into the standalone This Week (tdih) slice, plus the relevant decade slice
for dated ones (Garfield 1978, FreeBSD 1993). Served shuffled, so answer_index 0
is fine. Run from repo root with venv + AWS creds:
  AWS_PROFILE=watchtower AWS_REGION=us-east-2 ./venv/bin/python ingestion/june19.py
"""
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

REGION = os.environ.get("AWS_REGION", "us-east-2")
_cf = boto3.client("cloudformation", region_name=REGION)
_outs = _cf.describe_stacks(StackName="decades-trivia")["Stacks"][0]["Outputs"]
os.environ["QUESTIONS_TABLE"] = next(
    o["OutputValue"] for o in _outs if o["OutputKey"] == "QuestionsTable")

from shared import bank  # noqa: E402

CAT = "This Week in History"

# Each: subject, question, choices, answer_index, explanation, optional decade.
QUESTIONS = [
    {"subject": "Juneteenth Galveston",
     "question": "Juneteenth commemorates June 19, 1865, when Union troops arrived in which Texas city to announce that enslaved people were free?",
     "choices": ["Galveston", "Houston", "Austin", "San Antonio"], "answer_index": 0,
     "explanation": "On June 19, 1865, Major General Gordon Granger arrived in Galveston, Texas and issued General Order No. 3 announcing freedom for the enslaved."},
    {"subject": "Juneteenth federal holiday year",
     "question": "In what year did Juneteenth (June 19) become an official U.S. federal holiday?",
     "choices": ["2021", "2008", "2016", "1999"], "answer_index": 0,
     "explanation": "President Biden signed the Juneteenth National Independence Day Act into law in June 2021."},
    {"subject": "Juneteenth word blend",
     "question": "The holiday name 'Juneteenth' is a blend of which two words?",
     "choices": ["June and nineteenth", "June and thirteenth", "July and nineteenth", "June and juneberry"], "answer_index": 0,
     "explanation": "'Juneteenth' combines 'June' and 'nineteenth,' for June 19."},
    {"subject": "Garfield comic debut June 19",
     "question": "On June 19, 1978, which comic strip about a lazy, lasagna-loving cat first appeared in 41 newspapers?",
     "choices": ["Garfield", "Calvin and Hobbes", "The Far Side", "Heathcliff"], "answer_index": 0,
     "explanation": "Jim Davis's 'Garfield' debuted on June 19, 1978.", "decade": "70s"},
    {"subject": "National Martini Day June 19",
     "question": "June 19 is the U.S. observance 'National ___ Day,' honoring a classic cocktail of gin (or vodka) and vermouth. Which drink?",
     "choices": ["Martini", "Margarita", "Manhattan", "Mojito"], "answer_index": 0,
     "explanation": "June 19 is National Martini Day."},
    {"subject": "World Sickle Cell Day June 19",
     "question": "June 19 is 'World ___ Day,' a UN-recognized awareness day for an inherited red-blood-cell disorder. Which condition?",
     "choices": ["Sickle Cell", "Hemophilia", "Diabetes", "Leukemia"], "answer_index": 0,
     "explanation": "June 19 is World Sickle Cell Day, recognized by the United Nations."},
    {"subject": "National Flip Flop Day June 19",
     "question": "June 19 celebrates 'National ___ Day,' honoring the foam sandal that's a summer staple. Which footwear?",
     "choices": ["Flip Flop", "Loafer", "Clog", "Sneaker"], "answer_index": 0,
     "explanation": "National Flip Flop Day falls on June 19."},
    {"subject": "World Sauntering Day June 19",
     "question": "June 19 is 'World ___ Day,' encouraging people to slow down and stroll leisurely rather than rush. What activity?",
     "choices": ["Sauntering", "Jogging", "Cycling", "Marching"], "answer_index": 0,
     "explanation": "World Sauntering Day (June 19) promotes leisurely walking."},
    {"subject": "International Box Day June 19 cats",
     "question": "June 19's 'International Box Day' encourages owners of which pets to leave out cardboard boxes?",
     "choices": ["Cats", "Dogs", "Rabbits", "Ferrets"], "answer_index": 0,
     "explanation": "International Box Day encourages cat owners to provide cardboard boxes their cats love."},
    {"subject": "National FreeBSD Day June 19",
     "question": "June 19, 1993 is marked as 'National FreeBSD Day,' celebrating the release of what kind of software?",
     "choices": ["An open-source operating system", "A web browser", "A video game", "A spreadsheet app"], "answer_index": 0,
     "explanation": "FreeBSD, an open-source Unix-like operating system, dates to June 19, 1993.", "decade": "90s"},
    {"subject": "National Watch Day June 19",
     "question": "June 19 is 'National ___ Day,' celebrating the timepieces people wear on their wrists. What item?",
     "choices": ["Watch", "Ring", "Bracelet", "Belt"], "answer_index": 0,
     "explanation": "June 19 is National Watch Day."},
]


def main() -> None:
    n = 0
    for q in QUESTIONS:
        q = {**q, "category": CAT, "source": None}
        bank.put("tdih", CAT, {**q, "decade": "tdih"})          # standalone any-year
        n += 1
        if q.get("decade"):                                      # also its decade
            bank.put(q["decade"], CAT, dict(q))
            n += 1
    print(f"inserted {n} June 19 question rows")


if __name__ == "__main__":
    main()
