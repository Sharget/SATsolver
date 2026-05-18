import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solvers.cdcl import cdcl
from solvers.dpll import dpll
from utils.dimacs import read_dimacs_cnf


CASES = [
    "input/examples/sudoku_4x4.cnf",
    "input/examples/graph_coloring/gc_n10_p10_k2.cnf",
]


def time_solver(name, solver, clauses):
    start = time.perf_counter()
    solution, stats = solver(clauses, return_stats=True) if name == "CDCL" else (solver(clauses), None)
    elapsed = time.perf_counter() - start
    status = "SAT" if solution is not None else "UNSAT"
    return status, elapsed, stats


def main():
    print("CASE\tSOLVER\tSTATUS\tTIME\tCONFLICTS\tDECISIONS")

    for path in CASES:
        clauses = read_dimacs_cnf(path)

        for name, solver in [("DPLL", dpll), ("CDCL", cdcl)]:
            status, elapsed, stats = time_solver(name, solver, clauses)
            conflicts = "-" if stats is None else stats["conflicts"]
            decisions = "-" if stats is None else stats["decisions"]
            print(f"{path}\t{name}\t{status}\t{elapsed:.6f}s\t{conflicts}\t{decisions}")


if __name__ == "__main__":
    main()
