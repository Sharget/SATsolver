from __future__ import annotations

from problems.dimacs_problem import dimacs_problem_from_text
from problems.graph_coloring import (
    average_degree_graph_coloring_problem,
    exact_edges_graph_coloring_problem,
    manual_graph_coloring_problem,
    random_graph_coloring_problem,
)
from problems.sudoku import sudoku_problem
from sat_core.benchmark import run_graph_coloring_sweep
from sat_core.dimacs import clauses_to_dimacs
from sat_core.models import ProblemInstance
from sat_core.runtime import EVENT_CNF, EVENT_LOG, EVENT_PROGRESS, EVENT_RESULT, RunEvent, RunToken
from sat_core.solver_runner import solve_problem


def _problem_payload(problem: ProblemInstance) -> dict:
    return {
        "name": problem.name,
        "problem_type": problem.problem_type,
        "clauses": problem.clauses,
        "metadata": problem.metadata,
    }


def problem_from_snapshot(snapshot: dict) -> ProblemInstance:
    kind = snapshot["kind"]

    if kind == "Sudoku":
        return sudoku_problem(snapshot["grid"])

    if kind == "Graph Coloring":
        if snapshot["mode"] == "Probability":
            return random_graph_coloring_problem(
                snapshot["nodes"],
                snapshot["probability"],
                snapshot["colors"],
                seed=snapshot["seed"],
            )

        if snapshot["mode"] == "Exact edges":
            return exact_edges_graph_coloring_problem(
                snapshot["nodes"],
                snapshot["edge_count"],
                snapshot["colors"],
                seed=snapshot["seed"],
            )

        if snapshot["mode"] == "Average degree":
            return average_degree_graph_coloring_problem(
                snapshot["nodes"],
                snapshot["average_degree"],
                snapshot["colors"],
                seed=snapshot["seed"],
            )

        return manual_graph_coloring_problem(snapshot["nodes"], snapshot["colors"], snapshot["edge_text"])

    return dimacs_problem_from_text(snapshot["text"])


def _emit(queue, event: RunEvent) -> None:
    queue.put(event)


def _problem_summary(problem: ProblemInstance) -> str:
    base = f"Generated {problem.name}: {problem.clause_count} clauses, {problem.variable_count} variables"
    if problem.problem_type != "Graph Coloring":
        return base

    requested_edges = problem.metadata.get("requested_edges")
    actual_edges = problem.metadata.get("edges")
    average_degree = problem.metadata.get("average_degree")
    if average_degree is not None:
        if problem.metadata.get("edge_request_clamped"):
            return f"{base}, average degree {average_degree:g}, requested edges {requested_edges}, actual edges {actual_edges}"
        return f"{base}, average degree {average_degree:g}, edges {actual_edges}"
    if problem.metadata.get("edge_request_clamped"):
        return f"{base}, requested edges {requested_edges}, actual edges {actual_edges}"
    if actual_edges is not None:
        return f"{base}, edges {actual_edges}"
    return base


def generate_cnf_process(snapshot: dict, event_queue, cancel_event) -> None:
    token = RunToken(cancel_event)
    token.raise_if_cancelled()

    problem = problem_from_snapshot(snapshot)
    dimacs = clauses_to_dimacs(
        problem.clauses,
        [
            problem.name,
            f"type={problem.problem_type}",
            f"variables={problem.variable_count}",
        ],
    )

    _emit(event_queue, RunEvent(EVENT_LOG, _problem_summary(problem)))
    _emit(
        event_queue,
        RunEvent(
            EVENT_CNF,
            payload={
                "problem": _problem_payload(problem),
                "dimacs": dimacs,
            },
        ),
    )
    _emit(event_queue, RunEvent(EVENT_PROGRESS, "CNF generated", current=1, total=1))


def solve_process(snapshot: dict, solver_name: str, event_queue, cancel_event) -> None:
    token = RunToken(cancel_event)
    token.raise_if_cancelled()

    problem = problem_from_snapshot(snapshot)
    dimacs = clauses_to_dimacs(
        problem.clauses,
        [
            problem.name,
            f"type={problem.problem_type}",
            f"variables={problem.variable_count}",
        ],
    )

    _emit(event_queue, RunEvent(EVENT_LOG, _problem_summary(problem)))
    _emit(event_queue, RunEvent(EVENT_CNF, payload={"problem": _problem_payload(problem), "dimacs": dimacs}))

    result = solve_problem(problem, solver_name, event_callback=lambda event: _emit(event_queue, event), cancel_token=token)

    if result.status == "CANCELLED":
        token.cancel()
        return

    _emit(event_queue, RunEvent(EVENT_RESULT, payload={"result": result}))
    _emit(event_queue, RunEvent(EVENT_PROGRESS, "Solve complete", current=1, total=1))


def benchmark_process(params: dict, event_queue, cancel_event) -> None:
    token = RunToken(cancel_event)
    token.raise_if_cancelled()

    run_graph_coloring_sweep(
        params["node_counts"],
        params["probabilities"],
        params["color_counts"],
        params["solvers"],
        params["repeats"],
        seed=params["seed"],
        edge_counts=params.get("edge_counts"),
        generation_mode=params.get("generation_mode", "probability"),
        event_callback=lambda event: _emit(event_queue, event),
        cancel_token=token,
        average_degrees=params.get("average_degrees"),
    )
