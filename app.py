from __future__ import annotations

import queue
import threading
import multiprocessing as mp
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover - the app still runs without charts.
    Figure = None
    FigureCanvasTkAgg = None

from problems.dimacs_problem import dimacs_problem_from_text
from problems.graph_coloring import (
    average_degree_graph_coloring_problem,
    exact_edges_graph_coloring_problem,
    manual_graph_coloring_problem,
    random_graph_coloring_problem,
)
from problems.hamiltonian_path import (
    average_degree_hamiltonian_path_problem,
    exact_edges_hamiltonian_path_problem,
    manual_hamiltonian_path_problem,
    random_hamiltonian_path_problem,
)
from problems.independent_set import (
    average_degree_independent_set_problem,
    exact_edges_independent_set_problem,
    manual_independent_set_problem,
    random_independent_set_problem,
)
from problems.n_queens import n_queens_problem
from problems.sudoku import sudoku_problem
from sat_core.benchmark import SUDOKU_BENCHMARK_SIZES, write_benchmark_csv
from sat_core.dimacs import clauses_to_dimacs, load_dimacs, save_dimacs
from sat_core.models import BenchmarkRow, ProblemInstance
from sat_core.process_workers import benchmark_process, generate_cnf_process, solve_process
from sat_core.runtime import (
    EVENT_CANCELLED,
    EVENT_CNF,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_LOG,
    EVENT_PROGRESS,
    EVENT_RESULT,
    EVENT_ROW,
    RunEvent,
    RunToken,
)
from sat_core.solver_runner import SOLVERS


INPUT_GENERATED = Path("input/generated")
BENCHMARK_OUTPUT = Path("output/benchmarks")
SUDOKU_SIZES = (4, 9, 16, 25)
PROBLEM_KINDS = ("Sudoku", "Graph Coloring", "N-Queens", "Hamiltonian Path", "Independent Set", "DIMACS/CNF")
BENCHMARK_PROBLEMS = ("Graph Coloring", "Sudoku", "N-Queens", "Hamiltonian Path", "Independent Set")
GRAPH_PROBLEM_KINDS = ("Graph Coloring", "Hamiltonian Path", "Independent Set")
PROBLEM_DESCRIPTIONS = {
    "Sudoku": "Fill an n x n grid so each row, column, and square box contains every value exactly once.",
    "Graph Coloring": "Assign one of k colors to each node so adjacent nodes never share the same color.",
    "N-Queens": "Place n queens on an n x n chessboard so no two queens attack each other.",
    "Hamiltonian Path": "Find a path through an undirected graph that visits every node exactly once.",
    "Independent Set": "Choose at least k graph nodes so no two chosen nodes are connected by an edge.",
    "DIMACS/CNF": "Paste or load SAT clauses directly in DIMACS CNF format.",
}


def parse_int_list(text: str) -> list[int]:
    values = [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]
    return [int(value) for value in values]


def parse_float_list(text: str) -> list[float]:
    values = [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]
    return [float(value) for value in values]


def parse_timeout_seconds(text: str) -> float | None:
    raw = text.strip()
    if not raw:
        return None

    timeout = float(raw)
    return timeout if timeout > 0 else None


class SATApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SAT Problem Solver")
        self.root.geometry("1650x980")

        INPUT_GENERATED.mkdir(parents=True, exist_ok=True)
        BENCHMARK_OUTPUT.mkdir(parents=True, exist_ok=True)

        self.current_problem: ProblemInstance | None = None
        self.benchmark_rows: list[BenchmarkRow] = []
        self.benchmark_canvas = None
        self.benchmark_figure = None
        self.event_queue: queue.Queue[RunEvent] = queue.Queue()
        self.active_token: RunToken | None = None
        self.active_thread: threading.Thread | None = None
        self.active_process: mp.Process | None = None
        self.active_process_cancel = None
        self.active_process_skip = None
        self.run_active = False
        self.pending_chart_refresh = False
        self.controls_to_disable = []

        self._build_layout()
        self.root.after(100, self._poll_run_events)

    def _build_layout(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.solve_tab = ttk.Frame(self.notebook, padding=10)
        self.benchmark_tab = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.solve_tab, text="Solve")
        self.notebook.add(self.benchmark_tab, text="Benchmarks")
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_solve_tab()
        self._build_benchmark_tab()
        self._build_runtime_panel()

    def _build_runtime_panel(self) -> None:
        panel = ttk.LabelFrame(self.root, text="Run Feed", padding=8)
        panel.pack(fill=tk.X, padx=10, pady=(0, 10))
        panel.columnconfigure(1, weight=1)

        self.run_status = tk.StringVar(value="Ready")
        self.progress_value = tk.DoubleVar(value=0)

        ttk.Label(panel, textvariable=self.run_status, width=30).grid(row=0, column=0, sticky="w")
        self.progress_bar = ttk.Progressbar(panel, variable=self.progress_value, maximum=100)
        self.progress_bar.grid(row=0, column=1, sticky="ew", padx=(8, 8))

        self.cancel_button = ttk.Button(panel, text="Cancel", command=self.cancel_active_run, state=tk.DISABLED)
        self.cancel_button.grid(row=0, column=2, padx=(0, 6))
        ttk.Button(panel, text="Clear Feed", command=self.clear_feed).grid(row=0, column=3)

        self.feed_text = tk.Text(panel, height=7, wrap="word", state=tk.DISABLED)
        self.feed_text.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        feed_scroll = ttk.Scrollbar(panel, orient=tk.VERTICAL, command=self.feed_text.yview)
        feed_scroll.grid(row=1, column=4, sticky="ns", pady=(8, 0))
        self.feed_text.configure(yscrollcommand=feed_scroll.set)

    def clear_feed(self) -> None:
        self.feed_text.configure(state=tk.NORMAL)
        self.feed_text.delete("1.0", tk.END)
        self.feed_text.configure(state=tk.DISABLED)

    def append_feed(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.feed_text.configure(state=tk.NORMAL)
        self.feed_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.feed_text.see(tk.END)
        self.feed_text.configure(state=tk.DISABLED)

    def _set_run_active(self, active: bool, status: str = "Ready") -> None:
        self.run_active = active
        self.run_status.set(status)
        self.cancel_button.configure(state=tk.NORMAL if active else tk.DISABLED)

        for control in self.controls_to_disable:
            try:
                control.configure(state=tk.DISABLED if active else tk.NORMAL)
            except tk.TclError:
                pass

        if active:
            self.progress_value.set(0)

        self._refresh_skip_button_state()

    def _refresh_skip_button_state(self) -> None:
        if not hasattr(self, "skip_benchmark_button"):
            return

        state = tk.NORMAL if self.run_active and self.active_process_skip is not None else tk.DISABLED
        self.skip_benchmark_button.configure(state=state)

    def _queue_event(self, event: RunEvent) -> None:
        self.event_queue.put(event)

    def _start_worker(self, name: str, target) -> None:
        if self.run_active:
            messagebox.showinfo("Run already active", "Cancel or wait for the current run to finish.")
            return

        token = RunToken()
        self.active_token = token
        self._set_run_active(True, name)
        self.append_feed(name)

        def wrapped() -> None:
            try:
                target(token, self._queue_event)
            except Exception as exc:
                self._queue_event(RunEvent(EVENT_ERROR, str(exc)))
            finally:
                if token.is_cancelled():
                    self._queue_event(RunEvent(EVENT_CANCELLED, "Run cancelled."))
                else:
                    self._queue_event(RunEvent(EVENT_DONE, "Run finished."))

        self.active_thread = threading.Thread(target=wrapped, daemon=True)
        self.active_thread.start()

    def _start_process_worker(
        self,
        name: str,
        process_target,
        *args,
        extra_events=(),
        benchmark_skip_event=None,
    ) -> None:
        if self.run_active:
            messagebox.showinfo("Run already active", "Cancel or wait for the current run to finish.")
            return

        process_queue = mp.Queue()
        cancel_event = mp.Event()
        process = mp.Process(target=process_target, args=(*args, *extra_events, process_queue, cancel_event), daemon=True)

        self.active_process = process
        self.active_process_cancel = cancel_event
        self.active_process_skip = benchmark_skip_event
        self._set_run_active(True, name)
        self.append_feed(name)

        def supervise() -> None:
            process.start()

            while process.is_alive() or not process_queue.empty():
                try:
                    event = process_queue.get(timeout=0.05)
                    self._queue_event(event)
                except queue.Empty:
                    pass

            process.join(timeout=0.2)

            if cancel_event.is_set():
                self._queue_event(RunEvent(EVENT_CANCELLED, "Run cancelled."))
            elif process.exitcode not in (0, None):
                self._queue_event(RunEvent(EVENT_ERROR, f"Worker process exited with code {process.exitcode}"))
            else:
                self._queue_event(RunEvent(EVENT_DONE, "Run finished."))

        self.active_thread = threading.Thread(target=supervise, daemon=True)
        self.active_thread.start()

    def cancel_active_run(self) -> None:
        if self.active_token is None or not self.run_active:
            if self.active_process_cancel is None or not self.run_active:
                return

        if self.active_token is not None:
            self.active_token.cancel()
        if self.active_process_cancel is not None:
            self.active_process_cancel.set()

        self.run_status.set("Cancelling...")
        self.append_feed("Cancel requested; stopping after current solver checkpoint.")
        self.root.after(1500, self._terminate_process_if_needed)

    def skip_current_benchmark_case(self) -> None:
        if not self.run_active or self.active_process_skip is None:
            return

        self.active_process_skip.set()
        self.run_status.set("Skipping current benchmark case...")
        self.append_feed("Skip requested; current benchmark case will be marked SKIPPED at the next solver checkpoint.")

    def _terminate_process_if_needed(self) -> None:
        process = self.active_process
        if process is not None and process.is_alive():
            self.append_feed("Worker still running; terminating process.")
            process.terminate()

    def _poll_run_events(self) -> None:
        processed = 0

        while processed < 50:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            self._handle_run_event(event)
            processed += 1

        self.root.after(30, self._poll_run_events)

    def _handle_run_event(self, event: RunEvent) -> None:
        if event.type == EVENT_LOG:
            self.append_feed(event.message)
            return

        if event.type == EVENT_PROGRESS:
            self._apply_progress(event)
            return

        if event.type == EVENT_ROW:
            row = event.payload.get("row")
            if row is not None:
                self.benchmark_rows.append(row)
                self._insert_benchmark_row(row)
            self._apply_progress(event)
            return

        if event.type == EVENT_CNF:
            self._apply_cnf_event(event)
            return

        if event.type == EVENT_RESULT:
            result = event.payload.get("result")
            if result is not None:
                self._write_result(self._format_solve_result(result))
                self.progress_value.set(100)
            return

        if event.type == EVENT_ERROR:
            self.append_feed(f"ERROR: {event.message}")
            messagebox.showerror("Run failed", event.message)
            return

        if event.type == EVENT_CANCELLED:
            self.append_feed(event.message or "Run cancelled.")
            self._finish_run("Cancelled")
            return

        if event.type == EVENT_DONE:
            self.append_feed(event.message or "Run finished.")
            self._finish_run("Ready")

    def _apply_progress(self, event: RunEvent) -> None:
        if event.total:
            self.progress_value.set((event.current or 0) * 100 / event.total)
        if event.message:
            self.run_status.set(event.message)

    def _finish_run(self, status: str) -> None:
        if not self.run_active:
            return

        self._set_run_active(False, status)
        self.active_token = None
        self.active_thread = None
        self.active_process = None
        self.active_process_cancel = None
        self.active_process_skip = None
        self._refresh_skip_button_state()

        if self.pending_chart_refresh:
            self.pending_chart_refresh = False
            if len(self.benchmark_rows) <= 120:
                self.draw_benchmark_chart()
            else:
                self.append_feed("Chart auto-refresh skipped for a large benchmark; use Refresh Chart when you are ready.")

    def _apply_cnf_event(self, event: RunEvent) -> None:
        payload = event.payload
        problem_data = payload["problem"]
        self.current_problem = ProblemInstance(
            name=problem_data["name"],
            problem_type=problem_data["problem_type"],
            clauses=problem_data["clauses"],
            metadata=problem_data.get("metadata", {}),
        )
        self.cnf_text.delete("1.0", tk.END)
        self.cnf_text.insert("1.0", payload["dimacs"])
        self._write_result(f"Generated {self.current_problem.clause_count} clauses for {self.current_problem.name}.")

    def _build_solve_tab(self) -> None:
        self.solve_tab.columnconfigure(0, weight=0)
        self.solve_tab.columnconfigure(1, weight=1)
        self.solve_tab.rowconfigure(0, weight=1)

        left = ttk.Frame(self.solve_tab)
        right = ttk.Frame(self.solve_tab)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        controls = ttk.LabelFrame(left, text="Problem", padding=8)
        controls.pack(fill=tk.X)

        self.problem_kind = tk.StringVar(value="Sudoku")
        ttk.Label(controls, text="Type").grid(row=0, column=0, sticky="w")
        problem_box = ttk.Combobox(
            controls,
            textvariable=self.problem_kind,
            values=PROBLEM_KINDS,
            state="readonly",
            width=24,
        )
        problem_box.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        problem_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_problem_form())

        self.problem_description = tk.StringVar()
        ttk.Label(
            controls,
            textvariable=self.problem_description,
            wraplength=250,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.solver_name = tk.StringVar(value="CDCL")
        ttk.Label(controls, text="Solver").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            controls,
            textvariable=self.solver_name,
            values=SOLVERS,
            state="readonly",
            width=24,
        ).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        self.solve_timeout_seconds = tk.StringVar(value="30")
        ttk.Label(controls, text="Timeout (s)").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(
            controls,
            textvariable=self.solve_timeout_seconds,
            width=24,
        ).grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        self.advanced_solver_logs = tk.BooleanVar(value=False)
        self.solver_log_level = tk.StringVar(value="Periodic progress")
        ttk.Checkbutton(
            controls,
            text="Advanced solver logs",
            variable=self.advanced_solver_logs,
            command=self._refresh_solver_log_controls,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.solver_log_label = ttk.Label(controls, text="Log detail")
        self.solver_log_label.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.solver_log_box = ttk.Combobox(
            controls,
            textvariable=self.solver_log_level,
            values=("Periodic progress", "Verbose debug"),
            state=tk.DISABLED,
            width=24,
        )
        self.solver_log_box.grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        self.problem_form = ttk.LabelFrame(left, text="Input", padding=8)
        self.problem_form.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        buttons = ttk.Frame(left)
        buttons.pack(fill=tk.X, pady=(10, 0))
        self.generate_button = ttk.Button(buttons, text="Generate CNF", command=self.generate_cnf)
        self.solve_button = ttk.Button(buttons, text="Solve", command=self.solve_current)
        self.save_cnf_button = ttk.Button(buttons, text="Save CNF", command=self.save_cnf_dialog)
        self.load_dimacs_button = ttk.Button(buttons, text="Load DIMACS", command=self.load_dimacs_dialog)

        for button, padding in [
            (self.generate_button, 0),
            (self.solve_button, 6),
            (self.save_cnf_button, 6),
            (self.load_dimacs_button, 6),
        ]:
            button.pack(fill=tk.X, pady=(padding, 0))
            self.controls_to_disable.append(button)

        ttk.Label(right, text="CNF Preview").grid(row=0, column=0, sticky="w")
        self.cnf_text = tk.Text(right, height=22, wrap="none")
        self.cnf_text.grid(row=1, column=0, sticky="nsew", pady=(4, 10))
        yscroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.cnf_text.yview)
        yscroll.grid(row=1, column=1, sticky="ns", pady=(4, 10))
        self.cnf_text.configure(yscrollcommand=yscroll.set)

        ttk.Label(right, text="Result").grid(row=2, column=0, sticky="w")
        self.result_text = tk.Text(right, height=13, wrap="word")
        self.result_text.grid(row=3, column=0, sticky="nsew", pady=(4, 0))
        result_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.result_text.yview)
        result_scroll.grid(row=3, column=1, sticky="ns", pady=(4, 0))
        self.result_text.configure(yscrollcommand=result_scroll.set)

        self._refresh_problem_form()
        self._refresh_solver_log_controls()

    def _clear_form(self) -> None:
        for child in self.problem_form.winfo_children():
            child.destroy()

    def _refresh_solver_log_controls(self) -> None:
        if self.advanced_solver_logs.get():
            self.solver_log_box.configure(state="readonly")
        else:
            self.solver_log_box.configure(state=tk.DISABLED)

    def _refresh_problem_form(self) -> None:
        self._clear_form()
        kind = self.problem_kind.get()
        self.problem_description.set(PROBLEM_DESCRIPTIONS.get(kind, ""))

        if kind == "Sudoku":
            self._build_sudoku_form()
        elif kind in GRAPH_PROBLEM_KINDS:
            self._build_graph_form()
        elif kind == "N-Queens":
            self._build_n_queens_form()
        else:
            self._build_dimacs_form()

    def _build_sudoku_form(self) -> None:
        self.sudoku_size = tk.IntVar(value=4)
        top = ttk.Frame(self.problem_form)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Size").pack(side=tk.LEFT)
        size_box = ttk.Combobox(top, textvariable=self.sudoku_size, values=SUDOKU_SIZES, state="readonly", width=6)
        size_box.pack(side=tk.LEFT, padx=(8, 0))
        size_box.bind("<<ComboboxSelected>>", lambda _event: self._build_sudoku_grid())
        ttk.Button(top, text="Clear", command=lambda: self._build_sudoku_grid()).pack(side=tk.RIGHT)

        self.sudoku_grid_frame = ttk.Frame(self.problem_form)
        self.sudoku_grid_frame.pack(pady=(10, 0))
        self.sudoku_entries: list[list[ttk.Entry]] = []
        self._build_sudoku_grid()

    def _build_sudoku_grid(self) -> None:
        for child in self.sudoku_grid_frame.winfo_children():
            child.destroy()

        size = int(self.sudoku_size.get())
        self.sudoku_entries = []

        for r in range(size):
            row_entries = []
            for c in range(size):
                entry = ttk.Entry(self.sudoku_grid_frame, width=3, justify="center")
                entry.grid(row=r, column=c, padx=1, pady=1)
                row_entries.append(entry)
            self.sudoku_entries.append(row_entries)

    def _build_n_queens_form(self) -> None:
        fields = ttk.Frame(self.problem_form)
        fields.pack(fill=tk.X)
        self.n_queens_size = tk.StringVar(value="8")

        ttk.Label(fields, text="Board size n").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(fields, textvariable=self.n_queens_size, width=12).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)

    def _build_graph_form(self) -> None:
        self.graph_mode = tk.StringVar(value="Manual")
        self.graph_field_entries = {}
        mode_row = ttk.Frame(self.problem_form)
        mode_row.pack(fill=tk.X)
        ttk.Radiobutton(mode_row, text="Manual", variable=self.graph_mode, value="Manual", command=self._refresh_graph_controls).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="G(n,p)", variable=self.graph_mode, value="Probability", command=self._refresh_graph_controls).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Radiobutton(mode_row, text="G(n,m)", variable=self.graph_mode, value="Exact edges", command=self._refresh_graph_controls).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Radiobutton(mode_row, text="G(n,d)", variable=self.graph_mode, value="Average degree", command=self._refresh_graph_controls).pack(side=tk.LEFT, padx=(12, 0))

        fields = ttk.Frame(self.problem_form)
        fields.pack(fill=tk.X, pady=(10, 0))
        self.graph_nodes = tk.StringVar(value="10")
        self.graph_colors = tk.StringVar(value="3")
        self.graph_target = tk.StringVar(value="3")
        self.graph_probability = tk.StringVar(value="0.3")
        self.graph_edge_count = tk.StringVar(value="10")
        self.graph_average_degree = tk.StringVar(value="4")
        self.graph_seed = tk.StringVar(value="")

        labels = [("nodes", "Nodes", self.graph_nodes)]
        if self.problem_kind.get() == "Graph Coloring":
            labels.append(("colors", "Colors", self.graph_colors))
        if self.problem_kind.get() == "Independent Set":
            labels.append(("target", "Target k", self.graph_target))
        labels.extend([
            ("probability", "Probability p", self.graph_probability),
            ("edge_count", "Exact edges m", self.graph_edge_count),
            ("average_degree", "Average degree d", self.graph_average_degree),
            ("seed", "Seed", self.graph_seed),
        ])

        for row, (key, label, variable) in enumerate(labels):
            ttk.Label(fields, text=label).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(fields, textvariable=variable, width=12)
            entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
            self.graph_field_entries[key] = entry

        self.graph_edge_label = ttk.Label(self.problem_form, text="Manual edges: 1-2, 2-3")
        self.graph_edge_label.pack(anchor="w", pady=(10, 2))
        self.edge_text = tk.Text(self.problem_form, height=7, width=32)
        self.edge_text.pack(fill=tk.BOTH, expand=True)
        self.edge_text.insert("1.0", "1-2, 2-3, 3-4")
        self._refresh_graph_controls()

    def _refresh_graph_controls(self) -> None:
        if not hasattr(self, "graph_field_entries"):
            return

        mode = self.graph_mode.get()
        active_by_key = {
            "nodes": True,
            "colors": True,
            "target": True,
            "probability": mode == "Probability",
            "edge_count": mode == "Exact edges",
            "average_degree": mode == "Average degree",
            "seed": mode != "Manual",
        }

        for key, entry in self.graph_field_entries.items():
            entry.configure(state=tk.NORMAL if active_by_key.get(key, False) else tk.DISABLED)

        manual = mode == "Manual"
        if hasattr(self, "edge_text"):
            self.edge_text.configure(state=tk.NORMAL if manual else tk.DISABLED)

    def _build_dimacs_form(self) -> None:
        ttk.Label(self.problem_form, text="Paste DIMACS or plain CNF clauses").pack(anchor="w")
        self.dimacs_input = tk.Text(self.problem_form, height=18, width=36)
        self.dimacs_input.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.dimacs_input.insert("1.0", "p cnf 2 2\n1 2 0\n-1 2 0\n")

    def _read_sudoku_grid(self) -> list[list[int]]:
        grid = []

        for row_entries in self.sudoku_entries:
            row = []
            for entry in row_entries:
                raw = entry.get().strip()
                row.append(0 if raw == "" else int(raw))
            grid.append(row)

        return grid

    def build_problem_from_form(self) -> ProblemInstance:
        kind = self.problem_kind.get()

        if kind == "Sudoku":
            return sudoku_problem(self._read_sudoku_grid())

        if kind == "N-Queens":
            return n_queens_problem(int(self.n_queens_size.get()))

        if kind == "Graph Coloring":
            nodes = int(self.graph_nodes.get())
            colors = int(self.graph_colors.get())

            if self.graph_mode.get() == "Probability":
                probability = float(self.graph_probability.get())
                seed = self.graph_seed.get().strip()
                return random_graph_coloring_problem(nodes, probability, colors, seed=int(seed) if seed else None)

            if self.graph_mode.get() == "Exact edges":
                edge_count = int(self.graph_edge_count.get())
                seed = self.graph_seed.get().strip()
                return exact_edges_graph_coloring_problem(nodes, edge_count, colors, seed=int(seed) if seed else None)

            if self.graph_mode.get() == "Average degree":
                average_degree = float(self.graph_average_degree.get())
                seed = self.graph_seed.get().strip()
                return average_degree_graph_coloring_problem(nodes, average_degree, colors, seed=int(seed) if seed else None)

            edge_text = self.edge_text.get("1.0", tk.END)
            return manual_graph_coloring_problem(nodes, colors, edge_text)

        if kind == "Hamiltonian Path":
            nodes = int(self.graph_nodes.get())

            if self.graph_mode.get() == "Probability":
                probability = float(self.graph_probability.get())
                seed = self.graph_seed.get().strip()
                return random_hamiltonian_path_problem(nodes, probability, seed=int(seed) if seed else None)

            if self.graph_mode.get() == "Exact edges":
                edge_count = int(self.graph_edge_count.get())
                seed = self.graph_seed.get().strip()
                return exact_edges_hamiltonian_path_problem(nodes, edge_count, seed=int(seed) if seed else None)

            if self.graph_mode.get() == "Average degree":
                average_degree = float(self.graph_average_degree.get())
                seed = self.graph_seed.get().strip()
                return average_degree_hamiltonian_path_problem(nodes, average_degree, seed=int(seed) if seed else None)

            return manual_hamiltonian_path_problem(nodes, self.edge_text.get("1.0", tk.END))

        if kind == "Independent Set":
            nodes = int(self.graph_nodes.get())
            target = int(self.graph_target.get())

            if self.graph_mode.get() == "Probability":
                probability = float(self.graph_probability.get())
                seed = self.graph_seed.get().strip()
                return random_independent_set_problem(nodes, probability, target, seed=int(seed) if seed else None)

            if self.graph_mode.get() == "Exact edges":
                edge_count = int(self.graph_edge_count.get())
                seed = self.graph_seed.get().strip()
                return exact_edges_independent_set_problem(nodes, edge_count, target, seed=int(seed) if seed else None)

            if self.graph_mode.get() == "Average degree":
                average_degree = float(self.graph_average_degree.get())
                seed = self.graph_seed.get().strip()
                return average_degree_independent_set_problem(nodes, average_degree, target, seed=int(seed) if seed else None)

            return manual_independent_set_problem(nodes, target, self.edge_text.get("1.0", tk.END))

        text = self.dimacs_input.get("1.0", tk.END)
        return dimacs_problem_from_text(text)

    def _problem_snapshot_from_form(self) -> dict:
        kind = self.problem_kind.get()

        if kind == "Sudoku":
            return {"kind": "Sudoku", "grid": self._read_sudoku_grid()}

        if kind == "N-Queens":
            return {"kind": "N-Queens", "size": int(self.n_queens_size.get())}

        if kind in GRAPH_PROBLEM_KINDS:
            mode = self.graph_mode.get()
            snapshot = {
                "kind": kind,
                "mode": mode,
                "nodes": int(self.graph_nodes.get()),
                "seed": int(self.graph_seed.get()) if self.graph_seed.get().strip() else None,
            }
            if kind == "Graph Coloring":
                snapshot["colors"] = int(self.graph_colors.get())
            if kind == "Independent Set":
                snapshot["target"] = int(self.graph_target.get())
            if mode == "Probability":
                snapshot["probability"] = float(self.graph_probability.get())
            elif mode == "Exact edges":
                snapshot["edge_count"] = int(self.graph_edge_count.get())
            elif mode == "Average degree":
                snapshot["average_degree"] = float(self.graph_average_degree.get())
            else:
                snapshot["edge_text"] = self.edge_text.get("1.0", tk.END)
            return snapshot

        return {"kind": "DIMACS/CNF", "text": self.dimacs_input.get("1.0", tk.END)}

    def _solver_logging_options_from_form(self) -> dict:
        return self._logging_options(self.advanced_solver_logs.get(), self.solver_log_level.get())

    def _benchmark_logging_options_from_form(self) -> dict:
        return self._logging_options(self.bench_advanced_solver_logs.get(), self.bench_solver_log_level.get())

    def _logging_options(self, enabled: bool, level: str) -> dict:
        if not enabled:
            return {"mode": "normal"}

        if level == "Verbose debug":
            return {"mode": "debug", "progress_interval": 50, "verbose_limit": 200}

        return {"mode": "periodic", "progress_interval": 50, "verbose_limit": 200}

    def generate_cnf(self) -> None:
        try:
            snapshot = self._problem_snapshot_from_form()
            self._start_process_worker(f"Generating CNF for {snapshot['kind']}", generate_cnf_process, snapshot)
        except Exception as exc:
            messagebox.showerror("Cannot generate CNF", str(exc))

    def solve_current(self) -> None:
        try:
            snapshot = self._problem_snapshot_from_form()
            solver_name = self.solver_name.get()
            logging_options = self._solver_logging_options_from_form()
            timeout_seconds = parse_timeout_seconds(self.solve_timeout_seconds.get())
            self._start_process_worker(
                f"Solving {snapshot['kind']} with {solver_name}",
                solve_process,
                snapshot,
                solver_name,
                logging_options,
                timeout_seconds,
            )
        except Exception as exc:
            messagebox.showerror("Cannot solve problem", str(exc))

    def _format_solve_result(self, result) -> str:
        lines = [
            f"Problem: {self.current_problem.name if self.current_problem else ''}",
            f"Solver: {result.solver}",
            f"Status: {result.status}",
            f"Time: {result.elapsed:.6f}s",
            f"Clauses: {result.clauses}",
            f"Variables: {result.variables}",
        ]

        for key in ("decisions", "conflicts", "propagations", "learned_clauses"):
            if key in result.stats:
                lines.append(f"{key.replace('_', ' ').title()}: {result.stats[key]}")

        if result.decoded is not None:
            lines.append("")
            lines.append("Decoded solution:")
            lines.append(self._format_decoded(result.decoded))

        return "\n".join(lines)

    def _format_decoded(self, decoded) -> str:
        if isinstance(decoded, list):
            return "\n".join(" ".join(f"{value:2}" for value in row) for row in decoded)

        if isinstance(decoded, dict):
            if "board" in decoded:
                lines = []
                if "positions" in decoded:
                    lines.append(f"Positions: {decoded['positions']}")
                    lines.append("")
                lines.extend(str(row) for row in decoded["board"])
                return "\n".join(lines)
            if "path" in decoded:
                return "Path: " + " -> ".join(str(node) for node in decoded["path"])
            if "selected" in decoded:
                return "Selected nodes: " + ", ".join(str(node) for node in decoded["selected"])
            return "\n".join(f"{key}: {decoded[key]}" for key in sorted(decoded))

        return str(decoded)

    def _write_result(self, text: str) -> None:
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", text)

    def save_cnf_dialog(self) -> None:
        if self.current_problem is None:
            messagebox.showinfo("No CNF yet", "Generate CNF first, then save it.")
            return

        default_name = self.current_problem.name.replace(" ", "_").replace("/", "_") + ".cnf"
        path = filedialog.asksaveasfilename(
            initialdir=str(INPUT_GENERATED),
            initialfile=default_name,
            defaultextension=".cnf",
            filetypes=[("DIMACS CNF", "*.cnf"), ("All files", "*.*")],
        )

        if path:
            save_dimacs(path, self.current_problem.clauses, [self.current_problem.name])
            self._write_result(f"Saved CNF to {path}")

    def load_dimacs_dialog(self) -> None:
        path = filedialog.askopenfilename(
            initialdir="input",
            filetypes=[("DIMACS CNF", "*.cnf"), ("All files", "*.*")],
        )

        if not path:
            return

        try:
            clauses = load_dimacs(path)
            text = clauses_to_dimacs(clauses, [Path(path).name])
            self.problem_kind.set("DIMACS/CNF")
            self._refresh_problem_form()
            self.dimacs_input.delete("1.0", tk.END)
            self.dimacs_input.insert("1.0", text)
            self.current_problem = dimacs_problem_from_text(text, name=Path(path).name)
            self.cnf_text.delete("1.0", tk.END)
            self.cnf_text.insert("1.0", text)
            self._write_result(f"Loaded {len(clauses)} clauses from {path}")
        except Exception as exc:
            messagebox.showerror("Cannot load DIMACS", str(exc))

    def _build_benchmark_tab(self) -> None:
        self.benchmark_tab.columnconfigure(1, weight=1)
        self.benchmark_tab.rowconfigure(1, weight=1)

        self.benchmark_controls = ttk.LabelFrame(self.benchmark_tab, text="Benchmark", padding=8)
        self.benchmark_controls.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 10))
        self.benchmark_controls.columnconfigure(1, weight=1)

        self.bench_problem = tk.StringVar(value="Graph Coloring")
        self.bench_nodes = tk.StringVar(value="10,20,30")
        self.bench_generation_mode = tk.StringVar(value="Probability")
        self.bench_probs = tk.StringVar(value="0.1,0.3")
        self.bench_edges = tk.StringVar(value="10,20,40")
        self.bench_average_degrees = tk.StringVar(value="3,4,5,6,7")
        self.bench_colors = tk.StringVar(value="2,3")
        self.bench_targets = tk.StringVar(value="2,3")
        self.bench_n_queens_sizes = tk.StringVar(value="4,8")
        self.bench_repeats = tk.StringVar(value="1")
        self.bench_timeout_seconds = tk.StringVar(value="30")
        self.bench_seed = tk.StringVar(value="1")
        self.bench_cdcl = tk.BooleanVar(value=True)
        self.bench_dpll = tk.BooleanVar(value=True)
        self.bench_advanced_solver_logs = tk.BooleanVar(value=False)
        self.bench_solver_log_level = tk.StringVar(value="Periodic progress")
        self.bench_sudoku_size_vars = {
            size: tk.BooleanVar(value=size in (4, 9))
            for size in SUDOKU_BENCHMARK_SIZES
        }
        self.chart_metric = tk.StringVar(value="Raw Time")

        ttk.Label(self.benchmark_controls, text="Problem").grid(row=0, column=0, sticky="w")
        problem_box = ttk.Combobox(
            self.benchmark_controls,
            textvariable=self.bench_problem,
            values=BENCHMARK_PROBLEMS,
            state="readonly",
            width=18,
        )
        problem_box.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        problem_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_benchmark_form())

        self.benchmark_description = tk.StringVar()
        ttk.Label(
            self.benchmark_controls,
            textvariable=self.benchmark_description,
            wraplength=250,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.benchmark_input_frame = ttk.Frame(self.benchmark_controls)
        self.benchmark_input_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Label(self.benchmark_controls, text="Repeats").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(self.benchmark_controls, textvariable=self.bench_repeats, width=18).grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(10, 0))

        ttk.Label(self.benchmark_controls, text="Timeout (s)").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(self.benchmark_controls, textvariable=self.bench_timeout_seconds, width=18).grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Checkbutton(self.benchmark_controls, text="CDCL", variable=self.bench_cdcl).grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(self.benchmark_controls, text="DPLL", variable=self.bench_dpll).grid(row=5, column=1, sticky="w", pady=(8, 0))

        ttk.Checkbutton(
            self.benchmark_controls,
            text="Advanced solver logs",
            variable=self.bench_advanced_solver_logs,
            command=self._refresh_benchmark_log_controls,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.bench_log_label = ttk.Label(self.benchmark_controls, text="Log detail")
        self.bench_log_label.grid(row=7, column=0, sticky="w", pady=(8, 0))
        self.bench_log_box = ttk.Combobox(
            self.benchmark_controls,
            textvariable=self.bench_solver_log_level,
            values=("Periodic progress", "Verbose debug"),
            state=tk.DISABLED,
            width=16,
        )
        self.bench_log_box.grid(row=7, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        self.run_benchmark_button = ttk.Button(self.benchmark_controls, text="Run Benchmark", command=self.run_benchmark)
        self.skip_benchmark_button = ttk.Button(
            self.benchmark_controls,
            text="Skip Current",
            command=self.skip_current_benchmark_case,
            state=tk.DISABLED,
        )
        self.export_csv_button = ttk.Button(self.benchmark_controls, text="Export CSV", command=self.export_benchmark_csv)
        self.export_chart_button = ttk.Button(self.benchmark_controls, text="Export Chart", command=self.export_benchmark_chart)
        self.run_benchmark_button.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.skip_benchmark_button.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.export_csv_button.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.export_chart_button.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.controls_to_disable.extend([self.run_benchmark_button, self.export_csv_button, self.export_chart_button])

        ttk.Label(self.benchmark_controls, text="Chart").grid(row=12, column=0, sticky="w", pady=(12, 0))
        ttk.Combobox(
            self.benchmark_controls,
            textvariable=self.chart_metric,
            values=("Raw Time", "Log Time", "Normalized Time", "Conflicts", "Decisions"),
            state="readonly",
            width=16,
        ).grid(row=12, column=1, sticky="ew", padx=(8, 0), pady=(12, 0))
        ttk.Button(self.benchmark_controls, text="Refresh Chart", command=self.draw_benchmark_chart).grid(row=13, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        table_frame = ttk.Frame(self.benchmark_tab)
        table_frame.grid(row=0, column=1, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("case", "type", "detail", "solver", "status", "time", "conflicts", "decisions")
        self.benchmark_table = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        headings = {
            "case": "Case",
            "type": "Type",
            "detail": "Detail",
            "solver": "Solver",
            "status": "Status",
            "time": "Time",
            "conflicts": "Conflicts",
            "decisions": "Decisions",
        }
        widths = {"case": 240, "detail": 170}
        for column in columns:
            self.benchmark_table.heading(column, text=headings[column])
            self.benchmark_table.column(column, width=widths.get(column, 100))
        self.benchmark_table.grid(row=0, column=0, sticky="nsew")
        table_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.benchmark_table.yview)
        table_scroll.grid(row=0, column=1, sticky="ns")
        self.benchmark_table.configure(yscrollcommand=table_scroll.set)

        self.chart_frame = ttk.LabelFrame(self.benchmark_tab, text="Chart", padding=8)
        self.chart_frame.grid(row=1, column=1, sticky="nsew", pady=(10, 0))
        self.chart_frame.rowconfigure(0, weight=1)
        self.chart_frame.columnconfigure(0, weight=1)

        self._refresh_benchmark_form()
        self._refresh_benchmark_log_controls()

    def _refresh_benchmark_form(self) -> None:
        for child in self.benchmark_input_frame.winfo_children():
            child.destroy()

        problem = self.bench_problem.get()
        self.benchmark_description.set(PROBLEM_DESCRIPTIONS.get(problem, ""))

        if problem == "Sudoku":
            self.benchmark_controls.configure(text="Sudoku Benchmark")
            self._build_sudoku_benchmark_form()
        elif problem == "N-Queens":
            self.benchmark_controls.configure(text="N-Queens Benchmark")
            self._build_n_queens_benchmark_form()
        else:
            self.benchmark_controls.configure(text=f"{problem} Benchmark")
            self._build_graph_benchmark_form()

    def _refresh_benchmark_log_controls(self) -> None:
        if self.bench_advanced_solver_logs.get():
            self.bench_log_box.configure(state="readonly")
        else:
            self.bench_log_box.configure(state=tk.DISABLED)

    def _build_graph_benchmark_form(self) -> None:
        self.bench_graph_field_entries = {}
        self.bench_graph_mode_buttons = {}

        ttk.Label(self.benchmark_input_frame, text="Generation").grid(row=0, column=0, sticky="w", pady=2)
        mode_row = ttk.Frame(self.benchmark_input_frame)
        mode_row.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=2)
        for label, value in [
            ("G(n,p)", "Probability"),
            ("G(n,m)", "Exact edges"),
            ("G(n,d)", "Average degree"),
        ]:
            button = ttk.Radiobutton(
                mode_row,
                text=label,
                variable=self.bench_generation_mode,
                value=value,
                command=self._refresh_benchmark_graph_controls,
            )
            button.pack(side=tk.LEFT, padx=(0, 10))
            self.bench_graph_mode_buttons[value] = button

        fields = [
            ("nodes", "Nodes", self.bench_nodes),
        ]
        if self.bench_problem.get() == "Graph Coloring":
            fields.append(("colors", "Colors", self.bench_colors))
        if self.bench_problem.get() == "Independent Set":
            fields.append(("targets", "Target k values", self.bench_targets))
        fields.extend([
            ("probabilities", "Probabilities", self.bench_probs),
            ("edge_counts", "Edge counts", self.bench_edges),
            ("average_degrees", "Average degrees", self.bench_average_degrees),
            ("seed", "Seed", self.bench_seed),
        ])

        for row, (key, label, variable) in enumerate(fields, start=1):
            ttk.Label(self.benchmark_input_frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(self.benchmark_input_frame, textvariable=variable, width=18)
            entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
            self.bench_graph_field_entries[key] = entry

        self._refresh_benchmark_graph_controls()

    def _refresh_benchmark_graph_controls(self) -> None:
        if not hasattr(self, "bench_graph_field_entries"):
            return

        mode = self.bench_generation_mode.get()
        active_by_key = {
            "nodes": True,
            "colors": True,
            "targets": True,
            "probabilities": mode == "Probability",
            "edge_counts": mode == "Exact edges",
            "average_degrees": mode == "Average degree",
            "seed": True,
        }

        for key, entry in self.bench_graph_field_entries.items():
            entry.configure(state=tk.NORMAL if active_by_key.get(key, False) else tk.DISABLED)

    def _build_n_queens_benchmark_form(self) -> None:
        ttk.Label(self.benchmark_input_frame, text="Sizes").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(self.benchmark_input_frame, textvariable=self.bench_n_queens_sizes, width=18).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)

    def _build_sudoku_benchmark_form(self) -> None:
        ttk.Label(self.benchmark_input_frame, text="Sizes").grid(row=0, column=0, sticky="nw", pady=2)
        sizes_frame = ttk.Frame(self.benchmark_input_frame)
        sizes_frame.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=2)

        for index, size in enumerate(SUDOKU_BENCHMARK_SIZES):
            ttk.Checkbutton(
                sizes_frame,
                text=f"{size}x{size}",
                variable=self.bench_sudoku_size_vars[size],
            ).grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 10), pady=2)

    def _selected_sudoku_benchmark_sizes(self) -> list[int]:
        return [
            size
            for size in SUDOKU_BENCHMARK_SIZES
            if self.bench_sudoku_size_vars[size].get()
        ]

    def run_benchmark(self) -> None:
        try:
            solvers = []
            if self.bench_cdcl.get():
                solvers.append("CDCL")
            if self.bench_dpll.get():
                solvers.append("DPLL")
            if not solvers:
                raise ValueError("Select at least one solver")

            repeats = int(self.bench_repeats.get())
            logging_options = self._benchmark_logging_options_from_form()
            timeout_seconds = parse_timeout_seconds(self.bench_timeout_seconds.get())

            if self.bench_problem.get() == "Sudoku":
                sizes = self._selected_sudoku_benchmark_sizes()
                if not sizes:
                    raise ValueError("Select at least one Sudoku size")

                total_runs = len(sizes) * repeats * len(solvers)
                params = {
                    "problem_type": "Sudoku",
                    "sizes": sizes,
                    "solvers": solvers,
                    "repeats": repeats,
                    "logging_options": logging_options,
                    "timeout_seconds": timeout_seconds,
                }
            elif self.bench_problem.get() == "N-Queens":
                sizes = parse_int_list(self.bench_n_queens_sizes.get())
                total_runs = len(sizes) * repeats * len(solvers)
                params = {
                    "problem_type": "N-Queens",
                    "sizes": sizes,
                    "solvers": solvers,
                    "repeats": repeats,
                    "logging_options": logging_options,
                    "timeout_seconds": timeout_seconds,
                }
            else:
                seed_text = self.bench_seed.get().strip()
                node_counts = parse_int_list(self.bench_nodes.get())
                seed = int(seed_text) if seed_text else None
                if self.bench_generation_mode.get() == "Exact edges":
                    generation_mode = "exact_edges"
                    probabilities = []
                    edge_counts = parse_int_list(self.bench_edges.get())
                    average_degrees = []
                    sweep_values = edge_counts
                elif self.bench_generation_mode.get() == "Average degree":
                    generation_mode = "average_degree"
                    probabilities = []
                    edge_counts = []
                    average_degrees = parse_float_list(self.bench_average_degrees.get())
                    sweep_values = average_degrees
                else:
                    generation_mode = "probability"
                    probabilities = parse_float_list(self.bench_probs.get())
                    edge_counts = []
                    average_degrees = []
                    sweep_values = probabilities
                if self.bench_problem.get() == "Graph Coloring":
                    color_counts = parse_int_list(self.bench_colors.get())
                    target_sizes = []
                    specific_count = len(color_counts)
                elif self.bench_problem.get() == "Independent Set":
                    color_counts = []
                    target_sizes = parse_int_list(self.bench_targets.get())
                    specific_count = len(target_sizes)
                else:
                    color_counts = []
                    target_sizes = []
                    specific_count = 1
                total_runs = len(node_counts) * len(sweep_values) * specific_count * repeats * len(solvers)
                params = {
                    "problem_type": self.bench_problem.get(),
                    "node_counts": node_counts,
                    "probabilities": probabilities,
                    "edge_counts": edge_counts,
                    "average_degrees": average_degrees,
                    "color_counts": color_counts,
                    "target_sizes": target_sizes,
                    "solvers": solvers,
                    "repeats": repeats,
                    "seed": seed,
                    "generation_mode": generation_mode,
                    "logging_options": logging_options,
                    "timeout_seconds": timeout_seconds,
                }

            self.benchmark_rows = []
            self._fill_benchmark_table()
            self.pending_chart_refresh = True

            skip_event = mp.Event()
            self._start_process_worker(
                f"Benchmarking {total_runs} solver runs",
                benchmark_process,
                params,
                extra_events=(skip_event,),
                benchmark_skip_event=skip_event,
            )
        except Exception as exc:
            messagebox.showerror("Benchmark failed", str(exc))

    def _fill_benchmark_table(self) -> None:
        for item in self.benchmark_table.get_children():
            self.benchmark_table.delete(item)

        for row in self.benchmark_rows:
            self._insert_benchmark_row(row)

    def _insert_benchmark_row(self, row: BenchmarkRow) -> None:
        self.benchmark_table.insert(
            "",
            tk.END,
            values=(
                row.case_name,
                row.problem_type,
                row.detail,
                row.solver,
                row.status,
                f"{row.elapsed:.6f}s",
                row.conflicts,
                row.decisions,
            ),
        )

    def draw_benchmark_chart(self) -> None:
        if not self.benchmark_rows:
            return

        if Figure is None or FigureCanvasTkAgg is None:
            messagebox.showwarning("Charts unavailable", "Matplotlib Tk support is not available.")
            return

        if self.benchmark_canvas is not None:
            self.benchmark_canvas.get_tk_widget().destroy()

        figure = Figure(figsize=(7.5, 3.6), dpi=100)
        axis = figure.add_subplot(111)
        metric = self.chart_metric.get()

        x = list(range(len(self.benchmark_rows)))
        labels = [self._benchmark_chart_label(row) for row in self.benchmark_rows]

        if metric == "Raw Time":
            y = [row.elapsed for row in self.benchmark_rows]
            ylabel = "Seconds"
        elif metric == "Log Time":
            y = [max(row.elapsed, 1e-9) for row in self.benchmark_rows]
            ylabel = "Seconds (log)"
            axis.set_yscale("log")
        elif metric == "Normalized Time":
            y = [row.elapsed / max(row.variables, 1) for row in self.benchmark_rows]
            ylabel = "Seconds / variable"
        elif metric == "Conflicts":
            y = [0 if row.conflicts == "-" else int(row.conflicts) for row in self.benchmark_rows]
            ylabel = "Conflicts"
        else:
            y = [0 if row.decisions == "-" else int(row.decisions) for row in self.benchmark_rows]
            ylabel = "Decisions"

        colors = [self._benchmark_bar_color(row.status) for row in self.benchmark_rows]
        axis.bar(x, y, color=colors)
        axis.set_title(self._benchmark_chart_title(metric))
        axis.set_ylabel(ylabel)
        axis.set_xticks(x)
        axis.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        self._draw_benchmark_status_legend(axis)
        figure.tight_layout()

        self.benchmark_figure = figure
        self.benchmark_canvas = FigureCanvasTkAgg(figure, master=self.chart_frame)
        self.benchmark_canvas.draw()
        self.benchmark_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    def _benchmark_bar_color(self, status: str) -> str:
        return {
            "SAT": "#4c78a8",
            "UNSAT": "#e45756",
            "TIMEOUT": "#f58518",
            "SKIPPED": "#bab0ab",
            "CANCELLED": "#9d9d9d",
            "UNKNOWN": "#b279a2",
        }.get(status, "#72b7b2")

    def _benchmark_chart_label(self, row: BenchmarkRow) -> str:
        case_name = row.case_name
        problem_prefix = f"{row.problem_type} "
        if case_name.startswith(problem_prefix):
            case_name = case_name[len(problem_prefix):]
        return f"{case_name}\n{row.solver}"

    def _benchmark_chart_title(self, metric: str) -> str:
        problem_types = []
        for row in self.benchmark_rows:
            if row.problem_type not in problem_types:
                problem_types.append(row.problem_type)

        if len(problem_types) == 1:
            return f"{problem_types[0]} - {metric}"
        if problem_types:
            return f"Mixed Problems - {metric}"
        return metric

    def _draw_benchmark_status_legend(self, axis) -> None:
        try:
            from matplotlib.patches import Patch
        except Exception:
            return

        statuses = []
        for row in self.benchmark_rows:
            if row.status not in statuses:
                statuses.append(row.status)

        handles = [
            Patch(color=self._benchmark_bar_color(status), label=status)
            for status in statuses
        ]
        if handles:
            axis.legend(handles=handles, loc="best", fontsize=8)

    def export_benchmark_csv(self) -> None:
        if not self.benchmark_rows:
            messagebox.showinfo("No benchmark data", "Run a benchmark first.")
            return

        default_name = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            initialdir=str(BENCHMARK_OUTPUT),
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )

        if path:
            write_benchmark_csv(path, self.benchmark_rows)
            messagebox.showinfo("Exported", f"Saved benchmark CSV to {path}")

    def export_benchmark_chart(self) -> None:
        if self.benchmark_figure is None:
            self.draw_benchmark_chart()

        if self.benchmark_figure is None:
            return

        default_name = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = filedialog.asksaveasfilename(
            initialdir=str(BENCHMARK_OUTPUT),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("All files", "*.*")],
        )

        if path:
            self.benchmark_figure.savefig(path)
            messagebox.showinfo("Exported", f"Saved chart to {path}")


def main() -> None:
    root = tk.Tk()
    SATApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
