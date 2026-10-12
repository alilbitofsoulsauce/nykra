"""One approved live free-model exact-request cache experiment.

Runs the same prompt N times with an operator-private cache directory. Persists
only request/output hashes and provider receipt metadata, not raw prompt,
generated code, account key, or workstation-specific paths. Never edits a Git
repository, evaluates code, or contacts paid model routes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from nykra.free_model_client import generate_cached


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=450)
    parser.add_argument("--requests", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=70)
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args(argv)
    if not args.approve:
        parser.error("explicit approval required for live model requests")
    if not 2 <= args.requests <= 5:
        parser.error("requests must be in range 2-5")
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing to overwrite an existing evidence file")
    prompt = args.prompt_file.read_text(encoding="utf-8")
    calls = []
    for index in range(1, args.requests+1):
        result = generate_cached(prompt, model=args.model, cache_dir=args.cache_dir,
                                 max_tokens=args.max_tokens,
                                 timeout=args.timeout, approve=True)
        receipt = result["receipt"]
        calls.append({
            "request_number": index,
            "cache_hit": receipt["cache_hit"],
            "provider_called_this_request": receipt["provider_called_this_request"],
            "provider_calls_avoided": receipt["provider_calls_avoided"],
            "provider_tokens_this_request": receipt["provider_tokens_this_request"],
            "cost_this_request": receipt["cost_this_request"],
            "model_reported_original_tokens": receipt["tokens"],
            "original_provider_reported_cost": receipt["cost"],
            "response_id": receipt["response_id"],
            "output_sha256": hashlib.sha256(result["text"].encode("utf-8")).hexdigest(),
        })
    # No attempt to infer independent model behavior from cached outputs.
    if (not calls[0]["provider_called_this_request"] or
            any(x["provider_called_this_request"] for x in calls[1:])):
        raise ValueError("not a clean first-miss then all-hit cache comparison")
    if len({x["output_sha256"] for x in calls}) != 1:
        raise ValueError("cached outputs differ from original")
    if not all(x["original_provider_reported_cost"] == 0 for x in calls):
        raise ValueError("free cost was not confirmed in provider receipts")
    report = {
        "schema": "nykra-v30-live-exact-request-reuse-v1",
        "experiment_kind": "same request replay; not independent multi-prompt coding benchmark",
        "model": args.model,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "output_sha256": calls[0]["output_sha256"],
        "no_prompt_or_source_in_evidence": True,
        "cache_opt_in": True,
        "same_API_account": True,
        "requests": args.requests,
        "provider_calls_observed": sum(x["provider_called_this_request"] for x in calls),
        "provider_calls_avoided": sum(x["provider_calls_avoided"] for x in calls),
        "avoided_call_fraction": sum(x["provider_calls_avoided"] for x in calls)/len(calls),
        "provider_reported_tokens_this_experiment": sum(
            (x["provider_tokens_this_request"] or 0) for x in calls),
        "provider_reported_cost_this_experiment": sum(
            (x["cost_this_request"] or 0) for x in calls),
        "coding_correctness_evaluated": False,
        "policy_accuracy_uplift_claimed": False,
        "general_token_savings_claimed": False,
        "caveats": [
            "The replayed prompts are exactly identical by design.",
            "The cache does not predict whether distinct prompts produce identical code.",
            "The first request uses paid/fee-protected free endpoint; provider reported zero cost.",
            "The result does not measure correctness or any adaptive policy win.",
            "Cached model-generated text remains stored in the operator's private directory.",
        ],
        "call_receipts": calls,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({
        "requests": report["requests"],
        "provider_calls": report["provider_calls_observed"],
        "avoided": report["provider_calls_avoided"],
        "tokens_this_experiment": report["provider_reported_tokens_this_experiment"],
        "cost": report["provider_reported_cost_this_experiment"],
        "evidence_file": str(args.output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
