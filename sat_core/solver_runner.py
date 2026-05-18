from __future__ import annotations

import time

from solvers.cdcl import cdcl
from solvers.dpll import dpll
from solvers.heuristics import choose_variable_small_clause
from sat_core.models import ProblemInstance, SolveResult
from sat_core.runtime import EVENT_LOG, RunToken, cancel_requested, emit


SOLVERS = ("CDCL", "DPLL")


def solve_clauses(
    clauses: list[list[int]],
    solver_name: str,
    event_callback=None,
    cancel_token: RunToken | None = None,
) -> SolveResult:
    solver_name = solver_name.upper()
    started = time.perf_counter()
    variables = {abs(lit) for clause in clauses for lit in clause}

    if cancel_requested(cancel_token):
        return SolveResult(
            solver=solver_name,
            status="CANCELLED",
            elapsed=0.0,
            solution=None,
            stats={"elapsed": 0.0, "status": "CANCELLED"},
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
        )
        elapsed = stats.get("elapsed", time.perf_counter() - started)
        status = stats.get("status", "SAT" if solution is not None else "UNSAT")
    elif solver_name == "DPLL":
        solution = dpll(clauses, choose_var_fn=choose_variable_small_clause, cancel_token=cancel_token)
        elapsed = time.perf_counter() - started
        status = "CANCELLED" if cancel_requested(cancel_token) else ("SAT" if solution is not None else "UNSAT")
        stats = {"elapsed": elapsed, "status": status}
    else:
        raise ValueError(f"Unknown solver: {solver_name}")

    if status == "CANCELLED":
        emit(event_callback, EVENT_LOG, f"{solver_name} cancelled after {elapsed:.4f}s.")
    else:
        emit(event_callback, EVENT_LOG, f"{solver_name} finished: {status} in {elapsed:.4f}s.")

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
) -> SolveResult:
    result = solve_clauses(
        problem.clauses,
        solver_name,
        event_callback=event_callback,
        cancel_token=cancel_token,
    )
    result.decoded = problem.decode_solution(result.solution)
    return result
