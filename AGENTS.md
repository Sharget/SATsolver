# SAT Solver App Guide For Future Agents

This repository is now organized around the Tkinter SAT app as the main
product. Older console scripts and generated datasets are kept in `legacy/`
for reference only.

## Product Entry Points

- Run the desktop app:

```powershell
python app.py
```

- Run the unit tests:

```powershell
python -m unittest discover -s tests
```

- Run the small command-line smoke benchmark:

```powershell
python scripts/benchmark_cdcl.py
```

## Current Architecture

- `app.py` is the Tkinter UI. It owns widgets, user input, result display,
  feed messages, progress state, and export buttons.
- `sat_core/` contains reusable backend code:
  - `models.py`: `ProblemInstance`, `SolveResult`, `BenchmarkRow`
  - `solver_runner.py`: normalizes CDCL/DPLL solver calls
  - `benchmark.py`: graph-coloring benchmark sweeps and CSV export
  - `runtime.py`: run events, progress events, and cooperative cancellation
  - `process_workers.py`: multiprocessing workers used by the Tkinter app
  - `dimacs.py`: DIMACS parse/format/load/save helpers for the app
- `problems/` contains problem encoders that return `ProblemInstance`.
  Add new NP problems here rather than inside the UI.
- `solvers/` contains SAT solvers and heuristics.
  Keep `dpll.py` and `cdcl.py` APIs backward-compatible unless tests and docs
  are updated intentionally.
- `utils/` contains lower-level helpers still used by product code.
  Some useful logic remains here, especially Sudoku encoding and graph helpers.
- `tests/` contains standard-library `unittest` tests.
- `docs/` explains the app and the CDCL algorithm for humans.

## Product vs Legacy

Treat these as active product paths:

```text
app.py
sat_core/
problems/
solvers/
utils/
tests/
docs/
scripts/
input/examples/
```

Treat these as archived/reference paths:

```text
legacy/
legacy/generated_graph_coloring_cnf/
```

Do not import from `legacy/` in product code. If an old idea from `legacy/`
is useful, copy the concept into the active architecture and add tests.

## Problem Flow

The intended flow is:

```text
UI input -> problems/* encoder -> ProblemInstance -> sat_core solver wrapper
         -> solvers/CDCL or DPLL -> SolveResult -> UI display/export
```

Problem encoders should not call Tkinter. Solvers should not know about
Sudoku, graph coloring, DIMACS files, or UI state.

## Graph Coloring Modes

Graph coloring currently supports:

- Manual edges: user enters edges like `1-2, 2-3`
- `G(n,p)`: probability-based random graph
- `G(n,m)`: exact-edge-count random graph
- `G(n,d)`: average-degree random graph, converted with
  `m = round(n * d / 2)`

Graph coloring variable encoding is compact:

```text
var = (node - 1) * colors + color
```

Use `utils.general_utils.color_var(node, color, colors)` for new graph-coloring
clauses. Passing `colors` is important to avoid collisions for large color
counts.

## Tkinter Runtime Rules

Long-running work should not run directly on the Tkinter main thread.

- Use `sat_core.process_workers` for app solve/generate/benchmark work.
- Workers send `RunEvent` objects through a queue.
- Tkinter polls the queue with `root.after(...)`.
- Worker processes must not update widgets directly.
- Cancellation is cooperative via `RunToken`.

## Inputs And Outputs

- Keep small stable examples in `input/examples/`.
- App-generated CNFs go under `input/generated/` and are ignored by git.
- Benchmark exports go under `output/benchmarks/` and are ignored by git.
- Large old generated CNFs live in `legacy/generated_graph_coloring_cnf/`.

Current example files used by tests/scripts:

```text
input/examples/sudoku_4x4.cnf
input/examples/graph_coloring/gc_n10_p10_k2.cnf
```

If these move, update tests, docs, and `scripts/benchmark_cdcl.py`.

## Testing Expectations

Before finishing code changes, run:

```powershell
python -m unittest discover -s tests
```

For changes that touch solver APIs, DIMACS paths, or examples, also run:

```powershell
python scripts/benchmark_cdcl.py
```

Use focused tests for new encoders:

- CNF shape/clauses
- decoder behavior
- solver wrapper behavior
- benchmark rows/events
- app smoke tests when UI plumbing changes

## Cleanup Notes

- Do not commit `__pycache__/` or `*.pyc`; `.gitignore` excludes them.
- Do not add new generated benchmark output to git.
- Prefer adding new reusable behavior to `sat_core/` or `problems/`, then have
  the app call that backend.
- Keep comments readable and useful, especially around SAT/CDCL logic.
- Use ASCII in source/docs unless a file already clearly requires Unicode.

