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
from problems.hamiltonian_path import hamiltonian_var, manual_hamiltonian_path_problem, random_hamiltonian_path_problem
from problems.independent_set import independent_var, manual_independent_set_problem, random_independent_set_problem
from problems.n_queens import n_queens_problem, n_queens_var
from problems.sudoku import sudoku_problem, validate_sudoku_grid
from sat_core.benchmark import graph_coloring_sweep, result_to_row
from sat_core.dimacs import clauses_to_dimacs, parse_dimacs_text
from sat_core.models import BenchmarkRow, SolveResult
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

    def test_dimacs_problem_from_text_can_be_typed(self):
        problem = dimacs_problem_from_text("p cnf 2 1\n1 0\n", problem_type="Graph Coloring")

        self.assertEqual(problem.problem_type, "Graph Coloring")
        self.assertEqual(problem.metadata["loaded_as"], "Graph Coloring")

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

    def test_average_benchmark_groups_finished_repeats_only(self):
        app = SATApp.__new__(SATApp)
        rows = [
            BenchmarkRow("Graph Coloring n10_p30_k2", "Graph Coloring", "CDCL", "SAT", 1.0, 20, 10, 1, detail="probability, edges=8", conflicts=4, decisions=8, edge_count=8),
            BenchmarkRow("Graph Coloring n10_p30_k2", "Graph Coloring", "CDCL", "UNSAT", 3.0, 24, 10, 2, detail="probability, edges=10", conflicts=8, decisions=12, edge_count=10),
            BenchmarkRow("Graph Coloring n10_p30_k2", "Graph Coloring", "CDCL", "TIMEOUT", 30.0, 28, 10, 3, detail="probability, edges=12", edge_count=12),
            BenchmarkRow("Graph Coloring n10_p30_k2", "Graph Coloring", "CDCL", "SKIPPED", 0.0, 30, 10, 4, detail="probability, edges=13", edge_count=13),
        ]

        groups = app._aggregate_benchmark_rows(rows)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["status_counts"], {"SAT": 1, "UNSAT": 1, "TIMEOUT": 1, "SKIPPED": 1})
        self.assertAlmostEqual(app._benchmark_group_metric_value(groups[0], "Raw Time"), 2.0)
        self.assertAlmostEqual(app._benchmark_group_metric_value(groups[0], "Normalized Time"), 0.2)
        self.assertAlmostEqual(app._benchmark_group_metric_value(groups[0], "Conflicts"), 6.0)
        self.assertEqual(app._benchmark_status_count_label(groups[0]["status_counts"]), "S:1 U:1 T:1 K:1")

    def test_average_benchmark_separates_case_and_solver_groups(self):
        app = SATApp.__new__(SATApp)
        rows = [
            BenchmarkRow("Graph Coloring n10_p30_k2", "Graph Coloring", "CDCL", "SAT", 1.0, 20, 10, 1),
            BenchmarkRow("Graph Coloring n10_p30_k2", "Graph Coloring", "DPLL", "SAT", 2.0, 20, 10, 1),
            BenchmarkRow("Graph Coloring n20_p30_k2", "Graph Coloring", "CDCL", "SAT", 3.0, 40, 20, 1),
        ]

        groups = app._aggregate_benchmark_rows(rows)

        self.assertEqual(len(groups), 3)
        self.assertEqual([group["solver"] for group in groups], ["CDCL", "DPLL", "CDCL"])
        self.assertEqual([group["case_name"] for group in groups], [
            "Graph Coloring n10_p30_k2",
            "Graph Coloring n10_p30_k2",
            "Graph Coloring n20_p30_k2",
        ])

    def test_average_benchmark_five_random_repeats_make_one_case_group(self):
        app = SATApp.__new__(SATApp)
        rows = [
            BenchmarkRow("Graph Coloring n10_p10_k2", "Graph Coloring", "CDCL", "SAT", 0.1, 20, 10, 1, detail="probability, edges=3", edge_count=3),
            BenchmarkRow("Graph Coloring n10_p10_k2", "Graph Coloring", "CDCL", "SAT", 0.2, 24, 10, 2, detail="probability, edges=5", edge_count=5),
            BenchmarkRow("Graph Coloring n10_p10_k2", "Graph Coloring", "CDCL", "UNSAT", 0.3, 28, 10, 3, detail="probability, edges=7", edge_count=7),
            BenchmarkRow("Graph Coloring n10_p10_k2", "Graph Coloring", "CDCL", "UNSAT", 0.4, 30, 10, 4, detail="probability, edges=8", edge_count=8),
            BenchmarkRow("Graph Coloring n10_p10_k2", "Graph Coloring", "CDCL", "UNSAT", 0.5, 32, 10, 5, detail="probability, edges=9", edge_count=9),
            BenchmarkRow("Graph Coloring n10_p30_k2", "Graph Coloring", "CDCL", "UNSAT", 1.0, 40, 10, 1, detail="probability, edges=14", edge_count=14),
        ]

        groups = app._aggregate_benchmark_rows(rows)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["case_name"], "Graph Coloring n10_p10_k2")
        self.assertEqual(len(groups[0]["rows"]), 5)
        self.assertEqual(groups[0]["status_counts"], {"SAT": 2, "UNSAT": 3})
        self.assertAlmostEqual(app._benchmark_group_metric_value(groups[0], "Raw Time"), 0.3)

    def test_average_benchmark_all_unfinished_group_has_zero_metric(self):
        app = SATApp.__new__(SATApp)
        rows = [
            BenchmarkRow("N-Queens n8", "N-Queens", "CDCL", "TIMEOUT", 30.0, 100, 64, 1),
            BenchmarkRow("N-Queens n8", "N-Queens", "CDCL", "SKIPPED", 0.0, 100, 64, 2),
        ]

        groups = app._aggregate_benchmark_rows(rows)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["finished_rows"], [])
        self.assertEqual(app._benchmark_group_metric_value(groups[0], "Raw Time"), 0.0)
        self.assertEqual(groups[0]["status_counts"], {"TIMEOUT": 1, "SKIPPED": 1})

    def test_benchmark_detail_helpers_format_edges_stats_and_preview_policy(self):
        app = SATApp.__new__(SATApp)
        row = BenchmarkRow(
            "Graph Coloring n4_p50_k3",
            "Graph Coloring",
            "CDCL",
            "SAT",
            0.2,
            20,
            12,
            1,
            node_count=4,
            edge_count=3,
            graph_edges=[(3, 4), (1, 2), (2, 4)],
            decoded={1: 1, 2: 2, 3: 1, 4: 3},
            seed=9,
        )

        self.assertIn("1-2, 2-4, 3-4", app._format_benchmark_edges(row.graph_edges))
        details = app._format_benchmark_row_details(row)
        self.assertIn("Edges: 3", details)
        self.assertIn("Density: 0.5000", details)
        self.assertIn("Decoded response:", details)
        self.assertEqual(app._graph_preview_policy(80, 250), "auto")
        self.assertEqual(app._graph_preview_policy(81, 250), "manual")
        self.assertEqual(app._graph_preview_policy(200, 800), "manual")
        self.assertEqual(app._graph_preview_policy(201, 800), "skip")

    def test_random_graph_problem_is_buildable(self):
        problem = random_graph_coloring_problem(4, 0.5, 3, seed=1)

        self.assertEqual(problem.problem_type, "Graph Coloring")
        self.assertGreater(problem.clause_count, 0)
        self.assertEqual(problem.metadata["mode"], "probability")
        self.assertEqual(problem.metadata["nodes"], 4)
        self.assertEqual(len(problem.metadata["graph_edges"]), problem.metadata["edges"])

    def test_graph_benchmark_problem_metadata_keeps_edges(self):
        coloring = random_graph_coloring_problem(5, 0.4, 3, seed=2)
        hamiltonian = random_hamiltonian_path_problem(5, 0.4, seed=2)
        independent = random_independent_set_problem(5, 0.4, 2, seed=2)

        for problem in (coloring, hamiltonian, independent):
            self.assertEqual(problem.metadata["nodes"], 5)
            self.assertIn("graph_edges", problem.metadata)
            self.assertEqual(len(problem.metadata["graph_edges"]), problem.metadata["edges"])

    def test_result_to_row_preserves_graph_details_and_decoded_response(self):
        problem = random_graph_coloring_problem(4, 0.5, 3, seed=3)
        decoded = {1: 1, 2: 2, 3: 1, 4: 3}
        result = SolveResult(
            solver="CDCL",
            status="SAT",
            elapsed=0.25,
            solution={},
            decoded=decoded,
            stats={"conflicts": 2, "decisions": 3},
        )

        row = result_to_row(problem, result, repeat=5)

        self.assertEqual(row.node_count, 4)
        self.assertEqual(row.graph_edges, problem.metadata["graph_edges"])
        self.assertEqual(row.decoded, decoded)
        self.assertEqual(row.seed, 3)
        self.assertEqual(row.problem_metadata["nodes"], 4)
        self.assertEqual(row.problem_clauses, problem.clauses)

    def test_benchmark_row_dimacs_uses_stored_clauses(self):
        app = SATApp.__new__(SATApp)
        row = BenchmarkRow(
            "Tiny benchmark",
            "Graph Coloring",
            "CDCL",
            "SAT",
            0.1,
            2,
            2,
            1,
            problem_clauses=[[1, -2], [2]],
        )

        dimacs = app._benchmark_row_dimacs(row)

        self.assertIn("c Tiny benchmark", dimacs)
        self.assertIn("p cnf 2 2", dimacs)
        self.assertEqual(parse_dimacs_text(dimacs), [[1, -2], [2]])

    def test_solver_option_form_builder(self):
        app = SATApp.__new__(SATApp)

        options = app._logging_options(
            False,
            "Periodic progress",
            "MOMS",
            "Random",
            True,
            "25",
            "200",
            "7",
        )

        self.assertEqual(options["mode"], "normal")
        self.assertEqual(options["branching"], "MOMS")
        self.assertEqual(options["initial_phase"], "Random")
        self.assertEqual(options["restart_interval"], 25)
        self.assertEqual(options["learned_clause_limit"], 200)
        self.assertEqual(options["random_seed"], 7)

    def test_benchmark_row_records_solver_options(self):
        problem = random_graph_coloring_problem(4, 0.5, 3, seed=3)
        result = solve_problem(
            problem,
            "CDCL",
            logging_options={"branching": "MOMS", "initial_phase": "Negative first", "restart_interval": 10},
        )

        row = result_to_row(problem, result, repeat=1)

        self.assertIn("branch=MOMS", row.solver_options)
        self.assertIn("phase=Negative first", row.solver_options)
        self.assertIn("restart=10", row.solver_options)

    def test_dpll_ignores_cdcl_options(self):
        problem = dimacs_problem_from_text("p cnf 1 1\n1 0\n")
        result = solve_problem(
            problem,
            "DPLL",
            logging_options={"branching": "Random", "initial_phase": "Random", "random_seed": 4},
        )

        self.assertEqual(result.status, "SAT")
        self.assertEqual(result.stats["solver_options"], "DPLL small-clause")

    def test_dimacs_type_inference_reads_saved_type_comment(self):
        app = SATApp.__new__(SATApp)

        self.assertEqual(app._infer_dimacs_problem_type("c type=Hamiltonian Path\np cnf 1 1\n1 0\n"), "Hamiltonian Path")
        self.assertEqual(app._infer_dimacs_problem_type("c type=Unknown\np cnf 1 1\n1 0\n"), "DIMACS")

    def test_solve_detail_row_uses_current_problem_and_result(self):
        app = SATApp.__new__(SATApp)
        app.current_problem = random_graph_coloring_problem(4, 0.5, 3, seed=3)
        app.latest_solve_result = SolveResult(
            solver="CDCL",
            status="SAT",
            elapsed=0.25,
            solution={},
            decoded={1: 1, 2: 2, 3: 1, 4: 3},
            stats={"conflicts": 2, "decisions": 3},
        )
        app.solver_name = type("SolverName", (), {"get": lambda self: "CDCL"})()

        row = app._solve_detail_row()

        self.assertEqual(row.case_name, app.current_problem.name)
        self.assertEqual(row.status, "SAT")
        self.assertEqual(row.graph_edges, app.current_problem.metadata["graph_edges"])
        self.assertEqual(row.decoded, {1: 1, 2: 2, 3: 1, 4: 3})
        self.assertIn("Graph edges", app._benchmark_problem_data_label(row))
        self.assertEqual(row.problem_clauses, app.current_problem.clauses)

    def test_non_graph_benchmark_details_show_problem_data(self):
        app = SATApp.__new__(SATApp)
        sudoku_row = BenchmarkRow(
            "Sudoku 4x4 benchmark",
            "Sudoku",
            "CDCL",
            "SAT",
            0.1,
            100,
            64,
            1,
            decoded=[
                [1, 2, 3, 4],
                [3, 4, 1, 2],
                [2, 1, 4, 3],
                [4, 3, 2, 1],
            ],
            problem_metadata={
                "size": 4,
                "box_size": 2,
                "givens": 2,
                "empty_cells": 14,
                "grid": [
                    [1, 0, 0, 4],
                    [0, 0, 0, 0],
                    [0, 0, 0, 0],
                    [4, 0, 0, 1],
                ],
            },
        )
        queens_row = BenchmarkRow(
            "N-Queens n4",
            "N-Queens",
            "CDCL",
            "SAT",
            0.1,
            80,
            16,
            1,
            decoded={"positions": [(1, 2), (2, 4), (3, 1), (4, 3)], "board": [".Q..", "...Q", "Q...", "..Q."]},
            problem_metadata={"size": 4, "queens": 4, "board_cells": 16},
        )

        sudoku_details = app._format_benchmark_row_details(sudoku_row)
        sudoku_data = app._format_benchmark_problem_data(sudoku_row)
        queens_details = app._format_benchmark_row_details(queens_row)
        queens_data = app._format_benchmark_problem_data(queens_row)

        self.assertIn("Size: 4x4", sudoku_details)
        self.assertIn("Givens: 2", sudoku_details)
        self.assertIn("Initial puzzle:", sudoku_data)
        self.assertIn("1 . . 4", sudoku_data)
        self.assertIn("Solved grid:", sudoku_data)
        self.assertIn("Board: 4x4", queens_details)
        self.assertIn("Queens: 4", queens_details)
        self.assertIn("Positions:", queens_data)
        self.assertIn(".Q..", queens_data)

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

    def test_benchmark_row_selection_shows_details(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            row = BenchmarkRow(
                "Graph Coloring n3_p50_k2",
                "Graph Coloring",
                "CDCL",
                "SAT",
                0.01,
                8,
                6,
                1,
                conflicts=1,
                decisions=2,
                node_count=3,
                edge_count=2,
                graph_edges=[(1, 2), (2, 3)],
                decoded={1: 1, 2: 2, 3: 1},
                seed=4,
            )

            app._insert_benchmark_row(row)
            item = app.benchmark_table.get_children()[0]
            app.benchmark_table.selection_set(item)
            app._on_benchmark_row_selected()

            details = app.benchmark_detail_text.get("1.0", tk.END)
            edges = app.benchmark_edge_text.get("1.0", tk.END)
            self.assertIn("Status: SAT", details)
            self.assertIn("Conflicts: 1", details)
            self.assertIn("Decoded response:", details)
            self.assertIn("1-2, 2-3", edges)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
