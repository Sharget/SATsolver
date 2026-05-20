from __future__ import annotations

import random
import time

from sat_core.runtime import EVENT_LOG, cancellation_status, emit, stop_requested


def _normalise_formula(clauses):
    clean_clauses = []
    variables = set()
    has_empty_clause = False

    for clause in clauses:
        seen = set()
        clean = []
        tautology = False

        for lit in clause:
            lit = int(lit)
            if lit == 0:
                continue
            if -lit in seen:
                tautology = True
                break
            if lit not in seen:
                clean.append(lit)
                seen.add(lit)
                variables.add(abs(lit))

        if tautology:
            continue
        if clean:
            clean_clauses.append(clean)
        else:
            has_empty_clause = True

    return clean_clauses, sorted(variables), has_empty_clause


class _UnsatisfiedTracker:
    def __init__(self, clauses, variables, assignment):
        self.clauses = clauses
        self.assignment = assignment
        self.occurrences = {variable: [] for variable in variables}
        self.satisfied_counts = [0] * len(clauses)
        self.unsatisfied_list = []
        self.unsatisfied_positions = {}

        for clause_index, clause in enumerate(clauses):
            count = 0
            for lit in clause:
                variable = abs(lit)
                self.occurrences.setdefault(variable, []).append(clause_index)
                if self._literal_satisfied(lit):
                    count += 1

            self.satisfied_counts[clause_index] = count
            if count == 0:
                self._mark_unsatisfied(clause_index)

    def _literal_satisfied(self, lit):
        value = self.assignment.get(abs(lit), False)
        return (lit > 0 and value) or (lit < 0 and not value)

    def _mark_unsatisfied(self, clause_index):
        if clause_index in self.unsatisfied_positions:
            return
        self.unsatisfied_positions[clause_index] = len(self.unsatisfied_list)
        self.unsatisfied_list.append(clause_index)

    def _mark_satisfied(self, clause_index):
        position = self.unsatisfied_positions.pop(clause_index, None)
        if position is None:
            return

        last_clause = self.unsatisfied_list.pop()
        if position < len(self.unsatisfied_list):
            self.unsatisfied_list[position] = last_clause
            self.unsatisfied_positions[last_clause] = position

    def unsatisfied_count(self):
        return len(self.unsatisfied_list)

    def random_unsatisfied_clause(self, rng):
        return self.clauses[rng.choice(self.unsatisfied_list)]

    def flip_score(self, variable):
        score = self.unsatisfied_count()
        current_value = self.assignment[variable]

        for clause_index in self.occurrences.get(variable, []):
            old_count = self.satisfied_counts[clause_index]
            delta = 0
            for lit in self.clauses[clause_index]:
                if abs(lit) != variable:
                    continue
                old_satisfied = (lit > 0 and current_value) or (lit < 0 and not current_value)
                delta += -1 if old_satisfied else 1

            new_count = old_count + delta
            if old_count == 0 and new_count > 0:
                score -= 1
            elif old_count > 0 and new_count == 0:
                score += 1

        return score

    def flip(self, variable):
        current_value = self.assignment[variable]

        for clause_index in self.occurrences.get(variable, []):
            old_count = self.satisfied_counts[clause_index]
            delta = 0
            for lit in self.clauses[clause_index]:
                if abs(lit) != variable:
                    continue
                old_satisfied = (lit > 0 and current_value) or (lit < 0 and not current_value)
                delta += -1 if old_satisfied else 1

            new_count = old_count + delta
            self.satisfied_counts[clause_index] = new_count

            if old_count == 0 and new_count > 0:
                self._mark_satisfied(clause_index)
            elif old_count > 0 and new_count == 0:
                self._mark_unsatisfied(clause_index)

        self.assignment[variable] = not current_value


def walksat(
    clauses,
    max_tries=None,
    max_flips=None,
    noise=None,
    return_stats=False,
    event_callback=None,
    cancel_token=None,
    logging_options=None,
):
    """
    Incomplete WalkSAT-style local-search SAT solver.

    Return:
    - dict {variable: True/False} if SAT
    - None when no solution is found within the search budget
    - (solution, stats) when return_stats=True

    A None result with status UNKNOWN is not an UNSAT proof.
    """
    started = time.perf_counter()
    logging_options = logging_options or {}

    def positive_int(value, default):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default

    def probability(value, default):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return min(1.0, max(0.0, parsed))

    max_tries = positive_int(logging_options.get("max_tries", max_tries), 10)
    max_flips = positive_int(logging_options.get("max_flips", max_flips), 10000)
    noise = probability(logging_options.get("noise", noise), 0.5)
    random_seed = logging_options.get("random_seed")
    rng = random.Random(random_seed) if random_seed not in (None, "") else random.Random()
    log_mode = logging_options.get("mode", "normal")
    if log_mode not in ("normal", "periodic", "debug"):
        log_mode = "normal"
    progress_interval = positive_int(logging_options.get("progress_interval"), 1000)
    verbose_limit = positive_int(logging_options.get("verbose_limit"), 120)

    stats = {
        "status": "UNKNOWN",
        "tries": 0,
        "flips": 0,
        "best_unsatisfied": None,
        "elapsed": 0.0,
        "solver_options": (
            f"tries={max_tries}; flips={max_flips}; noise={noise:g}; "
            f"seed={random_seed if random_seed not in (None, '') else '-'}"
        ),
    }
    verbose_emitted = 0
    last_progress_work = 0

    def finish(solution, status):
        stats["status"] = status
        stats["elapsed"] = time.perf_counter() - started
        if return_stats:
            return solution, stats
        return solution

    def log_debug(message):
        nonlocal verbose_emitted
        if log_mode != "debug" or verbose_emitted >= verbose_limit:
            return
        verbose_emitted += 1
        emit(event_callback, EVENT_LOG, f"      WalkSAT debug: {message}")

    def log_progress(force=False):
        nonlocal last_progress_work
        if log_mode not in ("periodic", "debug"):
            return
        work = stats["flips"]
        if not force and work - last_progress_work < progress_interval:
            return
        last_progress_work = work
        emit(
            event_callback,
            EVENT_LOG,
            (
                "      WalkSAT progress: "
                f"tries={stats['tries']}, "
                f"flips={stats['flips']}, "
                f"best_unsatisfied={stats['best_unsatisfied']}"
            ),
        )

    if stop_requested(cancel_token):
        return finish(None, cancellation_status(cancel_token))

    normalised, variables, has_empty_clause = _normalise_formula(clauses)
    if has_empty_clause:
        stats["best_unsatisfied"] = 1
        return finish(None, "UNKNOWN")
    if not normalised:
        stats["best_unsatisfied"] = 0
        return finish({variable: False for variable in variables}, "SAT")

    best_unsatisfied = len(normalised)
    stats["best_unsatisfied"] = best_unsatisfied

    for try_index in range(1, max_tries + 1):
        if stop_requested(cancel_token):
            return finish(None, cancellation_status(cancel_token))

        stats["tries"] = try_index
        assignment = {variable: rng.choice((False, True)) for variable in variables}
        tracker = _UnsatisfiedTracker(normalised, variables, assignment)
        log_debug(f"try {try_index}: random assignment")

        for _flip_index in range(max_flips):
            unsatisfied_count = tracker.unsatisfied_count()
            if unsatisfied_count < best_unsatisfied:
                best_unsatisfied = unsatisfied_count
                stats["best_unsatisfied"] = best_unsatisfied
                log_progress()

            if unsatisfied_count == 0:
                log_progress(force=True)
                return finish(assignment, "SAT")

            if stop_requested(cancel_token):
                return finish(None, cancellation_status(cancel_token))

            clause = tracker.random_unsatisfied_clause(rng)
            if rng.random() < noise:
                variable = abs(rng.choice(clause))
                log_debug(f"random flip variable {variable}")
            else:
                candidates = [(abs(lit), tracker.flip_score(abs(lit))) for lit in clause]
                best_break = min(count for _variable, count in candidates)
                best_variables = [variable for variable, count in candidates if count == best_break]
                variable = rng.choice(best_variables)
                log_debug(f"greedy flip variable {variable} leaving {best_break} unsatisfied")

            tracker.flip(variable)
            stats["flips"] += 1
            log_progress()

    log_progress(force=True)
    return finish(None, "UNKNOWN")
