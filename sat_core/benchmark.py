from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from problems.graph_coloring import (
    average_degree_graph_coloring_problem,
    exact_edges_graph_coloring_problem,
    random_graph_coloring_problem,
)
from sat_core.models import BENCHMARK_HEADERS, BenchmarkRow, ProblemInstance, SolveResult
from sat_core.runtime import (
    EVENT_CANCELLED,
    EVENT_LOG,
    EVENT_PROGRESS,
    EVENT_ROW,
    RunToken,
    cancel_requested,
    emit,
)
from sat_core.solver_runner import solve_problem


def result_to_row(problem: ProblemInstance, result: SolveResult, repeat: int) -> BenchmarkRow:
    stats = result.stats or {}
    return BenchmarkRow(
        case_name=problem.name,
        problem_type=problem.problem_type,
        solver=result.solver,
        status=result.status,
        elapsed=result.elapsed,
        clauses=problem.clause_count,
        variables=problem.variable_count,
        repeat=repeat,
        conflicts=stats.get("conflicts", "-"),
        decisions=stats.get("decisions", "-"),
        propagations=stats.get("propagations", "-"),
        learned_clauses=stats.get("learned_clauses", "-"),
        generation_mode=problem.metadata.get("mode", ""),
        edge_count=problem.metadata.get("edges", "-"),
    )


def graph_coloring_sweep(
    node_counts: Iterable[int],
    probabilities: Iterable[float],
    color_counts: Iterable[int],
    solvers: Iterable[str],
    repeats: int,
    seed: int | None = None,
) -> list[BenchmarkRow]:
    return run_graph_coloring_sweep(
        node_counts,
        probabilities,
        color_counts,
        solvers,
        repeats,
        seed=seed,
    )


def run_graph_coloring_sweep(
    node_counts: Iterable[int],
    probabilities: Iterable[float] | None,
    color_counts: Iterable[int],
    solvers: Iterable[str],
    repeats: int,
    seed: int | None = None,
    edge_counts: Iterable[int] | None = None,
    generation_mode: str = "probability",
    event_callback=None,
    cancel_token: RunToken | None = None,
    average_degrees: Iterable[float] | None = None,
) -> list[BenchmarkRow]:
    node_counts = list(node_counts)
    if generation_mode == "exact_edges":
        values = list(edge_counts or [])
    elif generation_mode == "average_degree":
        values = list(average_degrees or [])
    else:
        values = list(probabilities or [])
    color_counts = list(color_counts)
    solvers = list(solvers)
    rows = []
    total_cases = len(node_counts) * len(values) * len(color_counts) * repeats
    total_runs = total_cases * len(solvers)
    case_index = 0
    run_index = 0

    if cancel_requested(cancel_token):
        emit(event_callback, EVENT_CANCELLED, "Benchmark cancelled before start.", current=0, total=total_runs)
        return rows

    for n in node_counts:
        for graph_value in values:
            for colors in color_counts:
                for repeat in range(1, repeats + 1):
                    if cancel_requested(cancel_token):
                        emit(event_callback, EVENT_CANCELLED, "Benchmark cancelled.", current=run_index, total=total_runs)
                        return rows

                    case_index += 1
                    seed_component = int(float(graph_value) * 100) if generation_mode in ("probability", "average_degree") else int(graph_value)
                    case_seed = None if seed is None else seed + repeat + n * 1000 + seed_component * 10 + colors
                    if generation_mode == "exact_edges":
                        case_label = f"Graph Coloring n{n}_m{int(graph_value)}_k{colors}"
                    elif generation_mode == "average_degree":
                        case_label = f"Graph Coloring n{n}_d{float(graph_value):g}_k{colors}"
                    else:
                        case_label = f"Graph Coloring n{n}_p{int(float(graph_value) * 100)}_k{colors}"
                    emit(
                        event_callback,
                        EVENT_LOG,
                        f"[{case_index}/{total_cases}] {case_label} repeat {repeat}",
                    )
                    emit(event_callback, EVENT_LOG, "   -> Generating CNF...")
                    if generation_mode == "exact_edges":
                        problem = exact_edges_graph_coloring_problem(n, int(graph_value), colors, seed=case_seed)
                    elif generation_mode == "average_degree":
                        problem = average_degree_graph_coloring_problem(n, float(graph_value), colors, seed=case_seed)
                    else:
                        problem = random_graph_coloring_problem(n, float(graph_value), colors, seed=case_seed)
                    emit(
                        event_callback,
                        EVENT_LOG,
                        _graph_generation_summary(problem),
                    )

                    for solver in solvers:
                        if cancel_requested(cancel_token):
                            emit(event_callback, EVENT_CANCELLED, "Benchmark cancelled.", current=run_index, total=total_runs)
                            return rows

                        emit(event_callback, EVENT_LOG, f"   -> Running {solver} solver...")
                        result = solve_problem(
                            problem,
                            solver,
                            event_callback=event_callback,
                            cancel_token=cancel_token,
                        )

                        if result.status == "CANCELLED":
                            emit(event_callback, EVENT_CANCELLED, "Benchmark cancelled during solver run.", current=run_index, total=total_runs)
                            return rows

                        run_index += 1
                        row = result_to_row(problem, result, repeat)
                        rows.append(row)
                        emit(event_callback, EVENT_ROW, payload={"row": row}, current=run_index, total=total_runs)
                        emit(event_callback, EVENT_PROGRESS, f"{run_index}/{total_runs} solver runs finished", current=run_index, total=total_runs)
                        emit(event_callback, EVENT_LOG, f"      {solver} time: {result.elapsed:.5f}s ({result.status})")

    return rows


def _graph_generation_summary(problem: ProblemInstance) -> str:
    edges = problem.metadata.get("edges")
    requested_edges = problem.metadata.get("requested_edges")
    average_degree = problem.metadata.get("average_degree")
    if average_degree is not None:
        if problem.metadata.get("edge_request_clamped"):
            return (
                f"      Requested average degree: {average_degree:g} "
                f"({requested_edges} edges), Generated edges: {edges} "
                f"(complete graph), Clauses: {problem.clause_count}, Variables: {problem.variable_count}"
            )

        return (
            f"      Average degree: {average_degree:g}, Edges: {edges}, "
            f"Clauses: {problem.clause_count}, Variables: {problem.variable_count}"
        )

    if problem.metadata.get("edge_request_clamped"):
        return (
            f"      Requested edges: {requested_edges}, Generated edges: {edges} "
            f"(complete graph), Clauses: {problem.clause_count}, Variables: {problem.variable_count}"
        )

    return f"      Edges: {edges}, Clauses: {problem.clause_count}, Variables: {problem.variable_count}"


def write_benchmark_csv(path: str | Path, rows: list[BenchmarkRow]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(BENCHMARK_HEADERS)
        for row in rows:
            writer.writerow(row.as_csv_row())
