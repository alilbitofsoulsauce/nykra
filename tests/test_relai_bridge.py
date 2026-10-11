import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from nykra.server import create_server
from nykra.store import HistoryStore


class TransparentRelaiBridgeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required for Rel.AI bridge tests")
    def test_real_node_bridge_to_local_server_without_agent_tool_calls(self):
        import threading
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(directory)
            token = store.token()
            self.assertTrue(token)
            server = create_server(store, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

            script = r"""
import { attachRelaiBridge, normalizeActivity } from './integrations/relai/bridge.mjs';
const listeners = new Set();
const onToolActivity = fn => { listeners.add(fn); return () => listeners.delete(fn); };
const observer = attachRelaiBridge(onToolActivity);
const emit = event => { for (const listener of listeners) listener(event); };
const originalToolReturn = { ok: true, value: 777 };
emit({ phase: 'progress', operationId: 'op-progress', tool: 'relai_exec' });
emit({
  phase: 'finished', operationId: 'op-synthetic-1', tool: 'relai_exec',
  taskId: 'task-123', ok: true, durationMs: 12,
  activityEvent: { status: 'succeeded', stdout: 'SECRET_OUTPUT', command: 'PRIVATE_COMMAND' },
  input: { prompt: 'PRIVATE_PROMPT', password: 'PRIVATE_PASSWORD' },
  result: originalToolReturn
});
emit({
  phase: 'finished', operationId: 'op-synthetic-1', tool: 'relai_exec',
  taskId: 'task-123', ok: true, durationMs: 12
});
emit({
  phase: 'finished', operationId: 'op-synthetic-2', tool: 'relai_validate',
  taskId: 'task-123', ok: false, durationMs: 4, activityEvent: { status: 'blocked' }
});
await observer.flush();
if (observer.stats.delivered !== 3 || observer.stats.ignored !== 1) {
  throw Error('unexpected observer state ' + JSON.stringify(observer.stats));
}
if (originalToolReturn.value !== 777) throw Error('tool return mutated');
await observer.close();
console.log(JSON.stringify(observer.stats));
"""
            env = os.environ.copy()
            env["NYKRA_HOME"] = directory
            env["NYKRA_PORT"] = str(server.server_port)
            process = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                capture_output=True, text=True, timeout=20, env=env,
                cwd=Path(__file__).resolve().parents[1])
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(result["dropped"], 0)
            events = store.list_activity(source="relai")
            self.assertEqual(len(events), 2)
            self.assertEqual({item["outcome"] for item in events}, {"succeeded", "denied"})
            self.assertEqual(store.stats()["attempt_count"], 0)
            self.assertNotIn("SECRET", json.dumps(events))
            self.assertNotIn("PRIVATE", json.dumps(events))

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for Rel.AI bridge tests")
    def test_nykra_absence_does_not_break_agent_execution(self):
        script = r"""
import { attachRelaiBridge } from './integrations/relai/bridge.mjs';
const listeners = [];
const observer = attachRelaiBridge(fn => { listeners.push(fn); }, { port: 1, timeoutMs: 100 });
const start = performance.now();
listeners[0]({ phase: 'finished', operationId: 'offline-1', tool: 'relai_exec', durationMs: 1, ok: true });
if (performance.now() - start > 1000) throw new Error('host blocked on Nykra');
await observer.flush();
if (observer.stats.dropped !== 1) throw new Error('missing dropped signal');
console.log('fail-open');
"""
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env["NYKRA_HOME"] = directory
            result = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                capture_output=True, text=True, timeout=10, env=env,
                cwd=Path(__file__).resolve().parents[1])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("fail-open", result.stdout)


if __name__ == "__main__":
    unittest.main()
