from problems.dimacs_problem import dimacs_problem_from_text
from problems.graph_coloring import (
    average_degree_graph_coloring_problem,
    exact_edges_graph_coloring_problem,
    manual_graph_coloring_problem,
    random_graph_coloring_problem,
)
from problems.sudoku import sudoku_problem


PROBLEM_TYPES = {
    "Sudoku": sudoku_problem,
    "Graph Coloring Manual": manual_graph_coloring_problem,
    "Graph Coloring Random": random_graph_coloring_problem,
    "Graph Coloring Exact Edges": exact_edges_graph_coloring_problem,
    "Graph Coloring Average Degree": average_degree_graph_coloring_problem,
    "DIMACS": dimacs_problem_from_text,
}
