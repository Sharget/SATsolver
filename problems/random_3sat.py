from __future__ import annotations

import random

from sat_core.models import ProblemInstance

RANDOM_3SAT_MODES = ("Planted SAT", "Forced UNSAT", "Random")


def _decode_assignment(solution: dict[int, bool]) -> dict[str, list[int]]:
    true_variables = sorted(var for var, value in solution.items() if value)
    false_variables = sorted(var for var, value in solution.items() if not value)
    return {
        "true_variables": true_variables,
        "false_variables": false_variables,
    }


def _clause_is_satisfied(clause: list[int], assignment: dict[int, bool]) -> bool:
    return any(assignment[abs(lit)] == (lit > 0) for lit in clause)


def _random_clause(rng, variable_count: int) -> list[int]:
    variables = rng.sample(range(1, variable_count + 1), 3)
    return [
        variable if rng.choice((False, True)) else -variable
        for variable in variables
    ]


def _forced_unsat_core(variables: list[int]) -> list[list[int]]:
    a, b, c = variables
    clauses = []
    for a_positive in (False, True):
        for b_positive in (False, True):
            for c_positive in (False, True):
                clauses.append([
                    a if a_positive else -a,
                    b if b_positive else -b,
                    c if c_positive else -c,
                ])
    return clauses


def random_3sat_problem(
    variable_count: int,
    clause_count: int,
    seed: int | None = None,
    planted: bool = True,
    formula_mode: str | None = None,
) -> ProblemInstance:
    if variable_count < 3:
        raise ValueError("Random 3-SAT needs at least 3 variables")
    if clause_count <= 0:
        raise ValueError("Clause count must be positive")

    if formula_mode is None:
        formula_mode = "Planted SAT" if planted else "Random"
    if formula_mode not in RANDOM_3SAT_MODES:
        raise ValueError(f"Unknown Random 3-SAT mode: {formula_mode}")
    if formula_mode == "Forced UNSAT" and clause_count < 8:
        raise ValueError("Forced UNSAT Random 3-SAT needs at least 8 clauses")

    rng = random.Random(seed) if seed is not None else random
    planted_assignment = {
        variable: rng.choice((False, True))
        for variable in range(1, variable_count + 1)
    }
    clauses = []

    if formula_mode == "Forced UNSAT":
        core_variables = rng.sample(range(1, variable_count + 1), 3)
        clauses.extend(_forced_unsat_core(core_variables))

    while len(clauses) < clause_count:
        while True:
            clause = _random_clause(rng, variable_count)
            if formula_mode != "Planted SAT" or _clause_is_satisfied(clause, planted_assignment):
                clauses.append(clause)
                break

    ratio = clause_count / variable_count
    name = f"Random 3-SAT n{variable_count}_m{clause_count}"
    mode_suffix = {
        "Planted SAT": "planted_sat",
        "Forced UNSAT": "forced_unsat",
        "Random": "random",
    }[formula_mode]
    name += f"_{mode_suffix}"

    return ProblemInstance(
        name=name,
        problem_type="Random 3-SAT",
        clauses=clauses,
        metadata={
            "variables": variable_count,
            "clauses_requested": clause_count,
            "width": 3,
            "ratio": ratio,
            "seed": seed,
            "mode": formula_mode,
            "planted": formula_mode == "Planted SAT",
            "forced_unsat": formula_mode == "Forced UNSAT",
        },
        decoder=_decode_assignment,
    )
