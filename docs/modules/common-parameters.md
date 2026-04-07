# Common Module Parameters

## Overview

All ATLAS modules inherit from `AbstractModuleParameters` and share a common set of configuration parameters organized into nested sections.


## Structure

Common parameters are organized into four sections:
```yaml
temporal:       # Time configuration (required)
output:         # Output configuration (recommended, has defaults)
solver:         # Solver configuration (optional, has defaults)
multiprocessing: # Parallel execution (optional, has defaults)
```

---

## `temporal` — Time Configuration (required)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_date` | ISO 8601 datetime | — | Start of the execution period |
| `end_date` | ISO 8601 datetime | — | End of the execution period |
| `execution_date` | ISO 8601 datetime | — | Forecast reference date for data retrieval |
| `timestep` | ISO 8601 duration | `"PT1H"` | Time resolution for calculations |

> `end_date` must be strictly greater than `start_date`.

---

## `solver` — Solver Configuration (optional)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `solver_name` | string | `"XPRESS"` | Solver to use (e.g. `"XPRESS"`, `"SCIP"`, `"HiGHS"`) |
| `timeout` | ISO 8601 duration | `"PT4M"` | Maximum solving time |
| `duality_gap` | float | `0.0001` | MIP optimality tolerance |
| `use_presolve` | boolean | `false` | Enable solver presolve |
| `export_lp` | boolean | `false` | Export LP file for debugging |

---

## `output` — Output Configuration (optional)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `export_result` | boolean | `false` | Write results back to business model objects |
| `export_output_dataset` | boolean | `false` | Export the output dataset to disk |
| `output_dir` | path | `""` | Directory where outputs are written |

---

## `multiprocessing` — Parallel Execution (optional)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable` | boolean | `false` | Enable parallel execution |
| `max_workers` | int or null | `null` | Number of workers (null = CPU count) |

---

## Example
```yaml
temporal:
  start_date: "2028-09-27 00:00:00"
  end_date: "2028-09-28 00:00:00"
  execution_date: "2028-09-26 12:00:00"
  timestep: "PT1H"

solver:
  solver_name: "SCIP"
  timeout: "PT60S"
  duality_gap: 0.0001
  use_presolve: false
  export_lp: false

output:
  export_result: false
  export_output_dataset: false
  output_dir: "results/"

multiprocessing:
  enable: false
  max_workers: null
```

---

## Parameter Formats

Parameters can be provided as a **YAML file**, a **JSON file**, or a **Python dictionary**:
```python
# Dictionary
module.run(input_data, {
    "temporal": {
        "start_date": "2028-09-27 00:00:00",
        "end_date": "2028-09-28 00:00:00",
        "execution_date": "2028-09-26 12:00:00",
    }
})

# File
module.run(input_data, "parameters.yml")
```

---

## Module-Specific Parameters

Each module extends these base parameters with additional options:

- [Portfolio Optimisation Parameters](../modules/portfolio-optimisation/user-guide/input-data.md)
- [Day-Ahead Orders Parameters](../modules/day-ahead-orders/user-guide/input-data.md)
- [Market Clearing Parameters](../modules/market-clearing/user-guide/input-data.md)

## See Also

- [Module Pattern](module-pattern.md): Understanding the ATLAS module architecture
- [Running Modules](running-modules.md): Execution details and best practices
