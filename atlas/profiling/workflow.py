"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from atlas import OptimisationModel, Workflow
from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler


@dataclass
class _State:
    global_steps: list[dict] = field(default_factory=list)
    job_steps: list[dict] = field(default_factory=list)
    solve_times: dict[str, float] = field(default_factory=dict)
    active_job_name: str | None = None

    def record_global(self, name: str, elapsed: float, error: str | None = None) -> None:
        self.global_steps.append({"name": name, "elapsed_s": round(elapsed, 3), "error": error})

    def record_job(self, name: str, run_s: float, apply_s: float, export_s: float, error: str | None = None) -> None:
        solve_s = self.solve_times.get(name, 0.0)
        build_s = max(0.0, run_s - solve_s)
        self.job_steps.append(
            {
                "name": name,
                "build_s": round(build_s, 3),
                "solve_s": round(solve_s, 3),
                "run_s": round(run_s, 3),
                "apply_s": round(apply_s, 3),
                "export_s": round(export_s, 3),
                "total_s": round(run_s + apply_s + export_s, 3),
                "error": error,
            }
        )


# ---------------------------------------------------------------------------
# Patches
# ---------------------------------------------------------------------------


def _patch_cis(cis_cls, state: _State) -> None:
    """Wraps CurrentInputState.from_directory to measure initial dataset loading."""
    original = cis_cls.from_directory

    @classmethod  # type: ignore[misc]
    def patched(cls, path):
        t0 = time.perf_counter()
        result = original.__func__(cls, path)
        state.record_global("CurrentInputState.from_directory", time.perf_counter() - t0)
        return result

    cis_cls.from_directory = patched


def _patch_workflow_load(workflow_cls, state: _State) -> None:
    """Wraps Workflow.from_file to measure YAML loading and job construction."""
    original = workflow_cls.from_file

    @classmethod  # type: ignore[misc]
    def patched(cls, file_path):
        t0 = time.perf_counter()
        result = original.__func__(cls, file_path)
        state.record_global("Workflow.from_file", time.perf_counter() - t0)
        return result

    workflow_cls.from_file = patched


def _patch_solver(solver_cls, state: _State) -> None:
    """Wraps SolverInterface.solve to accumulate solve time per active job.

    Each call adds its duration to state.solve_times[state.active_job_name].
    A single job.run() may call solve() multiple times (e.g. one per portfolio
    in PortfolioOptimisation), so durations are summed.
    """
    original = solver_cls.solve

    def patched_solve(self, *args, **kwargs):
        t0 = time.perf_counter()
        result = original(self, *args, **kwargs)
        elapsed = time.perf_counter() - t0
        if state.active_job_name is not None:
            state.solve_times[state.active_job_name] = state.solve_times.get(state.active_job_name, 0.0) + elapsed
        return result

    solver_cls.solve = patched_solve


def _patch_execute_job(orchestrator_cls, state: _State) -> None:
    """Replaces _execute_job on the given orchestrator class to time each sub-step:
      1. job.run
      2. CISHandler.apply
      3. cis.to_directory (optional)

    Timings are always recorded via finally, even if an exception is raised.

    Note: patches the class passed as argument. If Workflow overrides _execute_job,
    pass Workflow instead of AbstractOrchestrator.
    """

    def patched_execute_job(self, job, cis):
        run_s = apply_s = export_s = 0.0
        error = None

        try:
            try:
                state.active_job_name = job.name
                t0 = time.perf_counter()
                job.run(cis.get_data())
                run_s = time.perf_counter() - t0
            finally:
                state.active_job_name = None

            output_dataset = job.output_dataset
            if not output_dataset:
                raise RuntimeError(f"{job} did not produce output_dataset")

            t0 = time.perf_counter()
            CISHandler.apply(output_dataset.change_sets, cis, rollback_on_error=self.parameters.rollback_on_job_failure)
            apply_s = time.perf_counter() - t0

            if job.parameters.output.export_output_dataset:
                t0 = time.perf_counter()
                cis.to_directory(self.parameters.resolve_path(job.parameters.output.output_dir) / "output_dataset")
                export_s = time.perf_counter() - t0

        except Exception as e:
            error = str(e)
            raise

        finally:
            state.record_job(job.name, run_s, apply_s, export_s, error)

    orchestrator_cls._execute_job = patched_execute_job


B = "\033[1m"  # bold
R = "\033[0m"  # reset
Y = "\033[93m"  # yellow — build
D = "\033[2m"  # dim
E = "\033[91m"  # red — error


def _print_report(wall: float, global_steps: list[dict], job_steps: list[dict]):
    """Print a compact level-1 profiling report.

    :param wall: Total wall time in seconds.
    :type wall: float
    :param global_steps: List of { name, elapsed_s, error } dicts (setup / IO steps).
    :type global_steps: list[dict]
    :param job_steps: List of { name, run_s, apply_s, export_s, total_s, error } dicts.
    :type job_steps: list[dict]
    """
    print(f"\n{B}{'─' * 62}{R}")
    print(f"{B}  Atlas Workflow — Level 1 Profile   wall={wall:.2f}s{R}")
    print(f"{B}{'─' * 62}{R}")

    # Global steps — one line each
    for s in global_steps:
        pct = 100 * s["elapsed_s"] / wall if wall else 0
        print(f"  {D}{s['name']:<38}{R}  {s['elapsed_s']:>5.2f}s  {pct:>3.0f}%")

    if not job_steps:
        print(f"{'─' * 62}\n")
        return

    # Per-job table — columns: build | solve | run | apply | export | total | %
    # build + solve = run  (run is kept for reference)
    nw = max(max(len(j["name"]) for j in job_steps), 16)
    sep = f"  {'─' * (nw + 61)}"
    print(
        f"\n  {B}{'Job':<{nw}}  {'build':>6}  {'solve':>6}  {'run':>6}  {'apply':>6}  {'export':>6}  {'total':>6}  %{R}"
    )
    print(sep)

    G = "\033[92m"  # green  — solve
    for j in job_steps:
        pct = 100 * j["total_s"] / wall if wall else 0
        bar = "█" * max(1, int(pct / 5))
        err = f" {E}!{R}" if j["error"] else ""
        print(
            f"  {j['name']:<{nw}}"
            f"  {Y}{j['build_s']:>5.2f}s{R}"
            f"  {G}{j['solve_s']:>5.2f}s{R}"
            f"  {D}{j['run_s']:>5.2f}s{R}"
            f"  {j['apply_s']:>5.2f}s"
            f"  {j['export_s']:>5.2f}s"
            f"  {j['total_s']:>5.2f}s"
            f"  {pct:>2.0f}%  {bar}{err}"
        )

    # Totals row
    tb = sum(j["build_s"] for j in job_steps)
    ts = sum(j["solve_s"] for j in job_steps)
    tr = sum(j["run_s"] for j in job_steps)
    ta = sum(j["apply_s"] for j in job_steps)
    te = sum(j["export_s"] for j in job_steps)
    tt = sum(j["total_s"] for j in job_steps)
    print(sep)
    print(
        f"  {B}{'TOTAL':<{nw}}{R}"
        f"  {Y}{tb:>5.2f}s{R}"
        f"  {G}{ts:>5.2f}s{R}"
        f"  {D}{tr:>5.2f}s{R}"
        f"  {ta:>5.2f}s"
        f"  {te:>5.2f}s"
        f"  {tt:>5.2f}s"
        f"  {100 * tt / wall:>2.0f}%"
    )

    # Bottlenecks > 5%
    threshold = 0.05 * wall
    bottlenecks = (
        [(f"{j['name']} · solve", j["solve_s"]) for j in job_steps if j["solve_s"] >= threshold]
        + [(f"{j['name']} · build", j["build_s"]) for j in job_steps if j["build_s"] >= threshold]
        + [(f"{j['name']} · apply", j["apply_s"]) for j in job_steps if j["apply_s"] >= threshold]
        + [(s["name"], s["elapsed_s"]) for s in global_steps if s["elapsed_s"] >= threshold]
    )
    if bottlenecks:
        print(f"\n  {B}Bottlenecks (> 5%):{R}")
        for name, t in sorted(bottlenecks, key=lambda x: -x[1]):
            print(f"    → {name:<40}  {t:.2f}s  ({100 * t / wall:.0f}%)")

    print(f"\n  {D}build={Y}yellow{R}{D}  solve={G}green{R}{D}  run=build+solve (dim){R}")
    print(f"{'─' * 62}\n")


def _save_json(wall: float, global_steps: list[dict], job_steps: list[dict], output_path: Path):
    """
    Save the profiling data to a JSON file.

    :param wall: Total wall time in seconds.
    :type wall: float
    :param global_steps: Global setup/IO steps.
    :type global_steps: list[dict]
    :param job_steps: Per-job breakdown.
    :type job_steps: list[dict]
    :param output_path: Destination file path.
    :type output_path: Path
    """
    data = {
        "wall_time_s": round(wall, 3),
        "global_steps": global_steps,
        "job_steps": job_steps,
    }
    output_path.write_text(json.dumps(data, indent=2))
    print(f"  JSON saved: {output_path.resolve()}\n")


def _save_csv(wall: float, global_steps: list[dict], job_steps: list[dict], output_path: Path):
    """Save the profiling data to a CSV file.

    Produces two sections separated by a blank line:
      - Global steps: name, elapsed_s, pct_wall
      - Job steps: name, build_s, solve_s, run_s, apply_s, export_s, total_s, pct_wall

    :param wall: Total wall time in seconds.
    :type wall: float
    :param global_steps: Global setup/IO steps.
    :type global_steps: list[dict]
    :param job_steps: Per-job breakdown.
    :type job_steps: list[dict]
    :param output_path: Destination file path.
    :type output_path: Path
    """
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(["wall_time_s", round(wall, 3)])
        writer.writerow([])

        writer.writerow(["name", "elapsed_s", "pct_wall"])
        for s in global_steps:
            pct = round(100 * s["elapsed_s"] / wall, 1) if wall else 0.0
            writer.writerow([s["name"], s["elapsed_s"], pct])

        writer.writerow([])

        writer.writerow(["name", "build_s", "solve_s", "run_s", "apply_s", "export_s", "total_s", "pct_wall"])
        for j in job_steps:
            pct = round(100 * j["total_s"] / wall, 1) if wall else 0.0
            writer.writerow(
                [
                    j["name"],
                    j["build_s"],
                    j["solve_s"],
                    j["run_s"],
                    j["apply_s"],
                    j["export_s"],
                    j["total_s"],
                    pct,
                ]
            )

    print(f"  CSV saved: {output_path.resolve()}\n")


def run(parameters_path: Path, output: Path | None = None) -> None:
    state = _State()
    _patch_cis(CurrentInputState, state)
    _patch_workflow_load(Workflow, state)
    _patch_execute_job(AbstractOrchestrator, state)
    _patch_solver(OptimisationModel, state)

    t_start = time.perf_counter()
    wf = Workflow.from_file(parameters_path)
    wf.execute()
    wall = time.perf_counter() - t_start

    stem = output.with_suffix("") if output else Path("profiling_workflow")
    _print_report(wall, state.global_steps, state.job_steps)
    _save_json(wall, state.global_steps, state.job_steps, stem.with_suffix(".json"))
    _save_csv(wall, state.global_steps, state.job_steps, stem.with_suffix(".csv"))
