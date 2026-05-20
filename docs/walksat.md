# WalkSAT Local Search

WalkSAT is a local-search SAT solver. It works very differently from DPLL and
CDCL because it does not build a proof tree and does not prove UNSAT.

In this app, WalkSAT is useful as a contrast solver:

- `CDCL`: complete, learns from conflicts, can prove SAT or UNSAT.
- `DPLL`: complete, simpler recursive baseline, can prove SAT or UNSAT.
- `WalkSAT`: incomplete, often fast on SAT instances, returns `UNKNOWN` when it
  does not find a model.

## Status Meaning

When WalkSAT returns `SAT`, the assignment satisfies every clause.

When WalkSAT returns `UNKNOWN`, it means the search budget ended before a
solution was found. The formula might still be SAT. WalkSAT does not report
`UNSAT` because failing to find a solution is not a proof that none exists.

## Search Loop

WalkSAT starts with a random assignment for every variable. Then it repeats:

1. Find all currently unsatisfied clauses.
2. If there are none, the formula is SAT.
3. Pick one unsatisfied clause.
4. Flip one variable from that clause.
5. Continue until solved or the flip limit is reached.

The app implementation uses multiple random tries. Each try starts from a new
random assignment.

## Incremental Tracking

The solver keeps occurrence lists:

```text
variable -> clauses containing that variable
```

It also keeps a satisfaction count for every clause. A clause with count `0` is
currently unsatisfied.

When WalkSAT flips one variable, only clauses containing that variable can
change. The solver updates just those clauses, instead of rescanning the whole
formula after every flip. This is important for larger encodings because a
single flip usually touches a small part of the CNF.

The greedy repair score uses the same occurrence lists. For a candidate
variable, the solver estimates how many clauses would be unsatisfied after the
flip by checking only clauses where that variable appears.

## Noise

When choosing a variable to flip, WalkSAT mixes two behaviors:

- Random walk: choose a random variable from the unsatisfied clause.
- Greedy repair: choose a variable whose flip leaves the fewest unsatisfied
  clauses.

The `noise` value controls how often the random choice is used. Randomness helps
the solver escape unlucky local minima where every obvious greedy move looks
bad.

## App Controls

The app exposes WalkSAT controls in a compact `WalkSAT Options` group:

- `Max tries`: number of random restarts. Default: `10`.
- `Max flips`: maximum flips per try. Default: `10000`.
- `Noise`: probability of making a random flip instead of a greedy repair
  flip. Default: `0.5`.
- `Random seed`: optional seed for reproducible WalkSAT runs.

The solve timeout still applies. A timeout returns `TIMEOUT`, while a normal
budget exhaustion returns `UNKNOWN`.

## Python Usage

```python
from solvers.walksat import walksat

clauses = [[1, 2], [-1, 2], [1, -2]]
solution, stats = walksat(
    clauses,
    return_stats=True,
    logging_options={"random_seed": 7},
)

print(stats["status"])
print(solution)
```

## When To Use It

WalkSAT is a good demonstration solver for random or large SAT-looking
instances where a satisfying assignment probably exists. It is less useful when
you need an UNSAT proof, because `UNKNOWN` only says the local search did not
find a model in time.
