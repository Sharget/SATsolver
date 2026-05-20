import unittest

from sat_core.runtime import RunToken
from sat_core.solver_runner import solve_clauses
from solvers.walksat import walksat


def satisfies(clauses, model):
    if model is None:
        return False

    for clause in clauses:
        if not any((lit > 0 and model.get(abs(lit))) or (lit < 0 and not model.get(abs(lit))) for lit in clause):
            return False
    return True


class WalkSATTests(unittest.TestCase):
    def test_walksat_finds_simple_sat_model(self):
        formula = [[1], [2, -1]]

        solution, stats = walksat(
            formula,
            return_stats=True,
            logging_options={"random_seed": 1, "max_tries": 5, "max_flips": 20},
        )

        self.assertEqual(stats["status"], "SAT")
        self.assertTrue(satisfies(formula, solution))

    def test_walksat_exhaustion_is_unknown_not_unsat(self):
        solution, stats = walksat(
            [[1], [-1]],
            return_stats=True,
            logging_options={"random_seed": 1, "max_tries": 1, "max_flips": 1},
        )

        self.assertIsNone(solution)
        self.assertEqual(stats["status"], "UNKNOWN")
        self.assertNotEqual(stats["status"], "UNSAT")

    def test_seeded_walksat_runs_are_reproducible(self):
        formula = [[1, 2], [-1, 2], [1, -2]]
        options = {"random_seed": 11, "max_tries": 3, "max_flips": 20, "noise": 0.4}

        first_solution, first_stats = walksat(formula, return_stats=True, logging_options=options)
        second_solution, second_stats = walksat(formula, return_stats=True, logging_options=options)

        self.assertEqual(first_stats["status"], second_stats["status"])
        self.assertEqual(first_stats["flips"], second_stats["flips"])
        self.assertEqual(first_solution, second_solution)

    def test_walksat_cancellation_and_timeout_statuses(self):
        cancelled = RunToken()
        cancelled.cancel()
        _solution, cancelled_stats = walksat([[1]], return_stats=True, cancel_token=cancelled)

        timed_out = RunToken(timeout_seconds=0)
        _solution, timeout_stats = walksat([[1]], return_stats=True, cancel_token=timed_out)

        self.assertEqual(cancelled_stats["status"], "CANCELLED")
        self.assertEqual(timeout_stats["status"], "TIMEOUT")

    def test_solver_runner_supports_walksat(self):
        result = solve_clauses([[1]], "WalkSAT", logging_options={"random_seed": 3})

        self.assertEqual(result.solver, "WalkSAT")
        self.assertEqual(result.status, "SAT")
        self.assertIn("flips", result.stats)

    def test_solver_runner_maps_walksat_specific_options(self):
        result = solve_clauses(
            [[1], [-1]],
            "WalkSAT",
            logging_options={
                "random_seed": 1,
                "walksat_random_seed": 9,
                "walksat_max_tries": 2,
                "walksat_max_flips": 3,
                "walksat_noise": 0.25,
            },
        )

        self.assertEqual(result.status, "UNKNOWN")
        self.assertIn("tries=2", result.stats["solver_options"])
        self.assertIn("flips=3", result.stats["solver_options"])
        self.assertIn("noise=0.25", result.stats["solver_options"])
        self.assertIn("seed=9", result.stats["solver_options"])


if __name__ == "__main__":
    unittest.main()
