# Common Module Parameters

## Overview

All ATLAS modules inherit from `AbstractParameters` and share a common set of configuration parameters.

## Required Parameters

These parameters are inherited from `AbstractParameters` and required by all modules:

### Time Configuration

- **`start_date`**: Start of the execution period (ISO 8601 datetime)
- **`end_date`**: End of the execution period (ISO 8601 datetime)
- **`execution_date`**: Forecast reference date for data retrieval (ISO 8601 datetime)
- **`timestep`**: Time resolution for calculations (ISO 8601 duration, e.g., `"PT1H"` for 1 hour)

### Execution Control

- **`export_result`**: Whether to write results back to business model objects (boolean, default: `true`)

### Solver Configuration (for optimization modules)

- **`solver_name`**: Solver to use (e.g., `"XPRESS"`, `"GUROBI"`, `"HiGHS"`)
- **`solver_timeout`**: Maximum solving time in seconds (optional)
- **`solver_duality_gap`**: MIP optimality tolerance (optional, e.g., `0.01` for 1%)
- **`use_presolve`**: Enable solver presolve (boolean, default: `true`)

## Parameter Formats

Parameters can be provided as:

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
```yaml
# parameters.yml
start_date: "2024-01-01T00:00:00"
end_date: "2024-01-02T00:00:00"
execution_date: "2023-12-31T12:00:00"
export_result: true
timestep: "PT1H"
```

**JSON file**:
```json
{
  "start_date": "2024-01-01T00:00:00",
  "end_date": "2024-01-02T00:00:00",
  "execution_date": "2023-12-31T12:00:00",
  "export_result": true,
  "timestep": "PT1H"
}
```

## Module-Specific Parameters

Each module extends these base parameters with module-specific options. Refer to individual module documentation for additional parameters:

- [Portfolio Optimisation Parameters](../modules/portfolio-optimisation/user-guide/input-data.md)
- [Day-Ahead Orders Parameters](../modules/day-ahead-orders/user-guide/input-data.md)
- [Market Clearing Parameters](../modules/market-clearing/user-guide/input-data.md)

## See Also

- [Module Pattern](module-pattern.md): Understanding the ATLAS module architecture
- [Running Modules](running-modules.md): Execution details and best practices
