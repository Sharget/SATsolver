import os


def clear_console():
    # 'nt' is for Windows, 'posix' is for macOS and Linux.
    os.system("cls" if os.name == "nt" else "clear")


def indent(level):
    return "  " * level


def sudoku_var(r, c, v):
    """
    Encode a Sudoku variable as one integer.

    Meaning: row r, column c, value v is true.
    Example: (1, 2, 3) -> 10203
    """
    return (r * 10000) + (c * 100) + v


def color_var(node, color, colors=None):
    """
    Encode a graph-coloring variable as one integer.

    New graph-coloring encoders should pass the total number of colors, which
    gives a compact collision-free mapping:
    (node - 1) * colors + color.

    The two-argument form is kept only for old generated files/scripts.
    """
    if colors is not None:
        return (node - 1) * colors + color

    return (node * 100) + color


def var(*args):
    """
    Backwards-compatible encoder.

    New code should call sudoku_var(...) or color_var(...) directly, because
    those names explain which SAT encoding is being used.
    """
    if len(args) == 3:
        return sudoku_var(*args)
    if len(args) == 2:
        return color_var(*args)
    raise TypeError("var expects either 2 arguments for graph coloring or 3 for Sudoku")
