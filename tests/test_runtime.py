import unittest

from sat_core.benchmark import run_graph_coloring_sweep
from sat_core.runtime import EVENT_CANCELLED, EVENT_PROGRESS, EVENT_ROW, RunEvent, RunToken
from sat_core.solver_runner import solve_clauses


class RuntimeTests(unittest.TestCase):
    def test_run_event_serializes(self):
        event = RunEvent(EVENT_PROGRESS, "halfway", current=1, total=2)
        data = event.as_dict()

        self.assertEqual(data["type"], EVENT_PROGRESS)
        self.assertEqual(data["message"], "halfway")
        self.assertEqual(data["current"], 1)
        self.assertEqual(data["total"], 2)
        self.assertIn("created_at", data)

    def test_benchmark_emits_row_and_progress_events(self):
        events = []

        rows = run_graph_coloring_sweep(
            [3],
            [0.2],
            [2],
            ["CDCL"],
            repeats=1,
            seed=1,
            event_callback=events.append,
        )

        self.assertEqual(len(rows), 1)
        self.assertTrue(any(event.type == EVENT_ROW for event in events))
        self.assertTrue(any(event.type == EVENT_PROGRESS for event in events))

    def test_exact_edge_benchmark_emits_rows(self):
        rows = run_graph_coloring_sweep(
            [4],
            None,
            [2],
            ["CDCL"],
            repeats=1,
            edge_counts=[3],
            generation_mode="exact_edges",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].generation_mode, "exact_edges")
        self.assertEqual(rows[0].edge_count, 3)

    def test_average_degree_benchmark_emits_rows(self):
        rows = run_graph_coloring_sweep(
            [4],
            None,
            [2],
            ["CDCL"],
            repeats=1,
            generation_mode="average_degree",
            average_degrees=[2],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].generation_mode, "average_degree")
        self.assertEqual(rows[0].edge_count, 4)

    def test_cancelled_benchmark_before_start_returns_no_rows(self):
        events = []
        token = RunToken()
        token.cancel()

        rows = run_graph_coloring_sweep(
            [3],
            [0.2],
            [2],
            ["CDCL"],
            repeats=1,
            event_callback=events.append,
            cancel_token=token,
        )

        self.assertEqual(rows, [])
        self.assertTrue(any(event.type == EVENT_CANCELLED for event in events))

    def test_cdcl_cancelled_before_start(self):
        token = RunToken()
        token.cancel()

        result = solve_clauses([[1]], "CDCL", cancel_token=token)

        self.assertEqual(result.status, "CANCELLED")

    def test_dpll_cancelled_before_start(self):
        token = RunToken()
        token.cancel()

        result = solve_clauses([[1]], "DPLL", cancel_token=token)

        self.assertEqual(result.status, "CANCELLED")


if __name__ == "__main__":
    unittest.main()
