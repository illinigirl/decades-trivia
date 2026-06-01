# Decades Trivia

A RAG-grounded trivia study app for a decades-themed trivia night. Pick a
decade (60s/70s/80s/90s/00s), get quizzed across categories, track hits and
misses, and review facts — every question grounded in real Wikipedia source
text with a citation, so nothing is hallucinated.

Built fully AWS-native: **Bedrock Titan** for embeddings, **Bedrock Claude
(Haiku 4.5)** for generation, **Lambda + API Gateway + DynamoDB** for the app,
**S3 + CloudFront** for the static frontend. No external API keys.

## How it works

1. **Ingestion** (`ingestion/ingest.py`, run locally) fetches Wikipedia pages
   per decade by category, chunks them into facts, embeds each with Titan, and
   writes `corpus/<decade>.json` + `corpus/<decade>.f32` (raw float32 vectors).
2. **Retrieval** (`backend/shared/retrieval.py`) loads a corpus and does cosine
   search (numpy locally, pure-Python in Lambda — so no numpy layer needed).
3. **Quiz** (`backend/shared/quiz.py`) generates multiple-choice questions
   grounded in retrieved/sampled facts, returning the source citation.

## Categories

Overview, Music, Film, Television, Video Games, Fashion, News & Politics,
Sports, and **Rowing** (it's a rowing-group trivia night — Olympic rowers,
the Boat Race, Henley get first-class coverage).

## Local study (works today, before AWS deploy)

```bash
python3 -m venv venv && ./venv/bin/pip install boto3 numpy
AWS_PROFILE=watchtower AWS_REGION=us-east-2 ./venv/bin/python ingestion/ingest.py 80s
AWS_PROFILE=watchtower AWS_REGION=us-east-2 ./venv/bin/python study.py 80s
```

`study.py` is an interactive terminal quiz: it tracks per-category accuracy in
`study_stats.json` and biases questions toward your weak areas.

## Deploy (AWS)

```bash
./deploy.sh        # SAM build + deploy, uploads corpus to S3
```
