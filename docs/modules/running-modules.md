# Running Modules in Python

## Basic Usage Pattern

All ATLAS modules are run through `ModuleRun`, which handles dataset state management and change set application automatically:

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.<module_name> import <ModuleName>Module

# 1. Load input data
dataset = AtlasDataset.from_directory("path/to/dataset")

# 2. Run the module
result = ModuleRun(
    module=<ModuleName>Module(),
    dataset=dataset,
    parameters="path/to/parameters.yml",
).run()
```

`ModuleRun.run()` returns an `AtlasDataset` with all changes applied.

Replace `<ModuleName>` with the specific module you want to run:

- `PortfolioOptimisationModule`
- `DayAheadOrdersModule`
- `MarketClearingModule`

## Loading Data

ATLAS provides multiple ways to load input data:

```python
# From directory (lazy loading)
dataset = AtlasDataset.from_directory("path/to/dataset")

# From directory (eager loading)
dataset = AtlasDataset.from_directory("path/to/dataset", lazy=False)

# From existing business objects
dataset = AtlasDataset(
    portfolios=[portfolio1, portfolio2],
    equipment=[thermal1, hydro1, storage1],
    market_areas=[area1, area2]
)
```

## Providing Parameters

Parameters can be provided in three formats:

**Dictionary**:
```python
ModuleRun(module, dataset, params={
    "temporal": {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-01-02T00:00:00",
        "execution_date": "2023-12-31T12:00:00",
        "timestep": "PT1H",
    },
    "output": {
        "export_result": True,
    },
}).run()
```

**YAML file**:
```python
ModuleRun(module, dataset, "config/parameters.yml").run()
```

**JSON file**:
```python
ModuleRun(module, dataset, "config/parameters.json").run()
```

See [Common Parameters](common-parameters.md) for parameters shared across all modules.

## Performance Optimization

### Multiprocessing

Modules that support parallel execution (e.g., Portfolio Optimisation) can use multiprocessing:

```python
params = {
    # ... other parameters ...
    "multiprocessing": {
        "enable": True,
        "max_workers": 4,
    },
}
```

### Lazy Loading

For large datasets, use lazy loading to load data on-demand:

```python
input_data = AtlasDataset.from_directory("path/to/dataset", lazy=True)
```

### Solver Performance

For optimization modules, tune solver settings:

```python
params = {
    # ... other parameters ...
    "solver": {
        "solver_name": "XPRESS",
        "solver_timeout": 300,
        "solver_duality_gap": 0.01,
        "use_presolve": True,
    },
}
```

## CLI Usage

ATLAS modules can also be run from the command line:

```bash
atlas run parameters.yml \
    --module <MODULE_NAME> \
    --dataset path/to/dataset
```

See [CLI Documentation](../cli.md) for more details.

## See Also

- [Module Pattern](module-pattern.md): Understanding the ATLAS module architecture
- [Common Parameters](common-parameters.md): Parameters shared across modules
- Module-specific documentation:
    - [Portfolio Optimisation](../modules/portfolio-optimisation/index.md)
    - [Day-Ahead Orders](../modules/day-ahead-orders/index.md)
    - [Market Clearing](../modules/market-clearing/index.md)
