# SAT Problem App Prototype

Run the desktop prototype with:

```powershell
python app.py
```

The app has two tabs.

## Solve

Choose one problem type:

- Sudoku: choose size `4`, `9`, `16`, or `25`, then fill the grid. Empty cells mean
  unknown values.
- Graph Coloring: choose manual edges like `1-2, 2-3`, or random graph
  generation with node count, color count, and optional seed. Random generation
  supports `G(n,p)` probability mode, `G(n,m)` exact-edge-count mode, and
  `G(n,d)` average-degree mode.
- N-Queens: choose board size `n`. The app asks whether `n` queens can be
  placed on an `n x n` board with no shared row, column, or diagonal.
- Hamiltonian Path: choose manual or random undirected graph input. The app
  asks whether some path visits every node exactly once.
- Independent Set: choose manual or random undirected graph input plus target
  `k`. The app asks whether at least `k` nodes can be chosen with no edges
  between chosen nodes.
- DIMACS/CNF: paste or load raw DIMACS clauses.

Then choose `CDCL`, `DPLL`, or `WalkSAT`, generate the CNF preview, and solve.
CNF files can be saved under `input/generated/`. The compact Solver Guide in
the controls summarizes the solver families:

- `CDCL`: complete, learns clauses, backjumps, strongest default for hard
  formulas.
- `DPLL`: complete, recursive baseline, simpler and useful for comparison.
- `WalkSAT`: incomplete, random local search, fast on some SAT instances, and
  returns `UNKNOWN` if no model is found.

Advanced solver logs can be enabled for periodic progress messages or capped
verbose debug messages during a solve. The solve timeout defaults to 30
seconds; if a solver run exceeds it, the app stops that run and reports
`TIMEOUT`.

The CDCL advanced options let you experiment with search behavior:

- `CDCL branching`: `VSIDS`, `Most frequent`, `MOMS`, `DLIS`, or `Random`.
- `Initial phase`: `Positive first`, `Negative first`, `Polarity based`, or
  `Random`.
- `Restarts`: optionally restart CDCL every N conflicts while keeping learned
  clauses and activity scores.
- `Learned limit`: optionally cap the learned-clause database.
- `Random seed`: makes random branching and random phase choices repeatable.

These controls are grouped under `CDCL Options` because they apply only when
the selected solver is `CDCL`. `DPLL` ignores them and remains a fixed baseline
solver.

WalkSAT has its own `WalkSAT Options` group:

- `Max tries`: number of random restarts.
- `Max flips`: maximum flips per random try.
- `Noise`: probability of choosing a random variable from an unsatisfied clause
  instead of the best repair flip.
- `Random seed`: optional seed for reproducible local search.
Problem descriptions appear beside the controls, and irrelevant graph/log
settings are disabled as modes change.

CNF generation and solving run as background jobs, so the window stays
responsive even when the solver is CPU-heavy. The Solve tab has a compact
`Solve Jobs` panel. Pick a finished solve or generate job there to reload its
CNF, solver result, decoded response, problem input, and graph preview into the
main Solve view. `Cancel Selected` stops only the selected solve job, and
`Delete Selected` removes one finished solve job. `Clear Finished` removes all
finished solve jobs from that list.

The shared run feed at the bottom stays global and prefixes messages with the
job label, such as `J1` or `J2`.

## Benchmarks

The benchmark tab runs graph-coloring sweeps over node counts, either
probabilities, exact edge counts, or average degrees, color counts, repeats,
and solvers. The benchmark controls group the solver checkboxes with the same
Solver Guide used on the Solve tab, so the complete solvers and incomplete
local-search solver are easy to compare. It also runs Sudoku benchmarks over
built-in deterministic
`4x4`, `9x9`, `16x16`, and `25x25` cases. Sudoku defaults to `4x4` and `9x9`;
larger sizes are opt-in because they can take much longer. N-Queens benchmarks
sweep board sizes. Hamiltonian Path and Independent Set benchmarks reuse the
same random graph modes as graph coloring; Independent Set also sweeps target
`k` values. Benchmark solver logs can use the same normal, periodic progress,
or capped verbose modes as Solve. The benchmark tab also has the same CDCL
heuristic controls as the Solve tab. The compact option summary is stored in
each benchmark row, exported in CSV files, shown in the selected-case details,
and included as a comment when saving a selected benchmark CNF. Each benchmark
solver run also has a timeout, defaulting to 30 seconds. Timed-out runs are kept
as `TIMEOUT` rows and shown as distinct chart bars before the benchmark
continues. The chart title shows the active problem type, so bar labels stay
compact. Results appear in a shared table and Matplotlib chart and can be
exported to:

```text
output/benchmarks/
```

Benchmark rows appear as each solver run finishes. When multiple benchmarks are
running at once, the table and CSV export include a `Run`/`run` label so rows
from different jobs are easy to distinguish. The Benchmark tab also has a
`Benchmark Jobs` panel:

- `Show Selected Run` filters the shared table and chart to that job's rows.
- `Show All Runs` restores the combined benchmark table and chart.
- `Clear Selected Results` removes only that selected job's benchmark rows.
- `Delete Selected Job` removes one finished benchmark job and its rows.
- `Clear Table` or `Clear All Results` empties the benchmark result table.
- `Clear Finished Jobs` removes finished benchmark jobs from the job list, but
  does not delete their rows unless you clear results.

Select any benchmark row to inspect that exact case's solver response, decoded
output, input data, saved CNF, and graph preview. The feed logs each case,
repeat, CNF generation step, solver start, and solver finish, similar to the old
console output in `legacy/genearate_graph_coloring.py`. Large benchmark charts
are not auto-rendered at the end because drawing hundreds of bars can make
Tkinter feel stuck; use `Refresh Chart` when you want to draw them. Filtering
between benchmark jobs refreshes the table first and then redraws the chart so
job switching stays responsive.

Use benchmark heuristic comparisons carefully. Changing branching, phase,
restarts, learned-clause limits, or CDCL random seed changes the CDCL search
path. Changing WalkSAT tries, flips, noise, or WalkSAT random seed changes the
local-search path. Compare runs with the same timeout, problem sweep, solver
set, and repeat count. Random modes should use a seed when you want
reproducible results.

Use probability mode for quick Erdos-Renyi style experiments. Use exact-edge
mode when you want fixed edge counts. Use average-degree mode for fairer
benchmarks across different node counts; it converts `d` into
`m = round(n * d / 2)` and then reuses exact-edge generation. If the requested
edge count is larger than a simple graph can contain, the app generates the
complete graph instead and shows both the requested and actual edge counts in
the feed.

Use `Cancel Selected` in the relevant job panel to request cooperative
cancellation for that selected job. Small runs may finish before the click is
processed, but longer CDCL, DPLL, WalkSAT, and benchmark runs check the cancel
token during their work and stop with status `CANCELLED`.

Use `Skip Selected Case` during a benchmark to mark the selected benchmark
job's current case as `SKIPPED` and continue with the next case. This is useful
when one generated graph or puzzle is taking much longer than the surrounding
sweep.

## Adding More NP Problems

Add a new encoder in `problems/` that returns a `ProblemInstance`:

```python
from sat_core.models import ProblemInstance

def my_problem(...) -> ProblemInstance:
    return ProblemInstance(
        name="My Problem",
        problem_type="My Problem",
        clauses=clauses,
        metadata={},
        decoder=optional_decoder,
    )
```

The UI and benchmark code use the same `ProblemInstance` shape, so new problems
can be added without changing the solvers.
