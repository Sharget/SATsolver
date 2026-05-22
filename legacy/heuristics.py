def choose_variable_basic(clauses, assignment):
    for clause in clauses:
        for lit in clause:
            var = abs(lit)
            if var not in assignment:
                return var
    return None


def choose_variable_smart(clauses, assignment):
    freq = {}

    for clause in clauses:
        for lit in clause:
            var = abs(lit)
            if var not in assignment:
                freq[var] = freq.get(var, 0) + 1

    return max(freq, key=freq.get) if freq else None


def choose_variable_small_clause(clauses, assignment):
    for clause in sorted(clauses, key=len):
        for lit in clause:
            var = abs(lit)
            if var not in assignment:
                return var
    return None
