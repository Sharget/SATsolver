from utils.colored_graph import generate_random_graph, generate_coloring_clauses, solve_coloring_native_optimised, solve_coloring_native, decode_coloring
from utils.dimacs import write_dimacs_cnf, read_dimacs_cnf
from solvers.dpll import dpll,dpll_debug
import time
import os
import matplotlib.pyplot as plt

# 🎯 Ce înseamnă n, p (sau d), k la tine
# 🧩 1. n = numărul de noduri
# n = |V|
# câte noduri are graful
# controlează dimensiunea problemei

# 👉 exemplu:

# n = 20 → graf cu 20 noduri
# 🌐 2. p = probabilitatea de muchie (sau densitatea)

# Tu ai folosit:

# generate_random_graph(n, p)

# 👉 deci:

# p ∈ [0,1]
# probabilitatea ca o muchie să existe între două noduri
# controlează cât de dens e graful
# 🔁 echivalent cu „d” (densitate)

# Poți gândi:

# d ≈ p

# sau mai formal:

# d = |E| / (n(n-1)/2)
# 🎯 interpretare:
# p / d	tip graf	dificultate
# 0.1	rar (sparse)	ușor
# 0.3	mediu	interesant
# 0.5	dens	greu
# 🎨 3. k = număr de culori
# k = numărul de culori disponibile

# 👉 controlează dacă problema e:

# SAT (există soluție)
# UNSAT (nu există)
# 🎯 interpretare:
# k	dificultate
# 2	foarte greu / des UNSAT
# 3	mediu
# 4+	mai ușor


# Colorarea grafului
# Definim problema
# x(v, c) = nodul v are culoarea c
# N
# n mic → ușor
# n mare → greu
sizes = [10, 20, 30, 35, 40] 

# Graph Desity
# p = 0.1 → sparse graph (ușor)
# p = 0.5 → dense graph (greu)
density = [0.1, 0.3, 0.5]

# Colors 
# k = 2 → foarte greu (de multe ori UNSAT)
# k = 3 → mediu
# k = 4 → mai ușor
colors = [2, 3, 4, 5]


# -----------------------------
# 1. PROBLEMA (CLASA)
# -----------------------------
class GraphColoringProblem:
    def __init__(self, graph, k, name="", p=None):
        self.graph = graph
        self.k = k
        self.name = name
        self.p = p

def generate_graph_coloring_dataset():
    file_location = "input/graph_coloring"

    os.makedirs(file_location, exist_ok=True)

    for n in sizes:
        for p in density:
            graph = generate_random_graph(n, p)

            for k in colors:
                clauses = generate_coloring_clauses(graph, k)

                filename = f"{file_location}/gc_n{n}_p{int(p*100)}_k{k}.cnf"

                write_dimacs_cnf(filename, clauses)

                print(f"generated {filename}")

# -----------------------------
# 6. BENCHMARK RUNNER
# -----------------------------
results = []

def run_case(problem, repeats = 5, index=None, total=None):
    name = problem.name

    sat_times = []
    native_times = []

    n = len(problem.graph)
    k = problem.k
    edges = sum(len(v) for v in problem.graph.values()) // 2

    print("\n" + "="*50)
    if index is not None:
        print(f"[{index}/{total}] Running case: {name} (x{repeats})")
    else:
        print(f"Running case: {name} (x{repeats})")

    print(f"Nodes (n): {n}, Edges: {edges}, Colors (k): {k}")

    for i in range(repeats):
        print(f"-> iteration {i+1}/{repeats}")
        graph = generate_random_graph(n, problem.p)
        temp_problem = GraphColoringProblem(graph, k, name)

        # ---------------- SAT ----------------
        print("   -> Generating CNF...")
        clauses = generate_coloring_clauses(temp_problem.graph, temp_problem.k)
        print(f"      Clauses: {len(clauses)}")

        print("   -> Running SAT solver...")
        start = time.time()
        dpll(clauses)
        sat_time = time.time() - start
        sat_times.append(sat_time)
        print(f"      SAT time: {sat_time:.5f}s")

        # ---------------- SAT ----------------
        print("   -> Running native solver...")
        start = time.time()
        # solve_coloring_native(problem.graph, problem.k)
        solve_coloring_native_optimised(temp_problem.graph, temp_problem.k)
        native_time = time.time() - start
        native_times.append(native_time)
        print(f"      Native time: {native_time:.5f}s")

    avg_sat = sum(sat_times) / len(sat_times)
    avg_native = sum(native_times) / len(native_times)
    print("-"*35)
    print(f"  -> AVG SAT: {avg_sat:.5f}s")
    print(f"  -> AVG NATIVE: {avg_native:.5f}s")

    results.append((name, avg_sat, avg_native))

# -----------------------------
# 7. GENERARE CAZURI
# -----------------------------
def generate_cases():
    cases = []

    for n in sizes:
        for p in density:
            for k in colors:

                graph = generate_random_graph(n, p)
                name = f"n{n}_p{int(p*100)}_k{k}"

                problem = GraphColoringProblem(graph, k, name, p)
                cases.append(problem)

    return cases


# -----------------------------
# 8. PRINT + PLOT
# -----------------------------
def print_table():
    print("\nRESULTS:")
    print("CASE\t\tSAT\tNATIVE")

    for name, sat, nat in results:
        print(f"{name}\t{sat:.5f}\t{nat:.5f}")


def plot_results():
    names = [r[0] for r in results]
    sat = [r[1] for r in results]
    nat = [r[2] for r in results]

    x = range(len(names))

    plt.plot(x, sat, label="SAT (DPLL)")
    plt.plot(x, nat, label="Native")

    plt.xticks(x, names, rotation=45)
    plt.legend()
    plt.title("Graph Coloring Benchmark - Normal ")
    plt.tight_layout()
    plt.show()

def plot_results_log():
    names = [r[0] for r in results]
    sat = [r[1] for r in results]
    nat = [r[2] for r in results]
    # sat = [max(r[1], 1e-6) for r in results]
    # nat = [max(r[2], 1e-6) for r in results]

    x = range(len(names))

    plt.plot(x, sat, label="SAT (DPLL)")
    plt.plot(x, nat, label="Native")

    plt.yscale("log")  # 🔥 asta e cheia

    plt.xticks(x, names, rotation=45)
    plt.ylabel("Time (log scale)")
    plt.title("Graph Coloring Benchmark - Log Scale")
    plt.legend()

    plt.tight_layout()
    plt.show()

def plot_log_separate():
    names = [r[0] for r in results]
    sat = [max(r[1], 1e-6) for r in results]
    nat = [max(r[2], 1e-6) for r in results]

    x = range(len(names))

    plt.plot(x, sat, marker='o', label="SAT")
    plt.plot(x, nat, marker='x', label="Native")

    plt.yscale("log")

    plt.xticks(x, names, rotation=45)
    plt.ylabel("Time (log scale)")
    plt.title("SAT vs Native (Log Scale) - Separate")
    plt.legend()

    plt.tight_layout()
    plt.show()

def plot_speedup():
    names = [r[0] for r in results]
    speedup = [r[2] / max(r[1], 1e-6) for r in results]  # native / sat

    x = range(len(names))

    plt.plot(x, speedup, marker='o')
    plt.yscale("log")

    plt.xticks(x, names, rotation=45)
    plt.ylabel("Speedup (Native / SAT)")
    plt.title("Speedup Comparison")

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    # generate_graph_coloring_dataset()

    # formula_gc = read_dimacs_cnf("input/graph_coloring/gc_n80_p10_k4.cnf")
    
    # sol = dpll_debug(formula_gc)
    # print (sol)
    # print(decode_coloring(sol))

    

    cases = generate_cases()
    total = len(cases)

    print(f"Total test cases: {total}")

    for i, problem in enumerate(cases, start=1):
        run_case(problem, repeats=5, index=i, total=total)


    print_table()
    plot_results()
    plot_results_log()
    plot_log_separate()
    plot_speedup()
    