# SAT Problem App Prototype

Run the desktop prototype with:

```powershell
python app.py
```

The app has two tabs.

## Solve

Choose one problem type:

- Sudoku: choose size `4`, `9`, or `16`, then fill the grid. Empty cells mean
  unknown values.
- Graph Coloring: choose manual edges like `1-2, 2-3`, or random graph
  generation with node count, color count, and optional seed. Random generation
  supports `G(n,p)` probability mode, `G(n,m)` exact-edge-count mode, and
  `G(n,d)` average-degree mode.
- DIMACS/CNF: paste or load raw DIMACS clauses.

Then choose `CDCL` or `DPLL`, generate the CNF preview, and solve. CNF files can
be saved under `input/generated/`.

CNF generation and solving run in a background process, so the window stays
responsive even when the solver is CPU-heavy. The run feed at the bottom shows
messages such as generated clause counts, solver start, solver finish, elapsed
time, and cancellation notices.

## Benchmarks

The benchmark tab runs graph-coloring sweeps over node counts, either
probabilities, exact edge counts, or average degrees, color counts, repeats,
and solvers. It shows a result table and a Matplotlib chart. Results can be
exported to:

```text
output/benchmarks/
```

Benchmark rows appear as each solver run finishes. The feed logs each case,
repeat, CNF generation step, solver start, and solver finish, similar to the old
console output in `legacy/genearate_graph_coloring.py`. Large benchmark charts are not
auto-rendered at the end because drawing hundreds of bars can make Tkinter feel
stuck; use `Refresh Chart` when you want to draw them.

Use probability mode for quick Erdos-Renyi style experiments. Use exact-edge
mode when you want fixed edge counts. Use average-degree mode for fairer
benchmarks across different node counts; it converts `d` into
`m = round(n * d / 2)` and then reuses exact-edge generation. If the requested
edge count is larger than a simple graph can contain, the app generates the
complete graph instead and shows both the requested and actual edge counts in
the feed.

Use `Cancel` to request cooperative cancellation. Small runs may finish before
the click is processed, but longer CDCL, DPLL, and benchmark runs check the
cancel token during their work and stop with status `CANCELLED`.

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
