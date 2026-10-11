"""Policy controller tests independent of a model or Rel.AI workspace."""
import math
import unittest

from nykra.exploration_policy import POLICIES, select_next
from nykra.iterative import IterativeCoding


def step(id_, index, score, parent=None):
    return {"id": id_, "position": index, "score": score, "parent_id": parent}


class PolicyTests(unittest.TestCase):
    def next(self, mode, steps, *, budget=6, threshold=1.):
        return select_next(policy=mode, steps=steps, budget=budget,
                           threshold=threshold)

    def test_independent_initial_root(self):
        for policy in POLICIES:
            with self.subTest(policy=policy):
                expected = {"kind": "new_root", "parent_attempt_id": None}
                self.assertEqual(self.next(policy, []), expected)
                self.assertEqual(IterativeCoding._select(
                    {"budget": 6, "threshold": 1., "policy": policy}, []), expected)

    def test_breadth_uses_two_roots_then_shallower_less_explored_parent(self):
        one = [step("a", 0, .25)]
        self.assertEqual(self.next("breadth", one)["kind"], "new_root")
        two = one + [step("b", 1, .4)]
        self.assertEqual(self.next("breadth", two)["parent_attempt_id"], "a")
        three = two + [step("c", 2, .55, "a")]
        self.assertEqual(self.next("breadth", three)["parent_attempt_id"], "b")
        four = three + [step("d", 3, .55, "b")]
        self.assertEqual(self.next("breadth", four)["parent_attempt_id"], "a")

    def test_depth_uses_most_recent_attempt(self):
        history = [step("a", 0, .4), step("b", 1, .6, "a"),
                   step("c", 2, .2, "a")]
        self.assertEqual(self.next("depth", history)["parent_attempt_id"], "c")

    def test_adaptive_selects_high_score_until_stagnation(self):
        history = [step("a", 0, .6), step("b", 1, .5, "a")]
        self.assertEqual(self.next("adaptive", history)["parent_attempt_id"], "a")
        history.append(step("c", 2, .5, "b"))
        self.assertEqual(self.next("adaptive", history)["kind"], "new_root")
        history.append(step("d", 3, .75))
        self.assertEqual(self.next("adaptive", history)["parent_attempt_id"], "d")

    def test_stop_on_success_or_budget_and_tie_breaking(self):
        first = [step("a", 0, .9)]
        self.assertIsNone(self.next("adaptive", first, threshold=.8))
        self.assertIsNone(self.next("depth", first, budget=1))
        multiple = first + [step("b", 1, .9)]
        self.assertEqual(self.next("adaptive", multiple)["parent_attempt_id"], "b")

    def test_input_rejection(self):
        for policy, attempts, budget, threshold in (
            ("unknown", [], 4, 1.),
            ("depth", [], 0, 1.),
            ("depth", [], True, 1.),
            ("depth", [], 4, math.nan),
            ("depth", [step("a", 0, math.inf)], 4, 1.),
            ("depth", [step("a", 0, True)], 4, 1.),
            ("depth", [step("a", 1, .5)], 4, 1.),
            ("depth", [step("a", 0, .5), step("a", 1, .4)], 4, 1.),
            ("depth", [step("a", 0, .5, "future")], 4, 1.),
            ("depth", [step("a", 0, .4), step("b", 1, .4, "b")], 4, 1.),
        ):
            with self.subTest(policy=policy, attempts=attempts):
                with self.assertRaises(ValueError):
                    self.next(policy, attempts, budget=budget, threshold=threshold)


if __name__ == "__main__":
    unittest.main()
