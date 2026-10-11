# Rel.AI task instructions — Nykra feedback loop

Use **Rel.AI MCP tools on the nykra workspace**. These are instructions for an already-connected AI agent, not a self-starting model service.

Goal: complete the user's explicitly authorized bounded coding task **in one assistant turn** without requesting manual user assistance between safe candidate revisions.

1. Start a Nykra Rel.AI work session with this instruction file as the optional instructionPath; keep the same work_id throughout.
2. Run: python -m nykra relai-agent start --task TASK --policy POLICY --budget 4 --max-seconds 1200 --approve. Only use --approve when the user has authorized this execution task.
3. Interpret returned request kind. Write exactly one Python solve(...) function to a temporary workspace file via Rel.AI edit. The task and exposed parent_source are the only allowed task inputs. Do not inspect the held-out fixtures or read other users' files.
4. Run: python -m nykra relai-agent submit --session SESSION_ID --candidate-file CANDIDATE_FILE --approve.
5. If state is awaiting_agent, read the returned training feedback and next request. Revise the selected parent source when request kind is revise; generate an independent solution when new_root. Repeat steps 3-5 within the **same agent turn** until state is finished or a user-approved budget/timeout is exhausted.
6. On finished, report training progress, attempts, final held-out result and limited scope. On fatal error, explicitly abort if permitted; do not claim success.
7. Remove only the agent-owned temporary candidate file, never user files. Nykra automatically clears its own cached candidate source files on finish/abort.
8. Do not commit, push, install new packages, change Rel.AI MCP configuration, or contact paid model APIs unless the user separately approves.

Important: Rel.AI MCP provides tool execution but not a verified direct model-generation endpoint. The connected ChatGPT model supplies each candidate during the agent turn. This is NOT a background daemon autonomously invoking LLMs. Candidate evaluation uses a limited Python subprocess, **not** a hardened sandbox.
