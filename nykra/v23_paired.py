"""Live provider-neutral paired workflow with safe verified public-test reuse.

The caller supplies a proposal callback (for example a connected ChatGPT
agent supervised through Rel.AI). This module NEVER starts Codex, uses an
API key, connects to an LLM API, or invents a Rel.AI inference endpoint.

Only a proposal present in the same exact prompt/parent/evaluator context
is graded once. The second branch inherits its authenticated local receipt;
if policies diverge, each branch gets a separate proposal and public grade.
Hidden tests remain independent and run after all proposal callbacks.
"""
from __future__ import annotations
import hashlib

from . import agent_workflow as wf


def run_pair(task_id, propose, *, budget=4, approve=False,
             policies=("depth", "adaptive"), enriched_feedback=True):
    if approve is not True:
        raise ValueError("explicit approval required")
    if not callable(propose):
        raise ValueError("a connected proposal callback must be supplied")
    if policies != ("depth", "adaptive"):
        raise ValueError("only registered depth/adaptive pair supported")
    flows = {
        arm: wf.start(task_id=task_id, policy=arm, budget=budget,
                      driver="relai-supervised", enriched_feedback=enriched_feedback,
                      approve=True)
        for arm in policies
    }
    generated = []
    fork = None
    while any(x["agent_required"] for x in flows.values()):
        a, b = flows[policies[0]], flows[policies[1]]
        shareable = (a["agent_required"] and b["agent_required"]
                     and a["prompt_sha256"] == b["prompt_sha256"]
                     and a["request"] == b["request"])
        if shareable:
            proposal = propose(a["prompt"])
            if not isinstance(proposal, str):
                raise ValueError("proposal provider must return a single source string")
            generated.append({"mode":"shared",
                              "source_sha256":hashlib.sha256(proposal.encode()).hexdigest()})
            result = wf.submit(a["session_id"], proposal, approve=True,
                               agent_label="connected-chatgpt-relai")
            flows[policies[0]] = result["next"]
            # If public evaluation itself failed due to infrastructure or
            # invalid source, do not synthesize a receipt; the workflow
            # retains the true failure and halts as appropriate.
            verdict = result["evaluated"]["public"]
            if verdict["status"] in ("ok","test_failed") and result["evaluated"]["actual_git_apply_verified"]:
                reused = wf.share_attempt(b["session_id"], a["session_id"], approve=True)
                flows[policies[1]] = reused["next"]
            else:
                outcome = wf.submit(b["session_id"], proposal, approve=True,
                                    agent_label="connected-chatgpt-relai-repeat")
                flows[policies[1]] = outcome["next"]
        else:
            if fork is None and a["agent_required"] and b["agent_required"]:
                fork = {"depth":a["request"],"adaptive":b["request"]}
            for arm in policies:
                request = flows[arm]
                if not request["agent_required"]:
                    continue
                source = propose(request["prompt"])
                if not isinstance(source,str):
                    raise ValueError("proposal callback must return a source string")
                generated.append({"mode":arm,"source_sha256":hashlib.sha256(source.encode()).hexdigest()})
                response = wf.submit(request["session_id"],source,approve=True,
                                     agent_label="connected-chatgpt-relai")
                flows[arm] = response["next"]
    results = {arm:wf.finalize(flows[arm]["session_id"],approve=True)
               for arm in policies}
    return {
        "schema":"nykra-v23-connected-provider-shared-public-receipts-v1",
        "task_id":task_id,"provider":"callback-supplied-by-chatgpt-relai-host",
        "model_proposal_invocations":len(generated),
        "generated":generated,"policy_divergence":fork,
        "requested_candidate_instances":sum(x["attempt_count"] for x in results.values()),
        "real_public_docker_runs":sum(x["actual_public_evaluator_calls"]
                                       for x in results.values()),
        "verified_public_reuse":sum(x["verified_public_reuse_hits"]
                                    for x in results.values()),
        "real_git_apply_calls":sum(x["actual_git_apply_calls"]
                                   for x in results.values()),
        "final":results,"independent_hidden":True,
        "general_coding_quality_gain_proven":False,
        "note":"Real pinned single-function upstream Git repair; not arbitrary multi-file editing or independent LLM hosting."
    }
