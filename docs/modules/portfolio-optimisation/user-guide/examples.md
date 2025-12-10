# Examples

## Basic Usage

```python
from atlas.modules.portfolio_optimisation import PortfolioOptimisationModule

module = PortfolioOptimisationModule()

raw_data = {
    "portfolio": [portfolio1],
    "thermal": [thermal1],
    "hydro": [hydro1],
    "storage": [storage1],
}

params = {
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-01-02T00:00:00",
    "execution_date": "2023-12-31T12:00:00",
    "export_result": True,
    "solver": "XPRESS",
    "timestep": "PT1H"
}

module.run(raw_data, params)

# Access results
optimized_power = thermal1.power.get_forecast(
    params["execution_date"], params["start_date"], params["end_date"]
)
```

## Using Config File

```json
{
  "start_date": "2024-01-01T00:00:00",
  "end_date": "2024-01-02T00:00:00",
  "execution_date": "2023-12-31T12:00:00",
  "export_result": true,
  "solver": "XPRESS",
  "timestep": "PT1H",
  "thermal_additional_hours": "PT12H",
  "battery_additional_hours": "PT48H"
}
```

```python
module.run(raw_data, "config/parameters.json")
```

## Configuration Examples

**Individual unit optimization**:
```python
params = {"is_portfolio_bidding": False, ...}
```

**Exclude equipment**:
```python
params = {
    "excluded_technologies": "wind;solar",
    "excluded_thermal_strategy": "Peak",
    "excluded_market_areas": "FR",
    ...
}
```

**Multiprocessing**:
```python
params = {"use_multiprocessing": True, "max_workers": 4, ...}
```

**Solver options**:
```python
params = {
    "solver": "SCIP",
    "solver_timeout": "PT300S",
    "solver_duality_gap": 0.001,
    "use_presolve": True,
    ...
}
```

**Custom time horizons**:
```python
params = {
    "timestep": "PT1H",
    "thermal_additional_hours": "PT24H",
    "battery_additional_hours": "PT72H",
    "hydraulic_additional_hours": "PT168H",
    ...
}
```

**Adjust penalties**:
```python
params = {
    "imbalance_penalty_offset": 15,
    "small_imbalance_penalty": 0.15,
    "large_imbalance_penalty": 0.25,
    "automated_unprocured_reserves_penalty": 50000,
    ...
}
```
