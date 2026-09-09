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
- ✨ `CurrentInputState` as the single shared state passed between modules, updated only through change sets.
- ✨ `ChangeSetHandler` applying the change sets produced by a module onto the state.
- ✨ `ActionPlan` with job generation and a priority queue, to run several workflows over a set of dates and scenarios.
- ✨ An `ActionPlan` task running a workflow can be described inline as a dict, without a separate workflow file.
- ✨ Hooks on workflow steps.
- ✨ `Context` applied on parameters via `context.apply()`, for templated parameter files.

### Business model

- ✨ Core objects — equipment, market, market operator, network, network operator — inherited by the module input objects.
- ✨ Storage dispatch accounting for displacement energy over the cycle balance.

### Solver

- ✨ `OptimisationModel`, the single interface over OR-Tools, with helpers for tests.

### Math

- ✨ Timeseries and scenario matrices in lazy and eager variants, transparent to the caller, backed by Polars.

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
