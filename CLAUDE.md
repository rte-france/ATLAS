# ATLAS

Power market simulator (day-ahead, intraday, reserves) developed by Artelys for RTE.

## Stack

- Python 3.13+, managed with `uv`
- OR-Tools for optimization, Pydantic for models, Polars/Pandas for data.
- `antares-craft` for Antares study parsing
- Linting: Ruff | Types: mypy | Tests: pytest

## Setup

```bash
uv sync --all-groups
uv run pre-commit install
```

## Common commands

```bash
uv run atlas              # CLI entry point
uv run pytest .           # unit tests (integration excluded by default)
uv run ruff check atlas   # lint
uv run ruff format atlas  # formatting
uv run zensical serve     # Documentation
uv run mypy atlas/        # type check
```

## Architecture

```
atlas/
  app.py            # Typer CLI
  modules/          # Market modules — independent computation units
  orchestrator/     # Workflows: chains modules, manages state and changes
    current_input_state.py  # shared state passed between modules
    change_set.py           # represents changes to apply
    handler/                # ChangeSetHandler: applies changesets onto the state
    workflow/               # workflow sequencing definitions
    actionplan/             # execution plans
    hook/                   # hooks on workflow steps
  solver/           # OR-Tools interface & helpers
  math/             # Timeseries, matrices (lazy/scenario variants)
  io_utils/         # Input loading, output writing, dataset, Prometheus
  objects/          # Core business model objects (inherited by modules)
  abstract_class/   # Base classes for parameters, module, dataset
```

## Data flow (orchestrator)

Modules are **independent atomic units** — the orchestrator is only responsible for chaining them into a workflow. The flow is:

1. `CurrentInputState` — centralized state passed between modules
2. A module produces **ChangeSets** (computed modifications)
3. The `ChangeSetHandler` applies those ChangeSets onto the `CurrentInputState`
4. The next module receives the updated state

Never pass data between modules through any other mechanism.

## Creating a new market module

Each module is **fully independent**. Required structure:

```
modules/my_module/
  __init__.py
  module.py          # inherits from the Module abstract class
  parameters.py      # inherits from the Parameters abstract class
  dataset.py         # inherits from the Dataset abstract class
  input_objects/     # module-specific business objects, inherit from atlas core objects
```

`input_objects` define the attributes required to run the module — they inherit from `atlas/objects/` to get common attributes.

## Solver (OR-Tools)

The main interface is `OptimisationModel` — always go through it, never call OR-Tools directly. Helpers in `solver/solver_helper.py` are used for tests.

## Math objects (Timeseries / Matrices)

Lazy and eager variants are **transparent to the caller** — calling code should never need to distinguish between the two. Always code against the abstract interface (`abstract_timeseries`, `abstract_scenario_matrix`).
Always use these APIs and avoid falling back to raw Polars. No pandas. If a method is missing, implement it.

## Tests

- Test Dataset: `tests/dataset`
- Unit tests: `tests/test_unit/`
- pytest-cov for test coverage.
- Module tests: `tests/test_module/`
- Integration tests: `tests/test_integration/` — marked `@pytest.mark.integration`, run on CI only (PRs to `main`)

## Code Conventions

* Every code newly produced has to be tested.
* Use absolute imports for atlas imports, don't import directly from atlas.
* Use built-in typing where possible: `list`, `str`, `int`, `float`, `dict`. Use `X | None` instead of `Optional[X]`.
* Create custom errors if necessary or use specific built-in exceptions: `ValueError`, `TypeError`, `FileNotFoundError`.
* Use `pathlib.Path` for file operations.
* Make sure code produced is well typed.
* Use Zensical to build documentation; docstring format is Sphinx. Provide examples when necessary (for complex or non-obvious functions/methods).
