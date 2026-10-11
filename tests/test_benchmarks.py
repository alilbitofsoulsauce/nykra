"""Independent task generation, exact paired inference, honest evidence boundaries."""
import unittest
from unittest.mock import patch

from nykra.benchmarks import (
    _bootstrap_interval,
    _exact_discordance_test,
    _has_path,
    generate_tasks,
    paired_reference_benchmark,
)
from nykra.store import NykraError


class PairedBenchmarksTests(unittest.TestCase):
    def test_reproducible_unique_tasks_independent_of_policy(self):
        first=generate_tasks(count=32,seed=101)
        self.assertEqual(first,generate_tasks(count=32,seed=101))
        self.assertNotEqual(first,generate_tasks(count=32,seed=102))
        self.assertEqual(len(first),32)
        self.assertTrue(all(_has_path(board) for board in first))
        self.assertEqual(len({str(board) for board in first}),32)

    def test_exact_discordance_and_bootstrap(self):
        self.assertEqual(_exact_discordance_test(0,0),1.0)
        self.assertEqual(_exact_discordance_test(5,0),1/32)
        self.assertEqual(_exact_discordance_test(29,0),2**-29)
        self.assertGreater(_exact_discordance_test(29,0),0)
        self.assertEqual(_exact_discordance_test(0,5),1.0)
        self.assertEqual(_bootstrap_interval([0,0,0],seed=7),[0,0])
        self.assertEqual(_bootstrap_interval([1,1,1],seed=7),[1,1])

    def test_approval_and_validations(self):
        with self.assertRaises(NykraError):
            paired_reference_benchmark(count=20,budget=8)
        with self.assertRaises(NykraError):
            generate_tasks(count=19,seed=1)
        with self.assertRaises(NykraError):
            paired_reference_benchmark(count=20,budget=0,approval=True)

    def test_fresh_runtime_comparison_same_tasks_and_budget(self):
        result=paired_reference_benchmark(count=20,budget=12,seed=73,approval=True)
        self.assertEqual(result["sample"],20)
        self.assertEqual(result["attempt_budget_per_arm"],12)
        self.assertEqual(result["baseline"],"breadth")
        self.assertEqual(result["challenger"],"adaptive")
        s=result["results"]
        self.assertEqual(s["baseline_successes"]+s["challenger_only_succeeds"]+s["neither_succeeds"],20)
        self.assertEqual(s["both_succeed"]+s["baseline_only_succeeds"]+
                         s["challenger_only_succeeds"]+s["neither_succeeds"],20)
        self.assertGreaterEqual(s["paired_one_sided_exact_p"],0)
        self.assertLessEqual(s["paired_one_sided_exact_p"],1)
        self.assertFalse(result["limits"]["general_agent_improvement_proven"])
        self.assertFalse(result["limits"]["recursive_self_improvement_proven"])


if __name__=="__main__":
    unittest.main()
