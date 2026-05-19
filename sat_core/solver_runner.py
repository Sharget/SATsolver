from __future__ import annotations

import time

from solvers.cdcl import cdcl
from solvers.dpll import dpll
from solvers.heuristics import choose_variable_small_clause
from sat_core.models import ProblemInstance, SolveResult
from sat_core.runtime import EVENT_LOG, RunToken, cancellation_status, emit, stop_requested


SOLVERS = ("CDCL", "DPLL")


def solve_clauses(
    clauses: list[list[int]],
    solver_name: str,
    event_callback=None,
    cancel_token: RunToken | None = None,
    logging_options: dict | None = None,
    timeout_seconds: float | None = None,
) -> SolveResult:
    solver_name = solver_name.upper()
    logging_options = logging_options or {}
    if timeout_seconds is not None:
        cancel_token = RunToken(timeout_seconds=timeout_seconds, parent=cancel_token)
    started = time.perf_counter()
    variables = {abs(lit) for clause in clauses for lit in clause}

    if stop_requested(cancel_token):
        status = cancellation_status(cancel_token)
        if status == "TIMEOUT":
            emit(event_callback, EVENT_LOG, f"{solver_name} timed out before starting.")
        elif status == "SKIPPED":
            emit(event_callback, EVENT_LOG, f"{solver_name} skipped before starting.")
        else:
            emit(event_callback, EVENT_LOG, f"{solver_name} cancelled before starting.")
        return SolveResult(
            solver=solver_name,
            status=status,
            elapsed=0.0,
            solution=None,
            stats={"elapsed": 0.0, "status": status},
            clauses=len(clauses),
            variables=len(variables),
        )

    emit(event_callback, EVENT_LOG, f"Solving with {solver_name}...")

    if solver_name == "CDCL":
        solution, stats = cdcl(
            clauses,
            return_stats=True,
            event_callback=event_callback,
            cancel_token=cancel_token,
            logging_options=logging_options,
        )
        elapsed = stats.get("elapsed", time.perf_counter() - started)
        status = stats.get("status", "SAT" if solution is not None else "UNSAT")
    elif solver_name == "DPLL":
        solution, stats = dpll(
            clauses,
            choose_var_fn=choose_variable_small_clause,
            cancel_token=cancel_token,
            return_stats=True,
            event_callback=event_callback,
            logging_options=logging_options,
        )
        elapsed = stats.get("elapsed", time.perf_counter() - started)
        status = stats.get("status", "SAT" if solution is not None else "UNSAT")
    else:
        raise ValueError(f"Unknown solver: {solver_name}")

    if status == "CANCELLED":
        emit(event_callback, EVENT_LOG, f"{solver_name} cancelled after {elapsed:.4f}s.")
    elif status == "TIMEOUT":
        emit(event_callback, EVENT_LOG, f"{solver_name} timed out after {elapsed:.4f}s.")
        stats_summary = _stats_summary(stats)
        if stats_summary:
            emit(event_callback, EVENT_LOG, f"{solver_name} stats: {stats_summary}")
    elif status == "SKIPPED":
        emit(event_callback, EVENT_LOG, f"{solver_name} skipped after {elapsed:.4f}s.")
        stats_summary = _stats_summary(stats)
        if stats_summary:
            emit(event_callback, EVENT_LOG, f"{solver_name} stats: {stats_summary}")
    else:
        emit(event_callback, EVENT_LOG, f"{solver_name} finished: {status} in {elapsed:.4f}s.")
        stats_summary = _stats_summary(stats)
        if stats_summary:
            emit(event_callback, EVENT_LOG, f"{solver_name} stats: {stats_summary}")

    return SolveResult(
        solver=solver_name,
        status=status,
        elapsed=elapsed,
        solution=solution,
        stats=stats,
        clauses=len(clauses),
        variables=len(variables),
    )


def solve_problem(
    problem: ProblemInstance,
    solver_name: str,
    event_callback=None,
    cancel_token: RunToken | None = None,
    logging_options: dict | None = None,
    timeout_seconds: float | None = None,
) -> SolveResult:
    result = solve_clauses(
        problem.clauses,
        solver_name,
        event_callback=event_callback,
        cancel_token=cancel_token,
        logging_options=logging_options,
        timeout_seconds=timeout_seconds,
    )
    result.decoded = problem.decode_solution(result.solution)
    return result


def _stats_summary(stats: dict) -> str:
    labels = [
        ("decisions", "decisions"),
        ("conflicts", "conflicts"),
        ("propagations", "propagations"),
        ("learned_clauses", "learned"),
    ]
    parts = [f"{label}={stats[key]}" for key, label in labels if key in stats]
    return ", ".join(parts)
