# API Reference

Complete API documentation for Atlas core components, data structures, and utilities.

## :lucide-chart-line: Math Objects

Time series and matrix structures for scenario-based and forecasting data.

- [:lucide-activity: **Timeseries**](math/timeseries.md) — Time series data structures and operations
- [:lucide-grid: **Scenario Matrix**](math/scenario_matrix.md) — Matrix for scenario-based data
- [:lucide-trending-up: **Forecasting Matrix**](math/forecasting_matrix.md) — Matrix for forecasting data
- [:lucide-layers: **LazyTimeseries**](math/lazy_timeseries.md) — Lazy-evaluated time series
- [:lucide-layout-grid: **LazyMatrix**](math/lazy_scenario_matrix.md) — Lazy-evaluated scenario matrix

## :lucide-box: Models

Pydantic models for equipment assets, market entities, and network objects.

- [:lucide-zap: **Equipment**](models/equipment/equipment.md) — Generation assets: thermal, hydro, solar, wind, storage, load
- [:lucide-bar-chart-2: **Market**](models/market/market_area.md) — Market areas, borders, orders, and portfolios
- [:lucide-network: **Network**](models/network/node.md) — Network nodes and control blocks

## :lucide-hard-drive: I/O

- [:lucide-database: **AtlasDataset**](io/atlas_dataset.md) — Dataset reading and writing utilities

## :lucide-git-branch: Workflow

- [:lucide-workflow: **Workflow**](workflow/workflow.md) — Main workflow orchestration
- [:lucide-square: **Workflow Step**](workflow/workflow_step.md) — Individual workflow steps

## :lucide-refresh-cw: Orchestrator

- [:lucide-database: **CurrentInputState**](orchestrator/current_input_state.md) — Shared state passed between modules
- [:lucide-git-commit: **ChangeSets**](orchestrator/change_set.md) — Immutable state mutations (Add / Update / Delete)
- [:lucide-layers: **CISHandler**](orchestrator/cis_handler.md) — Apply a batch of ChangeSets with ordering and rollback
- [:lucide-wrench: **ChangeSetHandler**](orchestrator/change_set_handler.md) — Apply a single ChangeSet with reference resolution

## :lucide-cpu: Optimisation

- [:lucide-sliders: **Solver Interface**](solver/interface.md) — OR-Tools solver interface
- [:lucide-blocks: **Models**](solver/models.md) — Optimisation model helpers

## :lucide-settings: Utilities

- [:lucide-list: **Enum**](enum.md) — Enumeration types used across Atlas
- [:lucide-file-text: **Logging**](logging.md) — Logging configuration and utilities
