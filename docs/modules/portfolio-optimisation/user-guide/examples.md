# Examples

## Basic Usage

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.portfolio_optimisation import PortfolioOptimisationModule

dataset = AtlasDataset.from_directory("path/to/dataset")

params = {
    "temporal": {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-01-02T00:00:00",
        "execution_date": "2023-12-31T12:00:00",
        "timestep": "PT1H",
    },
    "solver": {
        "solver_name": "XPRESS",
    },
    "output": {
        "export_result": True,
    },
}

result = ModuleRun(
    module=PortfolioOptimisationModule(),
    dataset=dataset,
    parameters=params,
).run()

# Access results
temporal = params["temporal"]
optimized_power = result.equipment[0].power.get_forecast(
    temporal["execution_date"], temporal["start_date"], temporal["end_date"]
)
```

## Using Config File

```yaml
temporal:
  start_date: "2024-01-01T00:00:00"
  end_date: "2024-01-02T00:00:00"
  execution_date: "2023-12-31T12:00:00"
  timestep: "PT1H"
solver:
  solver_name: "XPRESS"
output:
  export_result: true
```

```python
result = ModuleRun(
    module=PortfolioOptimisationModule(),
    dataset=dataset,
    parameters="config/parameters.yaml",
).run()
```

## Configuration Examples

**Individual unit optimization**:
```python
params = {
    # ... temporal/solver/output ...
    "is_portfolio_bidding": False,
}
```

**Exclude equipment**:
```python
params = {
    # ... temporal/solver/output ...
    "excluded_technologies": ["wind", "solar"],
    "excluded_thermal_strategy": ["Peak"],
    "excluded_market_areas": ["FR"],
}
```

**Multiprocessing**:
```python
params = {
    # ... temporal/solver/output ...
    "multiprocessing": {
        "enable": True,
        "max_workers": 4,
    },
}
```

**Solver options**:
```python
params = {
    # ... temporal/output ...
    "solver": {
        "solver_name": "SCIP",
        "solver_timeout": "PT300S",
        "solver_duality_gap": 0.001,
        "use_presolve": True,
    },
}
```

**Adjust penalties**:
```python
params = {
    # ... temporal/solver/output ...
    "small_imbalance_penalty": 0.15,
    "large_imbalance_penalty": 0.25,
    "automated_unprocured_reserves_penalty": 50000,
}
```
