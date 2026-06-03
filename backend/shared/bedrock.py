"""Thin Bedrock helpers shared by ingestion + Lambdas.

Everything is AWS-native: Titan v2 for embeddings, Claude (via an inference
profile) for generation. No external API keys.
"""
import json
import os

import boto3
from botocore.config import Config

REGION = os.environ.get("AWS_REGION", "us-east-2")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0")
# Newer Claude models on Bedrock require an inference-profile id (the "us." prefix).
# Account has invoke access to these three (Sonnet 4.6 / Sonnet 4 are denied).
SONNET = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
OPUS = "us.anthropic.claude-opus-4-5-20251101-v1:0"
HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
# Generate with Opus: high quality AND currently far faster than Sonnet, which
# is heavily throttled on this account (~6s/call vs ~1.5s for Opus).
GEN_MODEL = os.environ.get("GEN_MODEL", OPUS)

# Adaptive retries back off automatically when Bedrock throttles on-demand
# throughput — essential for bulk embedding during ingestion.
_rt = boto3.client(
    "bedrock-runtime", region_name=REGION,
    config=Config(retries={"max_attempts": 10, "mode": "adaptive"}),
)


def embed(text: str) -> list[float]:
    """Embed a single string -> 1024-dim vector."""
    resp = _rt.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText": text[:8000]}),
    )
    return json.loads(resp["body"].read())["embedding"]


def generate(prompt: str, *, max_tokens: int = 800, temperature: float = 0.7,
             system: str | None = None, model: str | None = None) -> str:
    """Single-turn Claude completion, returns plain text."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    resp = _rt.invoke_model(modelId=model or GEN_MODEL, body=json.dumps(body))
    return json.loads(resp["body"].read())["content"][0]["text"]


def generate_json(prompt: str, **kwargs) -> dict:
    """Generate and parse a JSON object, tolerating ```json fences."""
    raw = generate(prompt, **kwargs).strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)
