import time

from utils.general_utils import indent
from solvers.solver_utils import unit_propagate_debug, unit_propagate
from solvers.heuristics import choose_variable_basic
from sat_core.runtime import EVENT_LOG, cancellation_status, emit, stop_requested
import utils.colored_text as txt


def _cancel_requested(cancel_token):
    return stop_requested(cancel_token)


def dpll_debug(clauses, assignment=None, level=0, choose_var_fn=None):
    """
    Return a satisfying assignment dict when SAT, otherwise None.
    Prints the recursive search steps for manual debugging.
    """
    if assignment is None:
        assignment = {}

    if choose_var_fn is None:
        choose_var_fn = choose_variable_basic

    print(indent(level) + txt.BOLD + txt.CYAN + "Entering DPLL" + txt.RESET)

    result = unit_propagate_debug(clauses, assignment.copy())

    if result is None:
        print(indent(level) + txt.RED + "Conflict after propagation -> BACKTRACK" + txt.RESET)
        return None

    clauses, assignment = result

    print("\n" + "-" * level + "-" * txt.separator_lenght)
    print(indent(level) + txt.BLUE + f"Clauses: {clauses}" + txt.RESET)
    print(indent(level) + txt.GREEN + f"Assignment: {assignment}" + txt.RESET)
    print("-" * level + "-" * txt.separator_lenght)

    if not clauses:
        print(txt.BOLD + txt.RED + f"level = {level}" + txt.RESET)
        print(indent(level) + txt.GREEN + "SAT FOUND" + txt.RESET)
        return assignment

    var = choose_var_fn(clauses, assignment)
    print(indent(level) + txt.YELLOW + f"Choose variable: {var}" + txt.RESET)

    for value in [True, False]:
        print(indent(level) + txt.CYAN + f"Trying {var} = {value}" + txt.RESET)

        new_assignment = assignment.copy()
        new_assignment[var] = value

        lit = var if value else -var
        new_clauses = []

        for c in clauses:
            if lit in c:
                continue

            if -lit in c:
                new_c = [x for x in c if x != -lit]

                if not new_c:
                    print(indent(level) + txt.RED + "Empty clause -> conflict" + txt.RESET)
                    break

                new_clauses.append(new_c)
            else:
                new_clauses.append(c)

        else:
            result = dpll_debug(new_clauses, new_assignment, level + 1, choose_var_fn)

            if result is not None:
                return result

        print(indent(level) + txt.RED + f"Backtracking on {var} = {value}" + txt.RESET)

    return None


def dpll(
    clauses,
    assignment=None,
    choose_var_fn=None,
    cancel_token=None,
    return_stats=False,
    event_callback=None,
    logging_options=None,
    _stats=None,
    _started=None,
    _level=0,
):
    """
    DPLL SAT solver.

    Return:
    - dict {variable: True/False} if SAT
    - None if UNSAT
    - (solution, stats) when return_stats=True
    """
    top_call = _stats is None
    if _stats is None:
        _stats = {
            "status": "UNKNOWN",
            "decisions": 0,
            "propagations": 0,
            "conflicts": 0,
            "elapsed": 0.0,
            "_verbose_emitted": 0,
            "_last_progress_work": 0,
        }
    if _started is None:
        _started = time.perf_counter()

    logging_options = logging_options or {}
    log_mode = logging_options.get("mode", "normal")
    if log_mode not in ("normal", "periodic", "debug"):
        log_mode = "normal"

    def positive_int(value, default):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default

    progress_interval = positive_int(logging_options.get("progress_interval"), 100)
    verbose_limit = positive_int(logging_options.get("verbose_limit"), 120)

    def public_stats():
        return {key: value for key, value in _stats.items() if not key.startswith("_")}

    def finish(solution, status):
        if status in ("CANCELLED", "TIMEOUT", "SKIPPED") or top_call:
            _stats["status"] = status
        if top_call:
            _stats["elapsed"] = time.perf_counter() - _started
            if return_stats:
                return solution, public_stats()
        return solution

    def log_debug(message):
        if log_mode != "debug" or _stats["_verbose_emitted"] >= verbose_limit:
            return
        _stats["_verbose_emitted"] += 1
        emit(event_callback, EVENT_LOG, f"      DPLL debug: level {_level}: {message}")

    def log_progress(force=False):
        if log_mode not in ("periodic", "debug"):
            return

        work = _stats["decisions"] + _stats["conflicts"] + _stats["propagations"]
        if not force and work - _stats["_last_progress_work"] < progress_interval:
            return

        _stats["_last_progress_work"] = work
        emit(
            event_callback,
            EVENT_LOG,
            (
                "      DPLL progress: "
                f"decisions={_stats['decisions']}, "
                f"conflicts={_stats['conflicts']}, "
                f"propagations={_stats['propagations']}"
            ),
        )

    if _cancel_requested(cancel_token):
        return finish(None, cancellation_status(cancel_token))

    if assignment is None:
        assignment = {}

    if choose_var_fn is None:
        choose_var_fn = choose_variable_basic

    before_propagation = len(assignment)
    result = unit_propagate(clauses, assignment.copy())

    if result is None:
        _stats["conflicts"] += 1
        log_debug("conflict during unit propagation")
        log_progress()
        return finish(None, "UNSAT")

    if _cancel_requested(cancel_token):
        return finish(None, cancellation_status(cancel_token))

    clauses, assignment = result
    propagated = max(0, len(assignment) - before_propagation)
    if propagated:
        _stats["propagations"] += propagated
        log_debug(f"unit propagation assigned {propagated} variable(s)")
        log_progress()

    if not clauses:
        return finish(assignment, "SAT")

    var = choose_var_fn(clauses, assignment)
    if var is None:
        return finish(assignment, "SAT")

    _stats["decisions"] += 1
    log_debug(f"choose variable {var}")
    log_progress()

    for value in [True, False]:
        if _cancel_requested(cancel_token):
            return finish(None, cancellation_status(cancel_token))

        new_assignment = assignment.copy()
        new_assignment[var] = value
        log_debug(f"try {var}={value}")

        lit = var if value else -var
        new_clauses = []
        branch_conflict = False

        for c in clauses:
            if lit in c:
                continue

            if -lit in c:
                new_c = [x for x in c if x != -lit]

                if not new_c:
                    branch_conflict = True
                    _stats["conflicts"] += 1
                    log_debug(f"empty clause after {var}={value}")
                    log_progress()
                    break

                new_clauses.append(new_c)
            else:
                new_clauses.append(c)

        if not branch_conflict:
            result = dpll(
                new_clauses,
                new_assignment,
                choose_var_fn,
                cancel_token=cancel_token,
                return_stats=False,
                event_callback=event_callback,
                logging_options=logging_options,
                _stats=_stats,
                _started=_started,
                _level=_level + 1,
            )

            if _cancel_requested(cancel_token):
                return finish(None, cancellation_status(cancel_token))

            if result is not None:
                return finish(result, "SAT")

        log_debug(f"backtrack on {var}={value}")

    return finish(None, "UNSAT")
