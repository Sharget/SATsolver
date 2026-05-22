"""Compatibility imports for older graph-coloring scripts.

Active product code should import graph helpers from ``utils.graph_utils``.
"""

from utils.graph_utils import (
    all_possible_edges,
    decode_coloring,
    generate_coloring_clauses,
    generate_random_graph,
    generate_random_graph_exact_edges,
    graph_edges,
)


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

    def is_valid(v, c):
        for neigh in graph[v]:
            if neigh in colors and colors[neigh] == c:
                return False
        return True

    def select_unassigned():
        best = None
        best_options = float("inf")

        for v in nodes:
            if v not in colors:
                options = sum(1 for c in range(1, k + 1) if is_valid(v, c))

                if options < best_options:
                    best = v
                    best_options = options

        return best

    def forward_check():
        for v in nodes:
            if v not in colors and not any(is_valid(v, c) for c in range(1, k + 1)):
                return False
        return True

    def backtrack(i=0):
        if i == len(nodes):
            return True

        v = select_unassigned()

        for c in range(1, k + 1):
            if is_valid(v, c):
                colors[v] = c

                if forward_check() and backtrack(i + 1):
                    return True

                del colors[v]

        return False

    return colors if forward_check() and backtrack() else None
