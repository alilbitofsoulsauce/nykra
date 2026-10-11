"""v0.23 no-model-call replay of real Git patches under ordinary vs reused grading.

Frozen original Codex-generated source from v0.22 is replayed, not regenerated:
same source, controller and public tests. The only intervention is whether a
second matching policy session repeats Git apply + Docker public evaluation or
inherits the first, verified local receipt. Hidden final testing is always
independent per arm and never replayed.

Model effectiveness isn't being measured: this isolates avoidable execution
work, and is not a new-agent benchmark or a model token-savings observation.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import agent_workflow as wf
from .v20_grader import EVIDENCE, ROOT
from .v21_grader import manifest


PROTOCOL = EVIDENCE / "v23_reuse_protocol.json"
INDEX = EVIDENCE / "v22_session_export_index.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen():
    raw = PROTOCOL.read_bytes()
    doc = json.loads(raw)
    _, evaluator_sha = manifest()
    if doc["id"] != "nykra-v23-exact-replay-public-evaluation-reuse-v1":
        raise ValueError("unexpected frozen replay protocol")
    if doc["v21_evaluator_sha256"] != evaluator_sha:
        raise ValueError("target repository/evaluator protocol modified")
    if doc["v22_portable_session_index_sha256"] != _sha(INDEX):
        raise ValueError("archival reference export registry modified")
    if len(doc["upstream_real_git_tasks"]) != 2 or [
            t["id"] for t in doc["upstream_real_git_tasks"]] != [
                "youtube-dl-27", "youtube-dl-43"]:
        raise ValueError("unregistered replay task")
    return doc, hashlib.sha256(raw).hexdigest()


def archived(task_id: str):
    doc, _ = frozen()
    task = next((t for t in doc["upstream_real_git_tasks"]
                 if t["id"] == task_id), None)
    if task is None:
        raise ValueError("task not in frozen replay")
    path = ROOT / task["pair_path"]
    if path.parent.resolve() != EVIDENCE.resolve():
        raise ValueError("unsafe registered pair path")
    if _sha(path) != task["pair_sha256"]:
        raise ValueError("previous model-generated trial was altered")
    pair = json.loads(path.read_bytes())
    if pair["task_id"] != task_id or not pair["preexisting_historical_benchmark"]:
        raise ValueError("wrong archival experiment")
    idx = json.loads(INDEX.read_bytes())
    refs = {s["session_id"]: s for s in idx["files"]}
    states = {}
    for arm in ("depth", "adaptive"):
        sid = pair["results"][arm]["session_id"]
        if sid not in refs or refs[sid]["role"] != "codex_model_trial":
            raise ValueError("archival source lacks original authenticated model provenance")
        record = next((x for x in refs[sid]["files"]
                       if x["path"].endswith("/state.json")), None)
        if not record:
            raise ValueError("missing original state")
        state_file = ROOT / record["path"]
        if _sha(state_file) != record["sha256"]:
            raise ValueError("archival model source checksum mismatch")
        state = json.loads(state_file.read_bytes())
        if state["task_id"] != task_id or state["policy"] != arm:
            raise ValueError("archived state/task mismatch")
        if len(state["attempts"]) != pair["results"][arm]["attempt_count"]:
            raise ValueError("archival number of attempts changed")
        for a in state["attempts"]:
            if (not a["actual_git_apply_verified"]
                    or hashlib.sha256(a["source"].encode()).hexdigest()
                    != a["source_sha256"]):
                raise ValueError("original model attempt source was not validated")
        states[arm] = state
    n = task["shared_original_attempts"]
    for i in range(n):
        for key in ("source_sha256", "prompt_sha256", "patch_sha256"):
            if states["depth"]["attempts"][i][key] != states["adaptive"]["attempts"][i][key]:
                raise ValueError("archival prefix not identical")
        left = json.loads(json.dumps(states["depth"]["attempts"][i]["public"]))
        right = json.loads(json.dumps(states["adaptive"]["attempts"][i]["public"]))
        # unittest reports variable "Ran N tests in 0.00Xs" durations in
        # stderr; hash differences can arise even when assertions, statuses,
        # diagnostics and exit codes are identical. Compare all those stable
        # properties, not presentation-level elapsed time or raw stderr hash.
        for verdict in (left, right):
            verdict.pop("elapsed_seconds", None)
            for check in verdict.get("checks", []):
                check.pop("stderr_sha256", None)
        if left != right:
            raise ValueError("archival public result or diagnostic differs")
    return task, pair, states


def _public_equal(actual, archived_verdict):
    # Verify real Docker outcome equivalence. Timings/checksums are expected
    # to vary across Docker runs, so don't demand byte-identical traceback.
    return (actual["status"] == archived_verdict["status"]
            and actual["passed"] == archived_verdict["passed"])


def condition(task_id: str, mode: str):
    if mode not in ("ordinary", "shared"):
        raise ValueError("unknown comparison condition")
    task, pair, archived_states = archived(task_id)
    streams = {
        arm: wf.start(task_id=task_id, policy=arm, budget=4,
                      driver="relai-supervised", enriched_feedback=True, approve=True)
        for arm in ("depth", "adaptive")
    }
    start = time.monotonic()
    transcript = []
    while any(v["agent_required"] for v in streams.values()):
        a, b = streams["depth"], streams["adaptive"]
        equivalent = (a["agent_required"] and b["agent_required"]
                      and a["request"] == b["request"]
                      and a["prompt_sha256"] == b["prompt_sha256"])
        if mode == "shared" and equivalent:
            # Only the source session genuinely executes Git + Docker. A
            # cryptographically matched host-owned receipt is transferred.
            current = a
            index = current["previous_attempt_count"]
            source = archived_states["depth"]["attempts"][index]["source"]
            response = wf.submit(current["session_id"], source, approve=True,
                                 agent_label="archived-model-replay-no-inference")
            new_a = response["next"]
            inherited = wf.share_attempt(b["session_id"], a["session_id"], approve=True)
            new_b = inherited["next"]
            for arm, target in (("depth", new_a), ("adaptive", new_b)):
                state = wf._read(target["session_id"])[1]["attempts"][-1]
                prior = archived_states[arm]["attempts"][index]
                if (not _public_equal(state["public"], prior["public"])
                        or state["source_sha256"] != prior["source_sha256"]):
                    raise RuntimeError("current Docker public result differs from archived grade")
                transcript.append({
                    "arm": arm, "attempt_id": state["id"],
                    "kind":state["kind"],"public_status":state["public"]["status"],
                    "source_sha256":state["source_sha256"],
                    "patch_sha256":state["patch_sha256"],
                    "reused_verified_public":bool(state.get("reused_public_from_session_id")),
                    "actual_public_evaluator_calls":state["public_evaluator_invocations"],
                    "actual_git_apply_calls":state["git_apply_invocations"],
                })
            streams["depth"], streams["adaptive"] = new_a, new_b
        else:
            for arm in ("depth", "adaptive"):
                req = streams[arm]
                if not req["agent_required"]:
                    continue
                index = req["previous_attempt_count"]
                reference = archived_states[arm]["attempts"][index]
                if req["request"] != {
                        "kind": reference["kind"],
                        "parent_attempt_id": reference["parent_attempt_id"]}:
                    raise RuntimeError("replay policy no longer follows the original decision")
                if req["prompt_sha256"] != reference["prompt_sha256"]:
                    raise RuntimeError("replay prompt changed versus frozen evidence")
                response = wf.submit(req["session_id"], reference["source"], approve=True,
                                     agent_label="archived-model-replay-no-inference")
                after = wf._read(req["session_id"])[1]["attempts"][-1]
                if (not _public_equal(after["public"], reference["public"])
                        or after["source_sha256"] != reference["source_sha256"]):
                    raise RuntimeError("new Docker result differs from historic grade")
                transcript.append({
                    "arm":arm,"attempt_id":after["id"],
                    "kind":after["kind"],"public_status":after["public"]["status"],
                    "source_sha256":after["source_sha256"],
                    "patch_sha256":after["patch_sha256"],
                    "reused_verified_public":False,
                    "actual_public_evaluator_calls":after["public_evaluator_invocations"],
                    "actual_git_apply_calls":after["git_apply_invocations"],
                })
                streams[arm] = response["next"]
    # All model output is from archived states. No new Codex or other model.
    outcome = {arm: wf.finalize(streams[arm]["session_id"], approve=True)
               for arm in ("depth", "adaptive")}
    elapsed = round(time.monotonic() - start, 4)
    if any(outcome[arm]["full_success"] != task["reference_hidden_result"][arm]
           for arm in ("depth", "adaptive")):
        raise RuntimeError("held-out final correctness changed between conditions")
    return {
        "mode":mode, "wall_seconds":elapsed, "new_model_proposal_calls":0,
        "actual_git_apply_calls":sum(x["actual_git_apply_calls"] for x in transcript),
        "actual_public_evaluator_calls":sum(x["actual_public_evaluator_calls"]
                                            for x in transcript),
        "reused_receipts":sum(x["reused_verified_public"] for x in transcript),
        "candidate_instances":len(transcript),
        "outcomes":outcome,"attempts":transcript,
    }


def run_task(task_id: str, *, approve=False):
    if approve is not True:
        raise ValueError("explicit source replay and Docker execution approval required")
    doc, protocol_sha = frozen()
    task = next((t for t in doc["upstream_real_git_tasks"] if t["id"] == task_id), None)
    if task is None:
        raise ValueError("unregistered task")
    out_file = EVIDENCE / ("v23_reuse_" + task_id.replace("-", "_") + ".json")
    if out_file.exists():
        raise ValueError("refusing to overwrite measured work")
    raw = {
        "schema":"nykra-v23-real-git-docker-duplicate-evaluation-reduction-v1",
        "task_id":task_id,"protocol_sha256":protocol_sha,
        "status":"running","conditions":{},
        "historical_reuse":True,"new_model_inference":False,
    }
    for mode in task["condition_order"]:
        raw["conditions"][mode] = condition(task_id, mode)
        # Checkpoint after a completed condition, but don't expose an
        # incomplete report as the immutable final experiment.
        temp = out_file.with_suffix(".partial.json")
        temp.write_text(json.dumps(raw,indent=2)+"\n",encoding="utf-8")
    plain, shared = raw["conditions"]["ordinary"], raw["conditions"]["shared"]
    for arm in ("depth", "adaptive"):
        a,b = plain["outcomes"][arm],shared["outcomes"][arm]
        if (a["full_success"]!=b["full_success"] or
                [z["status"] for z in a["ancestry"]] !=
                [z["status"] for z in b["ancestry"]]):
            raise RuntimeError("cache changes public or hidden correctness")
    if shared["actual_public_evaluator_calls"] > plain["actual_public_evaluator_calls"]:
        raise RuntimeError("public-cache regression")
    raw["status"] = "completed"
    out_file.write_text(json.dumps(raw,indent=2)+"\n",encoding="utf-8")
    out_file.with_suffix(".partial.json").unlink(missing_ok=True)
    return raw
