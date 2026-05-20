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
from sat_core.models import BenchmarkRow, ProblemInstance, SolveResult
from sat_core.runtime import EVENT_CNF, EVENT_LOG, EVENT_ROW, RunEvent, RunToken
from sat_core.solver_runner import SOLVERS, solve_problem
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

    def test_walksat_benchmark_sweep_rows(self):
        rows = graph_coloring_sweep([3], [0.2], [2], ["WalkSAT"], repeats=1, seed=7)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].solver, "WalkSAT")
        self.assertIn(rows[0].status, ("SAT", "UNKNOWN"))

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
        self.assertEqual(options["cdcl_random_seed"], 7)
        self.assertEqual(options["walksat_max_tries"], 10)
        self.assertEqual(options["walksat_max_flips"], 10000)
        self.assertEqual(options["walksat_noise"], 0.5)
        self.assertIsNone(options["walksat_random_seed"])

    def test_walksat_option_form_builder(self):
        app = SATApp.__new__(SATApp)

        options = app._logging_options(
            False,
            "Periodic progress",
            walksat_max_tries="3",
            walksat_max_flips="40",
            walksat_noise="0.25",
            walksat_random_seed="9",
        )

        self.assertEqual(options["walksat_max_tries"], 3)
        self.assertEqual(options["walksat_max_flips"], 40)
        self.assertEqual(options["walksat_noise"], 0.25)
        self.assertEqual(options["walksat_random_seed"], 9)

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
            self.assertIn("WalkSAT", SOLVERS)
            self.assertIn("WalkSAT", app.solve_solver_guide.guide_text)
            self.assertIn("UNKNOWN", app.solve_solver_guide.guide_text)
            self.assertIn("WalkSAT", app.benchmark_solver_guide.guide_text)
            self.assertFalse(app.bench_walksat.get())
            self.assertEqual(str(app.solve_cdcl_options_frame.cget("text")), "CDCL Options")
            self.assertEqual(str(app.benchmark_cdcl_options_frame.cget("text")), "CDCL Options")
            self.assertEqual(str(app.solve_walksat_options_frame.cget("text")), "WalkSAT Options")
            self.assertEqual(str(app.benchmark_walksat_options_frame.cget("text")), "WalkSAT Options")
            self.assertEqual(app.walksat_max_tries.get(), "10")
            self.assertEqual(app.walksat_max_flips.get(), "10000")
            self.assertEqual(app.walksat_noise.get(), "0.5")
            self.assertEqual(str(app.solve_jobs_scrollbar.cget("orient")), "vertical")
            self.assertEqual(str(app.benchmark_jobs_scrollbar.cget("orient")), "vertical")

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
            skip_event = object()
            benchmark_job = app._create_job("benchmark", "Benchmarking", skip_event=skip_event)
            benchmark_job.status = "Running"
            app._update_job_row(benchmark_job)
            self.assertEqual(str(app.skip_benchmark_button.cget("state")), "normal")
            app._finish_job(benchmark_job, "Done")
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

    def test_parallel_jobs_can_start_while_another_job_is_running(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            app._create_job("benchmark", "Long benchmark")

            def worker(_token, event_callback):
                event_callback(RunEvent(EVENT_LOG, "parallel hello"))

            solve_job = app._start_worker("Tiny solve", worker, kind="solve")
            time.sleep(0.05)
            app._poll_run_events()

            self.assertEqual(len(app.jobs), 2)
            self.assertEqual(solve_job.kind, "solve")
            self.assertIn("parallel hello", app.feed_text.get("1.0", tk.END))
        finally:
            root.destroy()

    def test_job_tagged_solve_events_update_only_selected_job(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            first = app._create_job("solve", "First solve")
            second = app._create_job("solve", "Second solve")

            app._handle_run_event(RunEvent(
                EVENT_CNF,
                payload={
                    "_job_id": first.job_id,
                    "problem": {
                        "name": "first problem",
                        "problem_type": "DIMACS",
                        "clauses": [[1]],
                        "metadata": {},
                    },
                    "dimacs": "p cnf 1 1\n1 0\n",
                },
            ))

            self.assertIsNone(app.current_problem)
            app._select_job(first.job_id)
            self.assertEqual(app.current_problem.name, "first problem")
            self.assertEqual(app.selected_job_id, first.job_id)
            self.assertNotEqual(app.selected_job_id, second.job_id)
        finally:
            root.destroy()

    def test_cancel_selected_job_does_not_cancel_other_jobs(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            first = app._create_job("solve", "First solve")
            second = app._create_job("solve", "Second solve")
            first.token = RunToken()
            second.token = RunToken()

            app._select_job(first.job_id)
            app.cancel_active_run()

            self.assertTrue(first.token.is_cancelled())
            self.assertFalse(second.token.is_cancelled())
            self.assertEqual(first.status, "Cancelling...")
        finally:
            root.destroy()

    def test_job_selection_event_does_not_recurse(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            job = app._create_job("solve", "Selectable solve")
            app.updating_job_selection = True
            app._on_solve_job_selected()
            app.updating_job_selection = False

            self.assertEqual(app.selected_job_id, job.job_id)
            self.assertEqual(app.solve_jobs_table.selection(), (job.job_id,))
        finally:
            root.destroy()

    def test_combobox_mousewheel_scrolls_page_instead_of_value(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            calls = []
            canvas = app.solve_tab._tab_scroll_canvas
            original_yview_scroll = canvas.yview_scroll

            def fake_yview_scroll(amount, units):
                calls.append((amount, units))

            canvas.yview_scroll = fake_yview_scroll

            event = type("Event", (), {})()
            event.widget = app.solver_log_box
            event.delta = -120
            event.state = 0

            self.assertEqual(app._scroll_page_from_combobox(event), "break")
            self.assertEqual(calls, [(1, "units")])
            canvas.yview_scroll = original_yview_scroll
        finally:
            root.destroy()

    def test_per_tab_job_tables_separate_solve_and_benchmark_jobs(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            solve_job = app._create_job("solve", "Solve job")
            benchmark_job = app._create_job("benchmark", "Benchmark job")

            self.assertTrue(app.solve_jobs_table.exists(solve_job.job_id))
            self.assertFalse(app.solve_jobs_table.exists(benchmark_job.job_id))
            self.assertTrue(app.benchmark_jobs_table.exists(benchmark_job.job_id))
            self.assertFalse(app.benchmark_jobs_table.exists(solve_job.job_id))
        finally:
            root.destroy()

    def test_selecting_finished_solve_job_reloads_result_view(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            job = app._create_job("solve", "Finished solve")
            app._handle_run_event(RunEvent(
                EVENT_CNF,
                payload={
                    "_job_id": job.job_id,
                    "problem": {
                        "name": "tiny cnf",
                        "problem_type": "DIMACS",
                        "clauses": [[1]],
                        "metadata": {},
                    },
                    "dimacs": "p cnf 1 1\n1 0\n",
                },
            ))
            job.result = SolveResult("CDCL", "SAT", 0.01, {1: True}, clauses=1, variables=1)
            job.finished = True

            app.cnf_text.delete("1.0", tk.END)
            app._select_job(job.job_id)

            self.assertEqual(app.current_problem.name, "tiny cnf")
            self.assertIn("p cnf 1 1", app.cnf_text.get("1.0", tk.END))
            self.assertIn("Status: SAT", app.result_text.get("1.0", tk.END))
        finally:
            root.destroy()

    def test_parallel_benchmark_rows_are_appended_and_labeled(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            first = app._create_job("benchmark", "First benchmark")
            second = app._create_job("benchmark", "Second benchmark")
            first_row = BenchmarkRow("case one", "N-Queens", "CDCL", "SAT", 0.1, 1, 1, 1)
            second_row = BenchmarkRow("case two", "N-Queens", "WalkSAT", "UNKNOWN", 0.2, 1, 1, 1)

            app._handle_run_event(RunEvent(EVENT_ROW, payload={"_job_id": first.job_id, "row": first_row}, current=1, total=2))
            app._handle_run_event(RunEvent(EVENT_ROW, payload={"_job_id": second.job_id, "row": second_row}, current=1, total=2))

            self.assertEqual(len(app.benchmark_rows), 2)
            self.assertEqual(first_row.run_label, first.label)
            self.assertEqual(second_row.run_label, second.label)
            self.assertEqual(app.benchmark_table.set(app.benchmark_table.get_children()[0], "run"), first.label)
            self.assertEqual(app.benchmark_table.set(app.benchmark_table.get_children()[1], "run"), second.label)
            self.assertEqual(first_row.as_csv_row()[0], first.label)
        finally:
            root.destroy()

    def test_benchmark_run_filter_and_clear_actions(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            app.draw_benchmark_chart = lambda: None
            first = app._create_job("benchmark", "First benchmark")
            second = app._create_job("benchmark", "Second benchmark")
            first_row = BenchmarkRow("case one", "N-Queens", "CDCL", "SAT", 0.1, 1, 1, 1)
            second_row = BenchmarkRow("case two", "N-Queens", "WalkSAT", "UNKNOWN", 0.2, 1, 1, 1)

            app._handle_run_event(RunEvent(EVENT_ROW, payload={"_job_id": first.job_id, "row": first_row}, current=1, total=2))
            app._handle_run_event(RunEvent(EVENT_ROW, payload={"_job_id": second.job_id, "row": second_row}, current=1, total=2))

            app._select_job(first.job_id)
            app.show_selected_benchmark_run()
            self.assertEqual(app.benchmark_filter_run_label, first.label)
            self.assertEqual(len(app.benchmark_table.get_children()), 1)
            self.assertEqual(app._visible_benchmark_rows(), [first_row])
            self.assertIsNotNone(app.pending_benchmark_chart_after_id)
            app.root.after_cancel(app.pending_benchmark_chart_after_id)
            app.pending_benchmark_chart_after_id = None

            app.show_all_benchmark_runs()
            self.assertIsNone(app.benchmark_filter_run_label)
            self.assertEqual(len(app.benchmark_table.get_children()), 2)
            self.assertIsNotNone(app.pending_benchmark_chart_after_id)
            app.root.after_cancel(app.pending_benchmark_chart_after_id)
            app.pending_benchmark_chart_after_id = None

            app._select_job(first.job_id)
            app.clear_selected_benchmark_run_results()
            self.assertEqual(app.benchmark_rows, [second_row])
            self.assertEqual(first.rows, [])
            if app.pending_benchmark_chart_after_id is not None:
                app.root.after_cancel(app.pending_benchmark_chart_after_id)
                app.pending_benchmark_chart_after_id = None

            app.clear_all_benchmark_results()
            self.assertEqual(app.benchmark_rows, [])
            self.assertEqual(len(app.benchmark_table.get_children()), 0)
        finally:
            root.destroy()

    def test_clear_benchmark_table_clears_results_but_keeps_jobs(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            job = app._create_job("benchmark", "Benchmark job")
            row = BenchmarkRow("case one", "N-Queens", "CDCL", "SAT", 0.1, 1, 1, 1)
            app._handle_run_event(RunEvent(EVENT_ROW, payload={"_job_id": job.job_id, "row": row}, current=1, total=1))
            app.benchmark_filter_run_label = job.label
            app.benchmark_canvas = type("CanvasStub", (), {"get_tk_widget": lambda self: type("WidgetStub", (), {"destroy": lambda self: None})()})()
            app.benchmark_figure = object()

            app.clear_benchmark_table()

            self.assertEqual(app.benchmark_rows, [])
            self.assertTrue(app.benchmark_jobs_table.exists(job.job_id))
            self.assertIsNone(app.benchmark_filter_run_label)
            self.assertIsNone(app.benchmark_canvas)
            self.assertIsNone(app.benchmark_figure)
            self.assertEqual(len(app.benchmark_table.get_children()), 0)
            self.assertIn("Select a benchmark row", app.benchmark_detail_text.get("1.0", tk.END))
        finally:
            root.destroy()

    def test_delete_selected_solve_job_removes_only_that_job(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            first = app._create_job("solve", "First solve")
            second = app._create_job("solve", "Second solve")
            first.finished = True
            first.status = "Done"
            first.problem = ProblemInstance("first", "DIMACS", [[1]], {})
            first.dimacs = "p cnf 1 1\n1 0\n"
            second.finished = True
            second.status = "Done"

            app._select_job(first.job_id)
            app.delete_selected_solve_job()

            self.assertNotIn(first.job_id, app.jobs)
            self.assertIn(second.job_id, app.jobs)
            self.assertFalse(app.solve_jobs_table.exists(first.job_id))
            self.assertTrue(app.solve_jobs_table.exists(second.job_id))
            self.assertIsNone(app.selected_solve_job_id)
            self.assertIsNone(app.current_problem)
            self.assertIn("Generate or solve", app.result_text.get("1.0", tk.END))
        finally:
            root.destroy()

    def test_delete_selected_benchmark_job_removes_its_rows_only(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

        root.withdraw()
        try:
            app = SATApp(root)
            app.draw_benchmark_chart = lambda: None
            first = app._create_job("benchmark", "First benchmark")
            second = app._create_job("benchmark", "Second benchmark")
            first.finished = True
            first.status = "Done"
            second.finished = True
            second.status = "Done"
            first_row = BenchmarkRow("case one", "N-Queens", "CDCL", "SAT", 0.1, 1, 1, 1)
            second_row = BenchmarkRow("case two", "N-Queens", "WalkSAT", "UNKNOWN", 0.2, 1, 1, 1)

            app._handle_run_event(RunEvent(EVENT_ROW, payload={"_job_id": first.job_id, "row": first_row}, current=1, total=2))
            app._handle_run_event(RunEvent(EVENT_ROW, payload={"_job_id": second.job_id, "row": second_row}, current=1, total=2))
            app._select_job(first.job_id)
            app.benchmark_filter_run_label = first.label

            app.delete_selected_benchmark_job()

            self.assertNotIn(first.job_id, app.jobs)
            self.assertIn(second.job_id, app.jobs)
            self.assertFalse(app.benchmark_jobs_table.exists(first.job_id))
            self.assertTrue(app.benchmark_jobs_table.exists(second.job_id))
            self.assertEqual(app.benchmark_rows, [second_row])
            self.assertIsNone(app.benchmark_filter_run_label)
            self.assertEqual(len(app.benchmark_table.get_children()), 1)
            self.assertEqual(app.benchmark_table.set(app.benchmark_table.get_children()[0], "run"), second.label)

            if app.pending_benchmark_chart_after_id is not None:
                app.root.after_cancel(app.pending_benchmark_chart_after_id)
                app.pending_benchmark_chart_after_id = None
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
