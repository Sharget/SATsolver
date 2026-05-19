import unittest
import time
import tkinter as tk
import random

from app import BENCHMARK_PROBLEMS, PROBLEM_KINDS, SATApp, SUDOKU_SIZES
from problems.dimacs_problem import dimacs_problem_from_text
from problems.graph_coloring import (
    average_degree_graph_coloring_problem,
    edge_count_from_average_degree,
    exact_edges_graph_coloring_problem,
    manual_graph_coloring_problem,
    parse_edge_list,
    random_graph_coloring_problem,
)
from problems.hamiltonian_path import hamiltonian_var, manual_hamiltonian_path_problem
from problems.independent_set import independent_var, manual_independent_set_problem
from problems.n_queens import n_queens_problem, n_queens_var
from problems.sudoku import sudoku_problem, validate_sudoku_grid
from sat_core.benchmark import graph_coloring_sweep
from sat_core.dimacs import clauses_to_dimacs, parse_dimacs_text
from sat_core.models import BenchmarkRow
from sat_core.runtime import EVENT_LOG, RunEvent
from sat_core.solver_runner import solve_problem
from utils.general_utils import color_var, sudoku_var
from utils.colored_graph import decode_coloring, generate_random_graph_exact_edges, graph_edges


class AppBackendTests(unittest.TestCase):
    def test_dimacs_round_trip(self):
        clauses = [[1, -2], [2], [-1, 3]]
        text = clauses_to_dimacs(clauses, ["round trip"])

        self.assertEqual(parse_dimacs_text(text), clauses)

    def test_dimacs_problem_from_text(self):
        problem = dimacs_problem_from_text("p cnf 2 2\n1 2 0\n-1 0\n")

        self.assertEqual(problem.problem_type, "DIMACS")
        self.assertEqual(problem.clause_count, 2)

    def test_sudoku_problem_contains_given_and_decodes_solution(self):
        grid = [
            [1, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ]
        problem = sudoku_problem(grid)

        self.assertIn([sudoku_var(1, 1, 1)], problem.clauses)

        solved_grid = [
            [1, 2, 3, 4],
            [3, 4, 1, 2],
            [2, 1, 4, 3],
            [4, 3, 2, 1],
        ]
        solution = {
            sudoku_var(r + 1, c + 1, solved_grid[r][c]): True
            for r in range(4)
            for c in range(4)
        }

        self.assertEqual(problem.decode_solution(solution), solved_grid)

    def test_sudoku_25x25_is_supported_by_app_and_validator(self):
        self.assertIn(25, SUDOKU_SIZES)
        validate_sudoku_grid([[0] * 25 for _ in range(25)])

    def test_n_queens_problem_solves_and_decodes(self):
        problem = n_queens_problem(4)

        self.assertIn([n_queens_var(1, 1, 4), n_queens_var(1, 2, 4), n_queens_var(1, 3, 4), n_queens_var(1, 4, 4)], problem.clauses)

        result = solve_problem(problem, "CDCL")

        self.assertEqual(result.status, "SAT")
        self.assertEqual(len(result.decoded["positions"]), 4)
        self.assertEqual(len(result.decoded["board"]), 4)

    def test_hamiltonian_path_problem_sat_and_unsat(self):
        sat_problem = manual_hamiltonian_path_problem(3, "1-2, 2-3")
        unsat_problem = manual_hamiltonian_path_problem(3, "1-2")

        self.assertIn([hamiltonian_var(1, 1, 3), hamiltonian_var(1, 2, 3), hamiltonian_var(1, 3, 3)], sat_problem.clauses)
        self.assertEqual(solve_problem(sat_problem, "CDCL").status, "SAT")
        self.assertEqual(solve_problem(unsat_problem, "CDCL").status, "UNSAT")

    def test_independent_set_problem_sat_and_unsat(self):
        sat_problem = manual_independent_set_problem(3, 2, "1-2")
        unsat_problem = manual_independent_set_problem(3, 2, "1-2, 1-3, 2-3")

        self.assertIn([independent_var(1, 1, 3), independent_var(1, 2, 3), independent_var(1, 3, 3)], sat_problem.clauses)
        self.assertEqual(solve_problem(sat_problem, "CDCL").status, "SAT")
        self.assertEqual(solve_problem(unsat_problem, "CDCL").status, "UNSAT")

    def test_graph_coloring_manual_encoder(self):
        problem = manual_graph_coloring_problem(2, 2, "1-2")

        self.assertIn([-color_var(1, 1, 2), -color_var(2, 1, 2)], problem.clauses)
        self.assertIn([-color_var(1, 2, 2), -color_var(2, 2, 2)], problem.clauses)

    def test_graph_edge_parser_accepts_commas_and_lines(self):
        self.assertEqual(parse_edge_list("1-2, 2-3\n3-4"), [(1, 2), (2, 3), (3, 4)])

    def test_solver_wrapper_returns_stats(self):
        problem = dimacs_problem_from_text("p cnf 1 1\n1 0\n")
        result = solve_problem(problem, "CDCL")

        self.assertEqual(result.status, "SAT")
        self.assertIn("decisions", result.stats)

    def test_tiny_benchmark_sweep_rows(self):
        rows = graph_coloring_sweep([3], [0.2], [2], ["CDCL"], repeats=1, seed=7)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].problem_type, "Graph Coloring")
        self.assertEqual(rows[0].solver, "CDCL")

    def test_random_graph_problem_is_buildable(self):
        problem = random_graph_coloring_problem(4, 0.5, 3, seed=1)

        self.assertEqual(problem.problem_type, "Graph Coloring")
        self.assertGreater(problem.clause_count, 0)
        self.assertEqual(problem.metadata["mode"], "probability")

    def test_exact_edge_graph_has_requested_edges(self):
        graph = generate_random_graph_exact_edges(6, 7, rng=random.Random(3))
        edges = graph_edges(graph)

        self.assertEqual(len(edges), 7)
        self.assertEqual(len(edges), len(set(edges)))
        self.assertTrue(all(u != v for u, v in edges))

    def test_exact_edge_graph_seed_is_reproducible(self):
        first = exact_edges_graph_coloring_problem(6, 7, 3, seed=11)
        second = exact_edges_graph_coloring_problem(6, 7, 3, seed=11)

        self.assertEqual(first.clauses, second.clauses)
        self.assertEqual(first.metadata["edges"], 7)
        self.assertEqual(first.metadata["mode"], "exact_edges")

    def test_exact_edge_count_above_complete_graph_saturates(self):
        problem = exact_edges_graph_coloring_problem(4, 100, 3)

        self.assertEqual(problem.metadata["edges"], 6)
        self.assertEqual(problem.metadata["requested_edges"], 100)
        self.assertTrue(problem.metadata["edge_request_clamped"])

    def test_negative_exact_edge_count_raises(self):
        with self.assertRaises(ValueError):
            exact_edges_graph_coloring_problem(4, -1, 3)

    def test_average_degree_edge_conversion(self):
        self.assertEqual(edge_count_from_average_degree(10, 4), 20)
        self.assertEqual(edge_count_from_average_degree(10, 0), 0)
        self.assertEqual(edge_count_from_average_degree(4, 20), 6)

    def test_negative_average_degree_raises(self):
        with self.assertRaises(ValueError):
            edge_count_from_average_degree(10, -1)

    def test_average_degree_graph_problem_metadata_and_seed(self):
        first = average_degree_graph_coloring_problem(10, 4, 3, seed=5)
        second = average_degree_graph_coloring_problem(10, 4, 3, seed=5)

        self.assertEqual(first.clauses, second.clauses)
        self.assertEqual(first.metadata["mode"], "average_degree")
        self.assertEqual(first.metadata["average_degree"], 4)
        self.assertEqual(first.metadata["requested_edges"], 20)
        self.assertEqual(first.metadata["edges"], 20)
        self.assertFalse(first.metadata["edge_request_clamped"])

    def test_average_degree_graph_above_complete_graph_saturates(self):
        problem = average_degree_graph_coloring_problem(4, 20, 3)

        self.assertEqual(problem.metadata["edges"], 6)
        self.assertEqual(problem.metadata["requested_edges"], 40)
        self.assertTrue(problem.metadata["edge_request_clamped"])

    def test_compact_color_encoding_does_not_collide(self):
        colors = 101
        seen = {
            color_var(node, color, colors)
            for node in range(1, 4)
            for color in range(1, colors + 1)
        }

        self.assertEqual(len(seen), 3 * colors)

    def test_decode_coloring_with_compact_encoding(self):
        solution = {
            color_var(1, 2, 3): True,
            color_var(2, 1, 3): True,
            color_var(3, 3, 3): True,
        }

        self.assertEqual(decode_coloring(solution, 3), {1: 2, 2: 1, 3: 3})

    def test_app_can_be_instantiated(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            self.assertIsNone(app.current_problem)
            self.assertEqual(app.solve_timeout_seconds.get(), "30")
            self.assertEqual(app.bench_timeout_seconds.get(), "30")
            self.assertEqual(app._benchmark_bar_color("TIMEOUT"), "#f58518")
            self.assertEqual(app._benchmark_bar_color("SKIPPED"), "#bab0ab")
            row = BenchmarkRow(
                case_name="Hamiltonian Path n10_p30",
                problem_type="Hamiltonian Path",
                solver="CDCL",
                status="SAT",
                elapsed=0.1,
                clauses=1,
                variables=1,
                repeat=1,
            )
            self.assertEqual(app._benchmark_chart_label(row), "n10_p30\nCDCL")
            app.benchmark_rows = [row]
            self.assertEqual(app._benchmark_chart_title("Raw Time"), "Hamiltonian Path - Raw Time")
            self.assertIn("N-Queens", PROBLEM_KINDS)
            self.assertIn("Hamiltonian Path", PROBLEM_KINDS)
            self.assertIn("Independent Set", PROBLEM_KINDS)
            self.assertIn("N-Queens", BENCHMARK_PROBLEMS)

            self.assertEqual(app.problem_description.get(), "Fill an n x n grid so each row, column, and square box contains every value exactly once.")
            self.assertEqual(str(app.solver_log_box.cget("state")), "disabled")
            app.advanced_solver_logs.set(True)
            app._refresh_solver_log_controls()
            self.assertEqual(str(app.solver_log_box.cget("state")), "readonly")

            app.problem_kind.set("Graph Coloring")
            app._refresh_problem_form()
            self.assertEqual(str(app.graph_field_entries["probability"].cget("state")), "disabled")
            self.assertEqual(str(app.edge_text.cget("state")), "normal")
            app.graph_mode.set("Average degree")
            app._refresh_graph_controls()
            self.assertEqual(str(app.graph_field_entries["average_degree"].cget("state")), "normal")
            self.assertEqual(str(app.graph_field_entries["probability"].cget("state")), "disabled")
            self.assertEqual(str(app.edge_text.cget("state")), "disabled")

            app.bench_problem.set("Sudoku")
            app._refresh_benchmark_form()
            self.assertEqual(app._selected_sudoku_benchmark_sizes(), [4, 9])
            self.assertEqual(str(app.skip_benchmark_button.cget("state")), "disabled")
            app.active_process_skip = object()
            app._set_run_active(True, "Benchmarking")
            self.assertEqual(str(app.skip_benchmark_button.cget("state")), "normal")
            app._set_run_active(False)
            app.active_process_skip = None
            app._refresh_skip_button_state()
            self.assertEqual(str(app.skip_benchmark_button.cget("state")), "disabled")
            self.assertFalse(app.bench_sudoku_size_vars[16].get())
            self.assertFalse(app.bench_sudoku_size_vars[25].get())
            self.assertEqual(str(app.bench_log_box.cget("state")), "disabled")
            app.bench_advanced_solver_logs.set(True)
            app._refresh_benchmark_log_controls()
            self.assertEqual(str(app.bench_log_box.cget("state")), "readonly")
            app.bench_problem.set("Hamiltonian Path")
            app._refresh_benchmark_form()
            self.assertEqual(set(app.bench_graph_mode_buttons), {"Probability", "Exact edges", "Average degree"})
            self.assertEqual(str(app.bench_graph_mode_buttons["Probability"].cget("text")), "G(n,p)")
            self.assertEqual(str(app.bench_graph_mode_buttons["Exact edges"].cget("text")), "G(n,m)")
            self.assertEqual(str(app.bench_graph_mode_buttons["Average degree"].cget("text")), "G(n,d)")
            self.assertEqual(str(app.bench_graph_field_entries["probabilities"].cget("state")), "normal")
            app.bench_generation_mode.set("Exact edges")
            app._refresh_benchmark_graph_controls()
            self.assertEqual(str(app.bench_graph_field_entries["edge_counts"].cget("state")), "normal")
            self.assertEqual(str(app.bench_graph_field_entries["probabilities"].cget("state")), "disabled")
        finally:
            root.destroy()

    def test_app_worker_feed_events_are_processed(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)

            def worker(_token, event_callback):
                event_callback(RunEvent(EVENT_LOG, "background hello"))

            app._start_worker("Tiny worker", worker)
            time.sleep(0.05)
            app._poll_run_events()

            feed = app.feed_text.get("1.0", tk.END)
            self.assertIn("background hello", feed)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
