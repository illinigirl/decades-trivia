"""Single Lambda behind an HTTP API. Serves the frontend at GET / and the
JSON endpoints under /api/*. Corpus is pulled from S3 into /tmp on demand.

Routes:
  GET  /                              -> SPA (index.html)
  GET  /api/meta                      -> {decades:[{key,label}]}
  GET  /api/categories?decade=        -> {categories:[...]}
  GET  /api/quiz?decade=&category=&topic=&user=
  POST /api/answer  {decade,category,correct,user}
  GET  /api/facts?decade=&topic=&category=
  GET  /api/stats?decade=&user=
"""
import json
import os
import random

from shared import bank, corpus_s3, quiz, retrieval, stats

_INDEX_HTML = None


def _index() -> str:
    global _INDEX_HTML
    if _INDEX_HTML is None:
        path = os.path.join(os.path.dirname(__file__), "index.html")
        with open(path) as f:
            _INDEX_HTML = f.read()
    return _INDEX_HTML


def _resp(status: int, body, *, content_type="application/json"):
    payload = body if isinstance(body, str) else json.dumps(body)
    return {
        "statusCode": status,
        "headers": {"content-type": content_type,
                    "access-control-allow-origin": "*",
                    # Never let the browser cache responses — a constant /api/quiz
                    # URL would otherwise return the same cached question, and a
                    # cached index.html would never pick up updates.
                    "cache-control": "no-store, no-cache, must-revalidate"},
        "body": payload,
    }


def _user(params: dict, headers: dict) -> str:
    return (params.get("user") or headers.get("x-user") or "anon").strip()[:64]


def handler(event, context):
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = event.get("rawPath", "/")
    params = event.get("queryStringParameters") or {}
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    try:
        if path in ("/", "/index.html"):
            return _resp(200, _index(), content_type="text/html; charset=utf-8")

        if path == "/api/meta":
            avail = corpus_s3.available()
            decades = [{"key": d, "label": retrieval.DECADE_LABEL[d]} for d in avail]
            if len(avail) >= 2:   # "all decades" only meaningful with multiple
                decades.append({"key": retrieval.ALL_KEY, "label": "All decades"})
            if corpus_s3.exists(retrieval.TDIH_KEY):   # first-class "this week" mode
                decades.append({"key": retrieval.TDIH_KEY,
                                "label": "🗓 This Week in History"})
            return _resp(200, {"decades": decades})

        if path == "/api/categories":
            return _resp(200, {"categories": quiz.categories_for(params["decade"])})

        if path == "/api/quiz":
            decade = params["decade"]
            topic = params.get("topic") or None
            user = _user(params, headers)
            fresh = params.get("fresh") == "1"
            client_recent = [x for x in (params.get("exclude") or "").split(",") if x]
            cats = quiz.categories_for(decade)
            yr = retrieval.year_range(decade)

            # Focused topic study: generate live from knowledge (verified).
            if topic:
                q = quiz.make_knowledge_question(decade, focus=topic)
                if q:
                    q["id"] = bank.put(decade, q.get("category", "Pop Culture"), q)
                    bank.shuffle_choices(q)
                    stats.record_served(user, decade, q["id"])
                    return _resp(200, q)

            # Resolve a concrete category (adaptive -> weak area -> random).
            category = (params.get("category")
                        or stats.weak_category(user, decade, cats)
                        or random.choice(cats))

            # Combine server-side history with the client's list so repeats are
            # prevented even if the browser sends nothing.
            recent = list(dict.fromkeys(stats.recent_served(user, decade)
                                        + client_recent))
            recent_set = set(recent)

            # Serve an unseen banked question if one exists (instant); else
            # generate live (verified) and cache it.
            q = None
            if not fresh:
                q = bank.random_question(decade, category, recent, yr)
            if q is None:
                q = quiz.make_knowledge_question(decade, category=category)
                if q and bank.item_key(q) in recent_set:    # same subject -> retry
                    alt = quiz.make_knowledge_question(decade, category=category)
                    if alt and bank.item_key(alt) not in recent_set:
                        q = alt
                if q is None:        # generation failed -> serve any banked question
                    q = bank.random_question(decade, category, [], yr)
                    if q is None:
                        return _resp(503, {"error": "could not produce a question; "
                                           "please try again"})
                else:
                    q["id"] = bank.put(decade, category, q)
                    bank.shuffle_choices(q)

            stats.record_served(user, decade, q["id"])
            return _resp(200, q)

        if path == "/api/answer" and method == "POST":
            body = json.loads(event.get("body") or "{}")
            user = _user({**params, **body}, headers)
            stats.record(user, body["decade"], body["category"],
                         bool(body["correct"]))
            return _resp(200, {"stats": stats.get(user, body["decade"])})

        if path == "/api/facts":
            decade = params["decade"]
            corpus_s3.ensure(decade)
            facts = quiz.review_facts(decade, topic=params.get("topic") or None,
                                      category=params.get("category") or None,
                                      n=int(params.get("n", 6)))
            return _resp(200, {"facts": facts})

        if path == "/api/stats":
            decade = params["decade"]
            return _resp(200, {"stats": stats.get(_user(params, headers), decade)})

        return _resp(404, {"error": "not found", "path": path})
    except KeyError as e:
        return _resp(400, {"error": f"missing parameter: {e}"})
    except Exception as e:  # surface errors as JSON during the build phase
        return _resp(500, {"error": str(e), "type": type(e).__name__})
