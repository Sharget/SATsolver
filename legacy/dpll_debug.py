from legacy import colored_text as txt
from utils.general_utils import indent


def choose_variable_basic(clauses, assignment):
    for clause in clauses:
        for lit in clause:
            var = abs(lit)
            if var not in assignment:
                return var
    return None


def unit_propagate_debug(clauses, assignment):
    changed = True

    while changed:
        changed = False

        for clause in clauses:
            if len(clause) == 1:
                lit = clause[0]
                var = abs(lit)
                val = lit > 0

                print(txt.YELLOW + f"Unit clause found: {clause}" + txt.RESET)

                if var in assignment:
                    if assignment[var] != val:
                        print(txt.RED + "Conflict in unit propagation!" + txt.RESET)
                        return None
                else:
                    print(txt.GREEN + f"Assign {var} = {val} (unit propagation)" + txt.RESET)
                    assignment[var] = val
                    changed = True

                    new_clauses = []

                    for current in clauses:
                        if lit in current:
                            print(txt.CYAN + f"Clause satisfied and removed: {current}" + txt.RESET)
                            continue

                        if -lit in current:
                            new_clause = [item for item in current if item != -lit]
                            print(txt.YELLOW + f"Removing {-lit} from {current} -> {new_clause}" + txt.RESET)

                            if not new_clause:
                                print(txt.RED + "Empty clause after propagation!" + txt.RESET)
                                return None

                            new_clauses.append(new_clause)
                        else:
                            new_clauses.append(current)

                    clauses = new_clauses
                    break

    return clauses, assignment


def dpll_debug(clauses, assignment=None, level=0, choose_var_fn=None):
    """
    Return a satisfying assignment dict when SAT, otherwise None.
    Prints recursive search steps for manual/legacy debugging.
    """
    if assignment is None:
        assignment = {}

    if choose_var_fn is None:
        choose_var_fn = choose_variable_basic

    print(indent(level) + txt.BOLD + txt.CYAN + "Entering DPLL" + txt.RESET)

    result = unit_propagate_debug(clauses, assignment.copy())

    if result is None:
        print(indent(level) + txt.RED + "Conflict after propagation -> BACKTRACK" + txt.RESET)
        return None

    clauses, assignment = result

    print("\n" + "-" * level + "-" * txt.separator_lenght)
    print(indent(level) + txt.BLUE + f"Clauses: {clauses}" + txt.RESET)
    print(indent(level) + txt.GREEN + f"Assignment: {assignment}" + txt.RESET)
    print("-" * level + "-" * txt.separator_lenght)

    if not clauses:
        print(txt.BOLD + txt.RED + f"level = {level}" + txt.RESET)
        print(indent(level) + txt.GREEN + "SAT FOUND" + txt.RESET)
        return assignment

    var = choose_var_fn(clauses, assignment)
    print(indent(level) + txt.YELLOW + f"Choose variable: {var}" + txt.RESET)

    for value in (True, False):
        print(indent(level) + txt.CYAN + f"Trying {var} = {value}" + txt.RESET)

        new_assignment = assignment.copy()
        new_assignment[var] = value

        lit = var if value else -var
        new_clauses = []

        for current in clauses:
            if lit in current:
                continue

            if -lit in current:
                new_clause = [item for item in current if item != -lit]

                if not new_clause:
                    print(indent(level) + txt.RED + "Empty clause -> conflict" + txt.RESET)
                    break

                new_clauses.append(new_clause)
            else:
                new_clauses.append(current)

        else:
            result = dpll_debug(new_clauses, new_assignment, level + 1, choose_var_fn)

            if result is not None:
                return result

        print(indent(level) + txt.RED + f"Backtracking on {var} = {value}" + txt.RESET)

    return None
