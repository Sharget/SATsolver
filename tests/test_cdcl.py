import unittest

from solvers.cdcl import cdcl
from solvers.dpll import dpll
from utils.dimacs import read_dimacs_cnf
from utils.general_utils import color_var, sudoku_var
from utils.sudoku_general import generate_sudoku_clauses


def satisfies(clauses, model):
    if model is None:
        return False

    for clause in clauses:
        clause_ok = False

        for lit in clause:
            value = model.get(abs(lit))
            if value is None:
                continue
            if (lit > 0 and value) or (lit < 0 and not value):
                clause_ok = True
                break

        if not clause_ok:
            return False

    return True


class CDCLTests(unittest.TestCase):
    def test_unit_sat(self):
        formula = [[1]]
        solution = cdcl(formula)

        self.assertIsNotNone(solution)
        self.assertTrue(solution[1])
        self.assertTrue(satisfies(formula, solution))

    def test_unit_unsat(self):
        self.assertIsNone(cdcl([[1], [-1]]))

    def test_implication_chain_sat(self):
        formula = [[1], [-1, 2], [-2, 3]]
        solution = cdcl(formula)

        self.assertIsNotNone(solution)
        self.assertTrue(solution[1])
        self.assertTrue(solution[2])
        self.assertTrue(solution[3])
        self.assertTrue(satisfies(formula, solution))

    def test_conflict_learning_unsat(self):
        # This formula has no unit clauses at the start. The solver must make
        # a decision, hit a conflict, learn, backjump, and then prove UNSAT.
        formula = [
            [1, 2],
            [1, -2],
            [-1, 2],
            [-1, -2],
        ]

        solution, stats = cdcl(formula, return_stats=True)

        self.assertIsNone(solution)
        self.assertEqual(stats["status"], "UNSAT")
        self.assertGreaterEqual(stats["learned_clauses"], 1)

    def test_graph_coloring_dimacs_matches_dpll(self):
        formula = read_dimacs_cnf("input/examples/graph_coloring/gc_n10_p10_k2.cnf")
        cdcl_solution = cdcl(formula)
        dpll_solution = dpll(formula)

        self.assertEqual(cdcl_solution is None, dpll_solution is None)
        if cdcl_solution is not None:
            self.assertTrue(satisfies(formula, cdcl_solution))

    def test_encoder_split_and_sudoku_generation(self):
        self.assertEqual(sudoku_var(1, 2, 3), 10203)
        self.assertEqual(color_var(2, 3, 10), 13)

        grid = [[0] * 4 for _ in range(4)]
        clauses = generate_sudoku_clauses(grid)

        self.assertIn([sudoku_var(1, 1, 1), sudoku_var(1, 1, 2), sudoku_var(1, 1, 3), sudoku_var(1, 1, 4)], clauses)


if __name__ == "__main__":
    unittest.main()
