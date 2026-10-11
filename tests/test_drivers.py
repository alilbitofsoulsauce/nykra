"""A native adapter contract that does not depend on Rel.AI Core imports."""
import tempfile
import unittest
from unittest.mock import patch

from nykra.drivers import AgentDriver, get_driver, scan_drivers
from nykra.store import HistoryStore, NykraError

INCORRECT="def solve(values):\n    return sorted(values)\n"
CORRECT="def solve(values):\n    return sorted(set(values))\n"

class DriverContractTests(unittest.TestCase):
    def test_discovery_does_not_claim_unverified_vendor_support(self):
        with patch("nykra.drivers.shutil.which",side_effect=lambda cmd: (
                "C:/tools/"+cmd if cmd in ("codex","opencode") else None)):
            scan=scan_drivers(relai_database_detected=True)
        self.assertEqual(scan["core"],"agent_independent")
        kinds={item["id"]:item for item in scan["drivers"]}
        self.assertEqual(kinds["relai"]["integration_level"],"supervised")
        self.assertFalse(kinds["relai"]["autonomous_generation"])
        for name in ("codex","opencode"):
            self.assertTrue(kinds[name]["detected"])
            self.assertEqual(kinds[name]["implementation"],"discovery_only")
            self.assertEqual(kinds[name]["integration_level"],"none")
            self.assertFalse(kinds[name]["auto_policy_application"])

    def test_missing_relai_history_not_claimed_connected(self):
        scan=scan_drivers(relai_database_detected=False)
        relai=next(item for item in scan["drivers"] if item["id"]=="relai")
        self.assertFalse(relai["detected"])
        self.assertFalse(relai["observation"])

    def test_unsupported_driver_refused_without_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            store=HistoryStore(directory)
            for name in ("codex","opencode","claude","other"):
                with self.assertRaises(NykraError):
                    get_driver(name,store)
            self.assertEqual(store.stats()["attempt_count"],0)

    def test_relai_implements_portable_contract_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            store=HistoryStore(directory)
            adapter=get_driver("relai",store)
            self.assertTrue(isinstance(adapter,AgentDriver))
            result=adapter.start(task_id="unique-sorted",budget=2,
                                 policy="depth",max_seconds=120,approval=True)
            sid=result["session"]["session_id"]
            result=adapter.submit(sid,source=INCORRECT,approval=True)
            self.assertEqual(result["state"],"awaiting_agent")
            self.assertEqual(adapter.next(sid)["request"]["kind"],"revise")
            final=adapter.submit(sid,source=CORRECT,approval=True)
            self.assertEqual(final["heldout_score"],1.0)
            self.assertFalse(final["model_invocation"])
