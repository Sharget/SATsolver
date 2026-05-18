import random

from utils.general_utils import color_var


def _empty_graph(n):
    graph = {i: [] for i in range(1, n + 1)}
    return graph


def _add_edge(graph, u, v):
    graph[u].append(v)
    graph[v].append(u)


def _sort_graph(graph):
    for neighbours in graph.values():
        neighbours.sort()
    return graph


def all_possible_edges(n):
    return [(i, j) for i in range(1, n + 1) for j in range(i + 1, n + 1)]


def generate_random_graph(n, p, rng=None):
    if n <= 0:
        raise ValueError("Node count must be positive")
    if p < 0 or p > 1:
        raise ValueError("Edge probability must be between 0 and 1")

    source = rng or random
    graph = _empty_graph(n)

    for i in range(1, n + 1):
        for j in range(i + 1, n + 1):
            if source.random() < p:
                _add_edge(graph, i, j)

    return _sort_graph(graph)


def generate_random_graph_exact_edges(n, m, rng=None):
    if n <= 0:
        raise ValueError("Node count must be positive")
    if m < 0:
        raise ValueError("Edge count must not be negative")

    max_edges = n * (n - 1) // 2
    # A simple undirected graph cannot have more than this many unique edges.
    # Oversized requests are treated as "make it as dense as possible" instead
    # of crashing the app or a long benchmark sweep.
    actual_edge_count = min(m, max_edges)

    source = rng or random
    graph = _empty_graph(n)

    for u, v in source.sample(all_possible_edges(n), actual_edge_count):
        _add_edge(graph, u, v)

    return _sort_graph(graph)


def graph_edges(graph):
    return [(u, v) for u in sorted(graph) for v in graph[u] if u < v]

def generate_coloring_clauses(graph, k):
    clauses = []

    nodes = list(graph.keys())

    # -----------------------------
    # 1. fiecare nod are cel putin o culoare
    # -----------------------------
    for v in nodes:
        clauses.append([color_var(v, c, k) for c in range(1, k + 1)])

    # -----------------------------
    # 2. fiecare nod are cel mult o culoare
    # -----------------------------
    for v in nodes:
        for c1 in range(1, k + 1):
            for c2 in range(c1 + 1, k + 1):
                clauses.append([-color_var(v, c1, k), -color_var(v, c2, k)])

    # -----------------------------
    # 3. muchii: vecinii nu au aceeasi culoare
    # -----------------------------
    for u in nodes:
        for v in graph[u]:
            if u < v:  # evitam duplicate
                for c in range(1, k + 1):
                    clauses.append([
                        -color_var(u, c, k),
                        -color_var(v, c, k)
                    ])

    return clauses


def decode_coloring(solution, colors=None):
    coloring = {}

    for key, value in solution.items():
        if value:
            if colors is None:
                v = key // 100
                c = key % 100
            else:
                v = (key - 1) // colors + 1
                c = (key - 1) % colors + 1
            coloring[v] = c

    return coloring


def solve_coloring_native(graph, k):
    colors = {}

    nodes = list(graph.keys())

    def is_valid(v, c):
        for neigh in graph[v]:
            if neigh in colors and colors[neigh] == c:
                return False
        return True

    def backtrack(i=0):
        if i == len(nodes):
            return True

        v = nodes[i]

        for c in range(1, k + 1):
            if is_valid(v, c):
                colors[v] = c

                if backtrack(i + 1):
                    return True

                del colors[v]

        return False

    return colors if backtrack() else None


def solve_coloring_native_optimised(graph, k):
    colors = {}

    nodes = list(graph.keys())

    def select_unassigned():
        best = None
        best_options = float("inf")

        for v in nodes:
            if v not in colors:
                options = sum(1 for c in range(1, k+1) if is_valid(v, c))

                if options < best_options:
                    best = v
                    best_options = options

        return best
    
    def forward_check():
        for v in nodes:
            if v not in colors:
                if not any(is_valid(v, c) for c in range(1, k+1)):
                    return False
        return True

    def is_valid(v, c):
        for neigh in graph[v]:
            if neigh in colors and colors[neigh] == c:
                return False
        return True

    def backtrack(i=0):
        if i == len(nodes):
            return True

        # v = nodes[i]
        v = select_unassigned()

        for c in range(1, k + 1):
            if is_valid(v, c):
                colors[v] = c

                if backtrack(i + 1):
                    return True

                del colors[v]

        return False

    return colors if forward_check and backtrack() else None
