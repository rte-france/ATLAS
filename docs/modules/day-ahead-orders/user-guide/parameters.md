# Parameters

The Day-Ahead Orders module is configured through `DayAheadOrdersParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

For common parameters (`temporal`, `solver`, `output`, `multiprocessing`), see [Common Parameters](../../common-parameters.md).

---

## Penalties & Pricing

| Parameter | Type | Default | Description |
|---|---|---|---|
| `proportional_reserves_penalty` | `bool` | `True` | When `True`, reserve volume is flexible and penalised proportionally instead of being fixed. |
| `automated_unprocured_reserves_penalty` | `float` | `10 000` €/MW/h | Penalty for failing to provide the automated reserves procurement. |
| `manual_unprocured_reserves_penalty` | `float` | `100` €/MW/h | Penalty for failing to provide the manual reserves procurement. |

## Storage Equipment

### Battery

| Parameter | Type | Default | Description |
|---|---|---|---|
| `battery_nb_fragments` | `int` | `3` | Number of orders formulated per timestep for Battery instances. |
| `battery_smoothing_factor` | `float` | `0.1` | Extra cost coefficient per power fragment for Battery instances. |

### Pumped Hydraulic Storage

| Parameter | Type | Default | Description |
|---|---|---|---|
| `phs_nb_fragments` | `int` | `3` | Number of orders formulated per timestep for PumpedHydraulicStorage instances. |
| `phs_smoothing_factor` | `float` | `0.2` | Extra cost coefficient per power fragment for PumpedHydraulicStorage instances. |
| `hydraulic_minimal_fragment_size` | `int` | `100` MW | Offers below this threshold are removed and remaining fragments renormalized. |

### Electric Vehicle

| Parameter | Type | Default | Description |
|---|---|---|---|
| `ev_nb_fragments` | `int` | `3` | Number of orders formulated per timestep for ElectricVehicle instances. |
| `ev_smoothing_factor` | `float` | `0.1` | Extra cost coefficient per power fragment for ElectricVehicle instances. |
| `ev_energy_coef` | `float` | `1.5` | Multiplier on `DisplacementEnergy` delta to generate enough Buy offers over the full EV horizon. |

## Other Equipment

| Parameter | Type | Default | Description |
|---|---|---|---|
| `load_price` | `float` | `3 000` €/MWh | Price applied to all load orders. `3 000` is the standard DayAhead upper price cap. |
| `epsilon` | `float` | `0.001` | Slack parameter to avoid infeasibilities from numerical approximations in thermal constraints. |
| `price_forecasts_types` | `list[str]` | `["Medium"]` | Available price forecast scenarios in the input data. `"Medium"` must always be present. |
| `thermal_additional_hours` | `Duration` | `12h` | Extra optimisation horizon appended after `end_date` for thermal units. |

---

## Example Configuration

```yaml
temporal:
  start_date: "2028-09-27 00:00:00"
  end_date: "2028-09-28 00:00:00"
  execution_date: "2028-09-26 12:00:00"
  timestep: "1h"
solver:
  solver_name: "SCIP"
  use_presolve: true
  export_lp: true
output:
  export_result: true
  export_output_dataset: true
multiprocessing:
  enable: true
  max_workers: 4
proportional_reserves_penalty: true
automated_unprocured_reserves_penalty: 10000
manual_unprocured_reserves_penalty: 100
battery_nb_fragments: 3
battery_smoothing_factor: 0.1
phs_nb_fragments: 3
phs_smoothing_factor: 0.2
hydraulic_minimal_fragment_size: 100
ev_nb_fragments: 3
ev_smoothing_factor: 0.1
ev_energy_coef: 1.5
load_price: 3000
epsilon: 0.001
price_forecasts_types: ["Medium"]
```

## Next Steps

- [Input Objects](input-objects.md): Required input data and attributes
- [Results](results.md): Understanding outputs
