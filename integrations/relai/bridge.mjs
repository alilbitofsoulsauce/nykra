/**
 * Nykra's transparent Rel.AI activity bridge.
 *
 * One subscription to Rel.AI's existing onToolActivity(listener) hook.
 * No new MCP tools, no model API keys, no tool inputs/results/prompts forwarded.
 * Best-effort: the observer never delays or changes an agent's tool execution.
 */
import { readFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';

const VALID_ID = /^[A-Za-z0-9_./:@-]{1,256}$/;
const VALID_TOOL = /^[A-Za-z0-9_./:@-]{1,256}$/;

function nykraHome() {
  if (process.env.NYKRA_HOME) return process.env.NYKRA_HOME;
  if (process.platform === 'win32') {
    return join(process.env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local'), 'Nykra');
  }
  return join(process.env.XDG_STATE_HOME || join(homedir(), '.local', 'state'), 'nykra');
}

function normalizeActivity(snapshot) {
  if (!snapshot || snapshot.phase !== 'finished') return null;
  const tool = String(snapshot.tool || snapshot.activityEvent?.tool?.name || '');
  const operationId = String(snapshot.operationId || '');
  const task = String(snapshot.taskId || '');
  if (!VALID_TOOL.test(tool) || !VALID_ID.test(operationId)) return null;
  if (task && !VALID_ID.test(task)) return null;
  const duration = Number(snapshot.durationMs);
  if (!Number.isFinite(duration) || duration < 0) return null;
  const observed = String(snapshot.activityEvent?.status || '');
  let outcome;
  if (observed === 'cancelled') outcome = 'cancelled';
  else if (observed === 'blocked') outcome = 'denied';
  else if (observed === 'failed') outcome = 'failed';
  else outcome = snapshot.ok === false ? 'failed' : 'succeeded';
  return {
    event_id: 'relai-' + operationId,
    source: 'relai',
    tool,
    outcome,
    duration_ms: duration,
    ...(task ? { task_id: task } : {})
  };
}

/**
 * Attach once inside the host runtime where onToolActivity is already exported.
 * Only local loopback is supported; endpoint/port never comes from model content.
 *
 * @param {Function} onToolActivity - Rel.AI's existing listener registration
 * @param {object} options - optional local-only connection parameters for tests
 */
function attachRelaiBridge(onToolActivity, options = {}) {
  if (typeof onToolActivity !== 'function') throw new TypeError('onToolActivity callback required');
  const port = options.port ?? Number(process.env.NYKRA_PORT || 8765);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new RangeError('local port must be 1..65535');
  }
  const tokenPath = options.tokenPath ?? join(nykraHome(), 'auth.token');
  const timeoutMs = options.timeoutMs ?? 900;
  if (!Number.isInteger(timeoutMs) || timeoutMs < 50 || timeoutMs > 10000) {
    throw new RangeError('timeoutMs must be 50..10000');
  }
  const pending = new Set();
  const stats = { observed: 0, delivered: 0, dropped: 0, ignored: 0 };
  let closed = false;

  async function deliver(payload) {
    try {
      const token = (await readFile(tokenPath, 'utf8')).trim();
      if (!token) throw new Error('local token unavailable');
      const response = await fetch('http://127.0.0.1:' + port + '/v1/activity', {
        method: 'POST',
        redirect: 'manual',
        headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(timeoutMs)
      });
      if (!response.ok) throw new Error('local ingestion rejected event');
      stats.delivered += 1;
    } catch {
      // No logging: tool output, private paths and credentials must not leak.
      stats.dropped += 1;
    }
  }

  const unsubscribe = onToolActivity(snapshot => {
    if (closed) return;
    const payload = normalizeActivity(snapshot);
    if (!payload) {
      stats.ignored += 1;
      return;
    }
    stats.observed += 1;
    if (pending.size >= 64) {
      stats.dropped += 1;
      return;
    }
    const promise = deliver(payload);
    pending.add(promise);
    void promise.finally(() => pending.delete(promise));
  });

  return Object.freeze({
    stats,
    async flush() {
      await Promise.allSettled([...pending]);
    },
    async close() {
      closed = true;
      if (typeof unsubscribe === 'function') unsubscribe();
      await Promise.allSettled([...pending]);
    }
  });
}

export { attachRelaiBridge, normalizeActivity };
