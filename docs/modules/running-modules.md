# Running Modules in Python

## Basic Usage Pattern

All ATLAS modules follow the same execution pattern:

```python
from atlas import AtlasDataset, <ModuleName>Module

# 1. Create module instance
module = <ModuleName>Module()

# 2. Load input data
input_data = AtlasDataset.from_directory("path/to/dataset")

# 3. Run the module
module.run(input_data, "path/to/parameters.yml")
```

Replace `<ModuleName>` with the specific module you want to run:

- `PortfolioOptimisationModule`
- `DayAheadOrdersModule`
- `MarketClearingModule`

## Loading Data

ATLAS provides multiple ways to load input data:

```python
# From directory (lazy loading)
input_data = AtlasDataset.from_directory("path/to/dataset")

# From directory (eager loading)
input_data = AtlasDataset.from_directory("path/to/dataset", lazy=False)

# From existing business objects
input_data = AtlasDataset(
    portfolios=[portfolio1, portfolio2],
    equipment=[thermal1, hydro1, storage1],
    market_areas=[area1, area2]
)
```

## Providing Parameters

Parameters can be provided in three formats:

**Dictionary**:
```python
params = {
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-01-02T00:00:00",
    "execution_date": "2023-12-31T12:00:00",
    "export_result": true,
    "timestep": "PT1H"
}
module.run(input_data, params)
```

**YAML file**:
```python
module.run(input_data, "config/parameters.yml")
```

**JSON file**:
```python
module.run(input_data, "config/parameters.json")
```

See [Common Parameters](common-parameters.md) for parameters shared across all modules.

## Performance Optimization

### Multiprocessing

Modules that support parallel execution (e.g., Portfolio Optimisation) can use multiprocessing:

```python
params = {
    # ... other parameters ...
    "use_multiprocessing": true,
    "max_workers": 4  # Number of parallel workers
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
    "solver_name": "XPRESS",
    "solver_timeout": 300,  # 5 minutes max
    "solver_duality_gap": 0.01,  # 1% optimality gap
    "use_presolve": true
}
```

## CLI Usage

ATLAS modules can also be run from the command line:

```bash
atlas run <module-name> \
    --input-data path/to/dataset \
    --parameters path/to/parameters.yml \
    --output-data path/to/output
```

See [CLI Documentation](../cli.md) for more details.

## See Also

- [Module Pattern](module-pattern.md): Understanding the ATLAS module architecture
- [Common Parameters](common-parameters.md): Parameters shared across modules
- Module-specific documentation:
    - [Portfolio Optimisation](../modules/portfolio-optimisation/index.md)
    - [Day-Ahead Orders](../modules/day-ahead-orders/index.md)
    - [Market Clearing](../modules/market-clearing/index.md)
