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

from shared import corpus_s3, quiz, retrieval, stats

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
                    "access-control-allow-origin": "*"},
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
            decades = [{"key": d, "label": retrieval.DECADE_LABEL[d]}
                       for d in corpus_s3.available()]
            return _resp(200, {"decades": decades})

        if path == "/api/categories":
            decade = params["decade"]
            corpus_s3.ensure(decade)
            return _resp(200, {"categories": retrieval.categories(decade)})

        if path == "/api/quiz":
            decade = params["decade"]
            corpus_s3.ensure(decade)
            category = params.get("category") or None
            topic = params.get("topic") or None
            # Adaptive: with no explicit category/topic, bias toward weak areas.
            if not category and not topic:
                category = stats.weak_category(
                    _user(params, headers), decade, retrieval.categories(decade))
            q = quiz.make_question(decade, category=category, topic=topic)
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
