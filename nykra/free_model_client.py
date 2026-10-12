"""Explicitly approved and free-route-only OpenRouter inference for supervised Nykra trials.

This is an optional adapter, not an automatically enabled background agent.
Requires an environment-injected OpenRouter API key. Never logs key or raw
provider messages; caller is responsible for retaining model-authored source.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import time
import urllib.error
import urllib.request
from pathlib import Path

from .workstation import _atomic_json, _single_instance
from .store import NykraError


API_URL = "https://openrouter.ai/api/v1/chat/completions"
FREE_MODEL = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*:free$")
_CACHE_SCHEMA = "nykra-exact-free-request-v1"
_MAX_CACHE_BYTES = 256000


class FreeModelError(RuntimeError):
    pass


def generate(prompt: str, *, model: str, max_tokens: int = 1800,
             timeout: int = 90, approve: bool = False,
             token: str | None = None) -> dict:
    if approve is not True:
        raise FreeModelError("inference requires explicit approval")
    if not isinstance(model, str) or not FREE_MODEL.fullmatch(model):
        raise FreeModelError("model must be a fixed provider/model:free route")
    if type(max_tokens) is not int or not 128 <= max_tokens <= 4096:
        raise FreeModelError("max_tokens must be 128-4096")
    if type(timeout) is not int or not 10 <= timeout <= 180:
        raise FreeModelError("timeout must be 10-180 seconds")
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 30000:
        raise FreeModelError("prompt length must be 1-30000 characters")
    token = token if token is not None else os.environ.get("OPENROUTER_API_KEY", "")
    if not token:
        raise FreeModelError("OPENROUTER_API_KEY must be set")
    payload = {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": 0.2,
        "provider": {"allow_fallbacks": False},
        "reasoning": {"enabled": False},
        "stream": False,
    }
    request = urllib.request.Request(
        API_URL, json.dumps(payload).encode("utf-8"),
        {"Authorization": "Bearer " + token,
         "Content-Type": "application/json",
         "User-Agent": "Nykra-supervised-free-proposal/1.0"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            document = json.loads(response.read(1_500_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do not preserve backend exception text; it might include secrets.
        raise FreeModelError(f"model provider HTTP {exc.code}") from None
    except (TimeoutError, OSError) as exc:
        raise FreeModelError(f"model provider connection {type(exc).__name__}") from None
    except (ValueError, UnicodeError, KeyError, TypeError) as exc:
        raise FreeModelError(f"malformed model response {type(exc).__name__}") from None

    usage = document.get("usage") or {}
    if usage.get("cost") is not None and float(usage["cost"]) != 0:
        raise FreeModelError("nonzero provider-reported cost; proposal refused")
    choices = document.get("choices") or []
    if not choices:
        raise FreeModelError("missing model choices")
    message = choices[0].get("message") or {}
    output = message.get("content") or ""
    if not isinstance(output, str) or not output.strip():
        raise FreeModelError("empty model content; reasoning-only output is not a proposal")
    actual = str(document.get("model") or "")
    if actual and actual != model:
        raise FreeModelError("provider changed requested free model identity")
    return {
        "text": output,
        "receipt": {
            "model": model,
            "response_id": str(document.get("id", ""))[:128],
            "sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "chars": len(output),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "tokens": {k: usage.get(k) for k in
                       ("prompt_tokens", "completion_tokens", "total_tokens")},
            "cost": usage.get("cost"),
            "finish_reason": choices[0].get("finish_reason"),
            "free_route_checked": True,
            "independently_verified_free_pricing": False,
        },
    }


def _cache_receipt(original, *, hit: bool, fingerprint: str):
    """Keep original provider usage separate from this request's usage."""
    data = dict(original)
    data["cache_hit"] = hit
    data["provider_called_this_request"] = not hit
    data["provider_calls_avoided"] = 1 if hit else 0
    tokens = original.get("tokens") or {}
    total = tokens.get("total_tokens")
    if total is None and all(type(tokens.get(k)) is int
                             for k in ("prompt_tokens", "completion_tokens")):
        total = tokens["prompt_tokens"] + tokens["completion_tokens"]
    data["provider_tokens_this_request"] = 0 if hit else total
    data["cost_this_request"] = 0 if hit else original.get("cost")
    data["request_hmac_sha256"] = fingerprint
    data["cache_scope"] = "operator_private_explicit_directory_and_API_account"
    return data


def generate_cached(prompt: str, *, model: str, cache_dir: str | Path,
                    max_tokens: int = 1800, timeout: int = 90,
                    approve: bool = False, token: str | None = None) -> dict:
    """Opt-in exact request memoization. No model call on an intact cache hit.

    A cache key uses HMAC with the current API key: identical input from a
    different account is never cross-reused. Only a confirmed $0 successful
    provider receipt may be stored. The human operator controls cache lifetime.
    No raw prompt or API key is persisted. Model-generated text IS persisted.
    """
    if approve is not True:
        raise FreeModelError("inference and replay require explicit approval")
    if not isinstance(model, str) or not FREE_MODEL.fullmatch(model):
        raise FreeModelError("model must be a fixed provider/model:free route")
    if type(max_tokens) is not int or not 128 <= max_tokens <= 4096:
        raise FreeModelError("max_tokens must be 128-4096")
    if type(timeout) is not int or not 10 <= timeout <= 180:
        raise FreeModelError("timeout must be 10-180 seconds")
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 30000:
        raise FreeModelError("prompt length must be 1-30000 characters")
    key = token if token is not None else os.environ.get("OPENROUTER_API_KEY", "")
    if not isinstance(key, str) or not key:
        raise FreeModelError("OPENROUTER_API_KEY must be set")
    # Include all stable wire-level parameters that influence generation.
    # Timeouts do not influence the expected result and aren't in the key.
    serialized = json.dumps({
        "schema": _CACHE_SCHEMA, "endpoint": API_URL,
        "model": model, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0.2, "reasoning_enabled": False,
        "stream": False, "allow_fallbacks": False,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request_id = hmac.new(key.encode("utf-8"), serialized, hashlib.sha256).hexdigest()
    if not isinstance(cache_dir, (str, Path)):
        raise FreeModelError("cache directory must be an explicit local path")
    base = Path(cache_dir).expanduser().absolute()
    if base.is_symlink():
        raise FreeModelError("cache directory must not be a symbolic link")
    if not base.exists():
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
    if base.is_symlink() or not base.is_dir():
        raise FreeModelError("cache directory is not a regular directory")
    if os.name != "nt" and (stat.S_IMODE(base.stat().st_mode) & 0o077):
        raise FreeModelError("cache directory must be private (mode 0700)")
    lock = base / "LOCK"
    if lock.is_symlink():
        raise FreeModelError("cache lock must not be a symbolic link")
    file = base / (request_id + ".json")

    try:
        with _single_instance(lock):
            if file.is_symlink():
                raise FreeModelError("cache entry must not be a symbolic link")
            if file.exists():
                if not file.is_file() or file.stat().st_size > _MAX_CACHE_BYTES:
                    raise FreeModelError("cache entry malformed or oversized")
                try:
                    saved = json.loads(file.read_text(encoding="utf-8"))
                    proposal = saved["text"]
                    receipt = saved["receipt"]
                    signed = json.dumps(
                        {"text": proposal, "receipt": receipt},
                        ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")).encode("utf-8")
                    signature = hmac.new(
                        key.encode("utf-8"), signed, hashlib.sha256).hexdigest()
                    if (not hmac.compare_digest(
                            saved.get("authenticated_record_hmac", ""), signature) or
                            saved["schema"] != _CACHE_SCHEMA or
                            saved["request_hmac_sha256"] != request_id or
                            not isinstance(proposal, str) or not proposal.strip() or
                            not isinstance(receipt, dict) or
                            receipt.get("model") != model or
                            receipt.get("sha256") !=
                            hashlib.sha256(proposal.encode("utf-8")).hexdigest() or
                            type(receipt.get("cost")) not in (int, float) or
                            receipt["cost"] != 0):
                        raise ValueError("invalid cached model provenance")
                except (OSError, ValueError, KeyError, TypeError,
                        UnicodeError) as exc:
                    raise FreeModelError(
                        "cached result failed integrity validation; no provider call"
                    ) from None
                return {
                    "text": proposal,
                    "receipt": _cache_receipt(receipt, hit=True,
                                              fingerprint=request_id),
                }
            result = generate(prompt, model=model, max_tokens=max_tokens,
                              timeout=timeout, approve=approve, token=key)
            original = result["receipt"]
            receipt = _cache_receipt(original, hit=False,
                                      fingerprint=request_id)
            # A free-route suffix is not proof of cost. Unknown or positive
            # provider costs must never be persisted as reusable free evidence.
            if type(original.get("cost")) in (int, float) and original["cost"] == 0:
                signed = json.dumps(
                    {"text": result["text"], "receipt": original},
                    ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")
                record = {
                    "schema": _CACHE_SCHEMA, "request_hmac_sha256": request_id,
                    "text": result["text"], "receipt": original,
                    "authenticated_record_hmac": hmac.new(
                        key.encode("utf-8"), signed, hashlib.sha256).hexdigest(),
                }
                if len(json.dumps(record, ensure_ascii=False).encode("utf-8")) > _MAX_CACHE_BYTES:
                    raise FreeModelError("model response too large to cache")
                _atomic_json(file, record)
                receipt["cache_saved"] = True
            else:
                receipt["cache_saved"] = False
                receipt["cache_save_skipped_reason"] = "provider_cost_unconfirmed"
            return {"text": result["text"], "receipt": receipt}
    except NykraError:
        raise FreeModelError("exact-request cache is busy") from None


def cli(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="One authorized free-route coding inference")
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--reuse-exact-request", action="store_true",
                        help="Opt in to reuse identical requests and avoid the API call")
    parser.add_argument("--cache-dir", type=Path,
                        help="Explicit operator-private cache directory (model source is stored)")
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output_file.exists() or args.output_file.is_symlink():
            raise FreeModelError("refusing to overwrite existing model proposal")
        if args.reuse_exact_request != (args.cache_dir is not None):
            raise FreeModelError("cache reuse requires both --reuse-exact-request and --cache-dir")
        prompt = args.prompt_file.read_text(encoding="utf-8")
        if args.reuse_exact_request:
            result = generate_cached(prompt, model=args.model,
                                     cache_dir=args.cache_dir, max_tokens=args.max_tokens,
                                     timeout=args.timeout, approve=args.approve)
        else:
            result = generate(prompt, model=args.model, max_tokens=args.max_tokens,
                              timeout=args.timeout, approve=args.approve)
        args.output_file.write_text(result["text"], encoding="utf-8", newline="\n")
        print(json.dumps(result["receipt"], sort_keys=True))
        return 0
    except (FreeModelError, OSError, UnicodeError) as exc:
        print(json.dumps({"ready": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
