# Conflict-Driven Clause Learning

This project represents SAT problems in CNF form. A formula is a list of
clauses, and each clause is a list of integer literals:

```python
[[1, -2], [2, 3], [-1]]
```

Positive `x` means variable `x` is true. Negative `-x` means variable `x` is
false. A clause is satisfied when at least one of its literals is true. The
whole formula is satisfied when every clause is satisfied.

## DPLL vs CDCL

DPLL tries a value, simplifies the formula, and backtracks when it reaches a
conflict. CDCL keeps the same search idea, but when a conflict happens it asks:
"what combination of assignments caused this?"

The answer becomes a learned clause. That learned clause blocks the solver from
making the same mistake again.

## Trail and Decision Levels

The CDCL solver stores assignments in a trail:

```text
1, -4, 7, -9
```

Each literal means one assignment. For example, `-4` means variable `4` is
false. The solver also stores the decision level for each assignment. Level `0`
contains facts forced before any guess. Every manual guess starts a new level.

This matters because CDCL can backjump. Instead of undoing only the last guess,
it jumps directly to the highest level that is still relevant to the learned
clause.

## Unit Propagation

A clause becomes unit when all but one literal are false:

```text
[-1, 2, 3]
```

If `1=True` and `3=False`, the only way to satisfy the clause is `2=True`.
That assignment is forced, not guessed. The solver stores the clause as the
reason for `2=True`.

## Watched Literals

Simple propagation scans every clause after every assignment. That is slow.

Watched literals avoid most scans. Each clause watches two literals. A clause is
only revisited when one of its watched literals becomes false. Then the clause
tries to watch another non-false literal. If it cannot, the clause is either:

- unit, so it forces the other watched literal
- conflicting, so conflict analysis starts

This is why the new CDCL solver can be much faster than simple DPLL on larger
CNF files.

## Conflict Analysis and First UIP

When a conflict appears, all literals in the conflicting clause are false. CDCL
walks backward through the trail and resolves the conflict clause with the
reason clauses of propagated assignments.

The solver stops when the learned clause contains exactly one literal from the
current decision level. This point is called the first UIP, short for first
Unique Implication Point.

That learned clause is useful because, after backjumping, it becomes unit and
immediately forces a better assignment.

## Backjumping

The learned clause has this shape:

```text
[asserting_literal, older_literal, older_literal, ...]
```

The solver jumps back to the highest decision level among the older literals.
At that level, the older literals are still false, so the asserting literal must
be true. This avoids repeating the conflict.

## VSIDS-Style Activity

Every variable has an activity score. When a variable appears in conflict
analysis, its score increases. Over time, recent conflicts matter more than old
ones. The next decision chooses the unassigned variable with the highest score.

This is a small version of the VSIDS idea used by modern SAT solvers.

## How To Run

Solve a DIMACS file directly from Python:

```python
from solvers.cdcl import cdcl
from utils.dimacs import read_dimacs_cnf

clauses = read_dimacs_cnf("input/examples/graph_coloring/gc_n10_p10_k2.cnf")
solution, stats = cdcl(clauses, return_stats=True)

print(solution)
print(stats)
```

Run the tests:

```powershell
python -m unittest discover -s tests
```

Run a small DPLL vs CDCL benchmark:

```powershell
python scripts/benchmark_cdcl.py
```
