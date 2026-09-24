# Changelog

All notable changes to this project will be documented in this file.

---

## Versioning

- `MAJOR` version when you make incompatible API changes,
- `MINOR` version when you add functionality in a backwards compatible manner,
- `PATCH` version when you make backwards compatible bug fixes.

---

## Release History Legend

- ✨ Feature
- 🐛 Fix
- 🔄 Change
- 🧹 Refactor
- 📚 Docs
- 🔒 Security

---

## Unreleased

### Breaking changes

The word `output` named at least six unrelated concepts. One word now stands for one concept: `run_dir` for the per-execution root directory, `export` for booleans, `result` for what a module returns, `columns` for Antares column-name configuration.

Parameter files must be updated — unknown keys are silently ignored, so a stale key degrades to its default instead of raising.

| Before | After |
|---|---|
| `output:` (module parameters section) | `export:` |
| `output.export_result` | `export.export_results` |
| `output.export_output_dataset` | `export.export_dataset` |
| `output.output_dir` | `export.run_dir` |
| `export_output` (orchestrator) | `export_final_state` |
| `output:` (antares_to_atlas) | `columns:` |

Python API:

| Before | After |
|---|---|
| `io_utils.parameters.OutputParameters` | `ExportParameters` |
| `abstract_class.dataset.AbstractModuleOutput` | `ModuleResult` |
| `<Module>Output` / `<Module>OutputDataset` | `<Module>Result`, in `modules/<name>/result.py` |
| `AbstractJob.output_dataset` / `get_output_dataset()` | `AbstractJob.result` |
| `AbstractOrchestrator.final_dataset` / `get_output_dataset()` | `AbstractOrchestrator.final_result` |
| `AbstractModuleParameters.get_output_results_dir()` | `.results_dir` (property) |
| `AbstractModuleParameters.get_output_dataset_dir()` | `.dataset_dir` (property) |
| `AbstractModuleParameters.get_lp_dir()` | `.lp_dir` (property) |
| `antares_to_atlas.parameters.OutputParameters` | `AntaresColumnNames` |
| `portfolio_optimisation.utils.orchestration.PortfolioOptimisationResult` | `SinglePortfolioResult` |

`AntaresToAtlasParameters.output_name` is unchanged: it names an Antares study output, which is antares-craft vocabulary, not Atlas vocabulary.

### Orchestrator

- 🧹 Introduced `RunPaths`, which owns the `results/`, `output_dataset/` and `lp_export/` layout of a run directory. On-disk names are unchanged.
- 🐛 Fixed `AttributeError` in the profiling workflow when `export_dataset` was enabled (an unfinished refactor left `job.parameters.get_`).
- 📚 Fixed the `export_final_state` docstring, which described a path instead of a boolean.

---

## 0.1.1

### Market modules

- 🐛 Fixed a sign error in the displacement term of the storage cycle balance.
- 🐛 Fixed a recursive issue in parent/children order coupling.
- 🐛 Fixed a stale loop variable in `update_orders` and bogus border neighbours in market clearing.
- 🐛 Intraday workflow no longer infeasible from iterating on the residual market-clearing order instead of the order itself.
- 🐛 Portfolios and orders that fail optimisation are no longer silently dropped; failures now propagate.
- 🔄 Refactored day-ahead orders and portfolio optimisation to share a marginal value dataclass, removing duplicated code, and migrated intraday orders onto the same fragment data as day-ahead orders.

### Orchestrator

- ✨ Parameters are now immutable (frozen), with deep copies made where mutation was previously relied upon.
- ✨ `Workflow` and `ActionPlan` now deduplicate step/task names and raise on ambiguous names instead of silently colliding.
- 🐛 Fixed several parity gaps between `Workflow` and `ActionPlan` (context application to module parameters, job naming, parameter completeness checks).
- 🐛 Fixed `use_context` merge semantics and the job name prefix in step output directories.

### I/O

- 🐛 Matrix concatenation now raises instead of silently dropping data when a file cannot be read.
- 🔄 Simplified input loading by removing a triple try/except.

### Error handling

- 🐛 Cleaned up error handling across the orchestrator, container and dataset: exceptions are now logged instead of swallowed, and `Container` raises `KeyError` when removing an unknown item.

### Packaging

- 📚 Updated README installation instructions for the PyPI package.

---

## 0.1.0

First public release, published on PyPI as `atlas-model`.

### Market modules

- ✨ `day_ahead_orders` — formulates day-ahead orders per portfolio (thermal, hydro, storage, solar, wind, load, non-dispatchable).
- ✨ `market_clearing` — clears the market over the optimisation horizon.
- ✨ `portfolio_optimisation` — re-optimises a portfolio against a set of prices, starting from its current engagement.
- ✨ `intraday_price_forecast` — forecasts intraday prices per market area from the deviation between the latest load, wind and solar forecasts and the day-ahead baseline.
- ✨ `intraday_orders` — formulates intraday orders from the gap between the optimised schedule and the current engagement.
- ✨ `antares_to_atlas` — converts an Antares study into an Atlas dataset.

### Orchestrator

- ✨ `Workflow` chaining modules into a market chain; day-ahead and intraday chains shipped as examples.
- ✨ Hooks on workflow steps.
- ✨ `CurrentInputState` as the single shared state passed between modules, updated only through change sets.
- ✨ `ChangeSetHandler` applying the change sets produced by a module onto the state.
- ✨ `ActionPlan` chaining a set of modules and workflows, each with its own recurring schedule ; used for rolling-horizon simulations with modules and workflows with different frequency, such as daily or monthly
- ✨ An `ActionPlan` task running a workflow can be described inline as a dict, without a separate workflow file.
- ✨ `Context` applied on parameters via `context.apply()`, for templated parameter files.

### Business model

- ✨ Core objects — equipment, market, market operator, network, network operator — inherited by the module input objects.
- ✨ Storage dispatch accounting for displacement energy over the cycle balance.

### Solver

- ✨ `OptimisationModel`, the single interface over OR-Tools, with helpers for tests.

### Math

- ✨ Timeseries and scenario matrices in lazy and eager variants, transparent to the caller, backed by Polars.
- ✨ Forecasting matrices as a special case of scenario matrices, with the column name index being a datetime. They allow visibility of data to be parametrized by a date of execution.

### I/O

- ✨ `AtlasDataset` input loading and output writing.
- ✨ Prometheus timeseries and HDF5 conversion, single-run and batch, with optional multiprocessing.

### CLI

- ✨ `atlas module run` / `atlas module list`.
- ✨ `atlas workflow run` / `atlas workflow list`.
- ✨ `atlas antares-to-atlas run` / `validate` / `converters`.
- ✨ `atlas prometheus-to-atlas run` / `batch`.
- ✨ `atlas profiling` at workflow or module level.
- ✨ `atlas version`.

### Packaging

- 🔄 Distribution renamed to `atlas-model` for the PyPI release.
- ✨ Release workflow publishing to PyPI through a trusted publisher, then creating the GitHub release with the wheel and sdist attached.
