"""Settings for the daily digest. Everything is overridable through environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DIGEST_DIR = ROOT / "data" / "digests"
SITE_DIR = ROOT / "_site"


def _int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


# --- What to publish -------------------------------------------------------
ITEMS_PER_DAY = _int("DIGEST_ITEMS", 5)
LANGUAGE = os.environ.get("DIGEST_LANGUAGE", "").strip() or "Korean"
TIMEZONE = ZoneInfo(os.environ.get("DIGEST_TIMEZONE", "").strip() or "Asia/Seoul")

# --- Claude ----------------------------------------------------------------
MODEL = os.environ.get("CLAUDE_MODEL", "").strip() or "claude-opus-5-5"
SELECT_EFFORT = os.environ.get("CLAUDE_SELECT_EFFORT", "").strip() or "low"
SUMMARY_EFFORT = os.environ.get("CLAUDE_SUMMARY_EFFORT", "").strip() or "medium"

# --- Candidate collection ----------------------------------------------------
# The digest is about what has been getting attention lately, not about what appeared today, so
# every source looks back a couple of weeks and is ranked by popularity.
HN_WINDOW_DAYS = 10
HN_FRONT_PAGE_MIN_POINTS = 100  # popular stories of any topic, before the title filter
HN_TOPIC_MIN_POINTS = 30  # stories found through HN_QUERIES may be less popular
HN_MAX_CANDIDATES = 30
HN_QUERIES = [
    "LLM",
    "language model",
    "VLM",
    "vision language",
    "VLA",
    "robot learning",
    "inference",
    "quantization",
    "distillation",
    "llama.cpp",
    "local model",
    "on-device",
    "transformer",
    "GPU",
]
# Cheap pre-filter: only stories whose title looks AI-related go to Claude, which does the real
# filtering. (Algolia matches loosely, so the topic queries return unrelated stories too.)
HN_TITLE_PATTERN = (
    r"\b(ai|ml|llms?|vlms?|vla|gpt|claude|gemini|llama|mistral|qwen|deepseek|gemma|phi-\d"
    r"|transformers?|diffusion|inference|quantiz\w*|distill\w*|prun\w*|fine-?tun\w*|lora|tokens?"
    r"|tokeniz\w*|embeddings?|neural|gpus?|cuda|mlx|gguf|ollama|vllm|onnx|tensorrt|on-device"
    r"|language models?|vision[- ]language|multimodal|robots?|robotics|agents?|models?|rag"
    r"|attention|kv[- ]cache|speculative|sparse|sparsity|1-bit|bitnet|mamba|open[- ]weights?"
    r"|benchmarks?|latency|throughput)\b"
)

HF_MAX_AGE_DAYS = 14
HF_MAX_PAGES = 10  # 100 papers per page, newest first
HF_MAX_CANDIDATES = 60  # the most upvoted papers of the window

# arXiv has no popularity signal: these are fresh efficiency papers that only fill a slot when
# nothing well-known is left.
ARXIV_MAX_AGE_DAYS = 4
ARXIV_MAX_CANDIDATES = 20
ARXIV_CATEGORIES = ["cs.CL", "cs.CV", "cs.LG", "cs.RO", "cs.AI"]
# A paper must mention one of these in its abstract ...
ARXIV_TOPIC_TERMS = [
    '"language model"',
    '"language models"',
    "LLM",
    "LLMs",
    '"vision-language"',
    '"vision-language-action"',
    "VLM",
    "VLA",
]
# ... and be about efficiency: one of these words in the title, or one of the phrases below in
# the abstract.
ARXIV_TITLE_TERMS = [
    "efficient",
    "efficiency",
    "quantization",
    "quantized",
    "pruning",
    "distillation",
    "compression",
    "lightweight",
    "fast",
    "faster",
    "acceleration",
    "accelerating",
    "sparse",
    "low-rank",
    "on-device",
    "edge",
    "latency",
    "real-time",
]
ARXIV_ABSTRACT_PHRASES = [
    '"efficient inference"',
    '"inference acceleration"',
    '"inference latency"',
    '"inference cost"',
    '"token pruning"',
    '"token reduction"',
    '"token compression"',
    '"KV cache"',
    '"speculative decoding"',
    '"model compression"',
    '"post-training quantization"',
    '"on-device"',
    '"memory footprint"',
]

# How many past digests are checked so an item is never featured twice.
SEEN_LOOKBACK_DIGESTS = 90

# Text sent to Claude per item.
SELECT_SNIPPET_CHARS = 420
ARTICLE_MAX_CHARS = 6000
# An item is only published when at least this much source text could be read; Claude ranks a few
# spare picks so an unreadable page (JavaScript-only site, bot wall) is replaced, not guessed at.
MIN_SOURCE_CHARS = 300
SPARE_PICKS = 3

USER_AGENT = "research-agent-digest/1.0 (GitHub Actions; daily paper digest)"

# --- Site --------------------------------------------------------------------
SITE_TITLE = os.environ.get("SITE_TITLE", "").strip() or "Efficient AI Daily"
SITE_TAGLINE = (
    os.environ.get("SITE_TAGLINE", "").strip()
    or "요즘 가장 주목받는 LLM · VLM · VLA 연구를 매일 5개, TL;DR로"
)
SITE_URL = os.environ.get("SITE_URL", "").strip().rstrip("/")
