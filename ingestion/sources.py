"""Per-decade Wikipedia source pages, grouped by trivia category.

Pages are requested optimistically; the ingester skips any that don't exist
(older decades lack e.g. "1960s in video games"), so it's safe to over-list.
"""

DECADES = {
    "60s": 1960,
    "70s": 1970,
    "80s": 1980,
    "90s": 1990,
    "00s": 2000,
}

# Winter Olympics years don't follow a clean modulo (they shifted off the
# Summer cycle in 1994), so list them explicitly.
WINTER_OLYMPIC_YEARS = {1960, 1964, 1968, 1972, 1976, 1980, 1984, 1988,
                        1992, 1994, 1998, 2002, 2006, 2010}

# Olympic rowing / World Championship pages are medal TABLES, which Wikipedia's
# plain-text extract strips. Prose lives in rower & event bios, so we curate
# standout figures per decade. (This is a rowing-group trivia night, so rowing
# gets first-class coverage.) Decades default to [] until curated.
ROWING_BASE = [           # evergreen rowing pages, added to every decade
    "Henley Royal Regatta",
    "World Rowing Championships",
    "The Boat Race",
]
ROWING_PAGES = {          # decade-specific standout rowers/figures (prose-rich)
    "60s": [
        "Vyacheslav Ivanov (rower)",   # USSR: single sculls gold 1956/60/64
        "Jack Wilson (rower)",
    ],
    "70s": [
        "Pertti Karppinen",            # Finland: single sculls gold 1976...
        "Peter-Michael Kolbe",         # West Germany sculling great
    ],
    "80s": [
        "Steve Redgrave",          # GB legend: gold 1984 (coxed four) & 1988 (coxless pair)
        "Andy Holmes (rower)",     # Redgrave's 1988 pair partner
        "Pertti Karppinen",        # Finland: single sculls gold 1976, 1980, 1984
        "Giuseppe Abbagnale",      # Italy: coxed pair golds, world champions
        "Carmine Abbagnale",
    ],
    "90s": [
        "Steve Redgrave",          # golds 1992 & 1996
        "Matthew Pinsent",         # Redgrave's pair partner, multiple golds
        "Xeno Müller",             # single sculls gold 1996
        "Elisabeta Lipă",          # Romania, most decorated female rower
    ],
    "00s": [
        "Steve Redgrave",          # fifth consecutive gold, Sydney 2000
        "Matthew Pinsent",         # gold 2000 & 2004
        "James Cracknell",         # GB golds 2000 & 2004
        "Mahé Drysdale",           # NZ single sculls dominance
    ],
}


# "This Week in History" — the quizmaster favours on-this-week questions, and
# the trivia night is June 19. We ingest each Wikipedia date page (events/
# births/deaths by year) for the calendar week containing the 19th. Edit
# TDIH_DATES if the date/window moves.
TDIH_KEY = "tdih"
TDIH_LABEL = "This Week in History"
TDIH_DATES = ["June 14", "June 15", "June 16", "June 17",
              "June 18", "June 19", "June 20"]


def pages_for(decade: str) -> list[tuple[str, str]]:
    """Return (category, wikipedia_title) pairs for a decade key like '80s'."""
    start = DECADES[decade]
    d = f"{start}s"            # e.g. "1980s"
    years = range(start, start + 10)

    pages: list[tuple[str, str]] = [
        ("Overview",   d),
        ("Music",      f"{d} in music"),
        ("Film",       f"{d} in film"),
        ("Television", f"{d} in television"),
        ("Video Games", f"{d} in video games"),
        ("Fashion",    f"{d} in fashion"),
    ]
    # Year pages carry dense "events" lists -> great for news/politics trivia.
    for y in years:
        pages.append(("News & Politics", str(y)))
    # Year-in-sports pages (often list-heavy, so we add real event pages below).
    for y in years:
        pages.append(("Sports", f"{y} in sports"))
    # Year-in-music adds chart/award detail beyond the decade overview.
    for y in years:
        pages.append(("Music", f"{y} in music"))

    # --- Sports: marquee events have rich prose (unlike year-in-sports). ---
    summer_oly = [y for y in years if y % 4 == 0]
    winter_oly = [y for y in years if y in WINTER_OLYMPIC_YEARS]
    world_cup = [y for y in years if y % 4 == 2]
    for y in summer_oly:
        pages.append(("Sports", f"{y} Summer Olympics"))
    for y in winter_oly:
        pages.append(("Sports", f"{y} Winter Olympics"))
    for y in world_cup:
        pages.append(("Sports", f"{y} FIFA World Cup"))

    # --- Rowing: dedicated category (this is a rowing-group trivia night). ---
    for y in summer_oly:
        pages.append(("Rowing", f"Rowing at the {y} Summer Olympics"))
    for y in years:
        pages.append(("Rowing", f"{y} World Rowing Championships"))
    for y in years:
        # Oxford–Cambridge Boat Race article naming varies by era; try both,
        # the missing one is skipped during ingestion.
        pages.append(("Rowing", f"{y} Boat Race"))
        pages.append(("Rowing", f"The Boat Race {y}"))
    # Curated prose-rich rower/event bios (tables don't survive extraction).
    for title in ROWING_BASE + ROWING_PAGES.get(decade, []):
        pages.append(("Rowing", title))

    return pages
