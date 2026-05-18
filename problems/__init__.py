from problems.dimacs_problem import dimacs_problem_from_text
from problems.graph_coloring import (
    average_degree_graph_coloring_problem,
    edge_count_from_average_degree,
    exact_edges_graph_coloring_problem,
    graph_coloring_problem,
    random_graph_coloring_problem,
)
from problems.sudoku import sudoku_problem

__all__ = [
    "average_degree_graph_coloring_problem",
    "dimacs_problem_from_text",
    "edge_count_from_average_degree",
    "exact_edges_graph_coloring_problem",
    "graph_coloring_problem",
    "random_graph_coloring_problem",
    "sudoku_problem",
]
