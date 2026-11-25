"""One function, ``ask_json``: send a prompt to Claude and get schema-valid JSON back.

Two ways to authenticate, picked from the environment:

* ``ANTHROPIC_API_KEY``        -> Anthropic API through the official SDK (pay per token).
* ``CLAUDE_CODE_OAUTH_TOKEN``  -> Claude Code CLI in headless mode (uses a Claude subscription;
                                  create the token with ``claude setup-token``).

``DIGEST_LLM_BACKEND=sdk|cli`` forces one of them.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

from . import config

# Models that accept the server-side refusal fallback: if a safety classifier declines a request
# (it can misfire on ML-research text), the API re-runs it on another model in the same call.
FALLBACK_MODELS = {
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
    "claude-fable-5-2",
    "claude-fable-5-1",
}
MAX_TOKENS = 16000


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    models: set[str] = field(default_factory=set)

    def add(self, input_tokens: int, output_tokens: int, model: str) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1
        self.models.add(model)

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "calls": self.calls,
            "models": sorted(self.models),
        }


USAGE = Usage()


class LLMError(RuntimeError):
    pass


def backend() -> str:
    forced = os.environ.get("DIGEST_LLM_BACKEND", "").strip().lower()
    if forced in ("sdk", "cli"):
        return forced
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "sdk"
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return "cli"
    raise LLMError(
        "No Claude credentials found. Add the repository secret ANTHROPIC_API_KEY (API billing) "
        "or CLAUDE_CODE_OAUTH_TOKEN (Claude subscription, from `claude setup-token`)."
    )


def ask_json(system: str, user: str, schema: dict, *, effort: str) -> dict:
    if backend() == "sdk":
        return _ask_sdk(system, user, schema, effort)
    return _ask_cli(system, user, schema, effort)


def _ask_sdk(system: str, user: str, schema: dict, effort: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(max_retries=4)
    request = {
        "model": config.MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }
    try:
        if config.MODEL in FALLBACK_MODELS:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
            )
        else:
            response = client.messages.create(**request)
    except anthropic.AuthenticationError as error:
        raise LLMError("ANTHROPIC_API_KEY was rejected - check the repository secret.") from error
    except anthropic.NotFoundError as error:
        raise LLMError(f"Model {config.MODEL!r} not found - check CLAUDE_MODEL.") from error

    USAGE.add(response.usage.input_tokens, response.usage.output_tokens, response.model)
    if response.stop_reason == "refusal":
        details = response.stop_details
        raise LLMError(f"Claude declined the request ({details.category if details else 'unknown'}).")
    if response.stop_reason == "max_tokens":
        raise LLMError("Claude's answer was cut off at max_tokens.")
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def _ask_cli(system: str, user: str, schema: dict, effort: str) -> dict:
    command = [
        "claude",
        "--print",
        "--model", config.MODEL,
        "--effort", effort,
        "--output-format", "json",
        "--tools", "",  # plain text-in / JSON-out: no file, shell or web tools
        "--system-prompt", system,
        "--json-schema", json.dumps(schema),
    ]  # fmt: skip
    # An empty ANTHROPIC_API_KEY (unset repository secret) must not shadow the subscription token.
    env = {name: value for name, value in os.environ.items() if value}
    try:
        completed = subprocess.run(
            command, input=user, capture_output=True, text=True, timeout=900, env=env
        )
    except FileNotFoundError as error:
        raise LLMError("`claude` CLI not found: npm install -g @anthropic-ai/claude-code") from error
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise LLMError(
            f"claude CLI failed (exit {completed.returncode}): "
            f"{(completed.stderr or completed.stdout)[-800:]}"
        ) from error
    if result.get("is_error") or completed.returncode != 0:
        raise LLMError(f"claude CLI error: {str(result.get('result'))[:800]}")

    for model, used in (result.get("modelUsage") or {}).items():
        input_tokens = sum(
            used.get(key, 0)
            for key in ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
        )
        USAGE.add(input_tokens, used.get("outputTokens", 0), model)
        USAGE.calls -= 1
    USAGE.calls += 1
    structured = result.get("structured_output")
    return structured if structured is not None else json.loads(result["result"])
