# API Reference

Complete API documentation for Atlas core components, data structures, and utilities.

## Core Components

### Math Objects

Mathematical data structures for time series and matrix operations.

- [**Timeseries**](math/timeseries.md) - Time series data structures and operations
- [**Scenario Matrix**](math/scenario_matrix.md) - Matrix for scenario-based data
- [**Forecasting Matrix**](math/forecasting_matrix.md) - Matrix for forecasting data
- [**LazyTimeseries**](math/lazy_timeseries.md) - Lazy-evaluated time series
- [**LazyMatrix**](math/lazy_scenario_matrix.md) - Lazy-evaluated matrices

### Models

Pydantic models for equipment and market entities.

- [**Equipment**](models/equipment.md) - Models for generation assets (thermal, hydro, solar, wind, storage)
- [**Market**](models/market.md) - Models for market areas, borders, orders, and portfolios

### I/O

Data input/output and dataset management.

- [**AtlasDataset**](io/atlas_dataset.md) - Dataset reading and writing utilities

### Workflows

Workflow orchestration and step management.

- [**Workflow**](workflow/workflow.md) - Main workflow orchestration
- [**Workflow Step**](workflow/workflow_step.md) - Individual workflow steps

### Optimization

Solver interfaces and optimization models.

- [**Solver Interface**](solver/interface.md) - Interface for optimization solvers
- [**Other**](solver/models.md) - Additional solver-related models

### Utilities

- [**Enum**](enum.md) - Enumeration types used across Atlas
- [**Logging**](logging.md) - Logging configuration and utilities
