# Parameters

The Day-Ahead Orders module is configured through `DayAheadOrdersParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

For common parameters (`temporal`, `solver`, `output`, `multiprocessing`), see [Common Parameters](../../common-parameters.md).

---

## Penalties & Pricing

| Parameter | Type | Default | Description |
|---|---|---|---|
| `proportional_reserves_penalty` | `bool` | `True` | When `True`, reserve volume is flexible and penalised proportionally instead of being fixed. |
| `automated_unprocured_reserves_penalty` | `float` | `10 000` €/MW/h | Penalty for failing to provide the automated reserves procurement. Should be greater than the manual reserve penalty. |
| `manual_unprocured_reserves_penalty` | `float` | `100` €/MW/h | Penalty for failing to provide the manual reserves procurement. |

## Storage Equipment

### Battery

| Parameter | Type | Default | Description |
|---|---|---|---|
| `battery_nb_fragments` | `int` | `3` | In the optimization problem, the total upward capacity (i.e. what can be sold) is divided into fragments to avoid an all-or-nothing effect of the price forecast. Each fragment considered a lower price forecast compared to the precedent. |
| `battery_smoothing_factor` | `float` | `0.1` | Extra coefficient applied to the price forecast. Each fragment i considers `price_forecast_medium` * (1 - (i*`battery_smoothing_factor`)/(`battery_nb_fragments` - 1)) as its price forecast reference. |

### Pumped Hydraulic Storage

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pumped_hydraulic_nb_fragments` | `int` | `3` | See similar parameter for batteries. |
| `pumped_hydraulic_smoothing_factor` | `float` | `0.2` | See similar parameter for batteries. |

### Electric Vehicle

| Parameter | Type | Default | Description |
|---|---|---|---|
| `electric_vehicle_nb_fragments` | `int` | `3` | See similar parameter for batteries. |
| `electric_vehicle_smoothing_factor` | `float` | `0.1` | See similar parameter for batteries. |
| `ev_energy_coef` | `float` | `1.5` | Multiplier on `DisplacementEnergy` delta to generate enough Buy offers over the full EV horizon. |

## Other Equipment

| Parameter | Type | Default | Description |
|---|---|---|---|
| `load_price` | `float` | `3 000` €/MWh | Price applied to all load orders. `3 000` is the standard DayAhead upper price cap. |
| `epsilon` | `float` | `0.001` | Slack parameter to avoid infeasibilities from numerical approximations in thermal constraints. |
| `price_forecasts_types` | `list[str]` | `["Medium"]` | Available price forecast scenarios in the input data. `"Medium"` must always be present. If present, `"Low"` and `"High"` are used in the Thermal optimization problem for Intermediate strategy.`"Medium"` is always used for the price forecast estimation of Storage units. |
| `thermal_additional_hours` | `Duration` | `12h` | Extra optimisation horizon appended after `end_date` for thermal units, for economical relevance of orders formulated. Regardless of this extra horizon, technical constraints are always checked on extended time frames. |
| `hydraulic_minimal_fragment_size` | `int` | `100` MW | For hydro units, the range [`MinimumPower`; `MaximumPower`] is divided into a fixed number of fragments. Depending on the capacity of the unit, this can lead to small fragments which are not deemed relevant. This parameter imposes an minimum size on said fragments (MW). |

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
pumped_hydraulic_nb_fragments: 3
pumped_hydraulic_smoothing_factor: 0.2
hydraulic_minimal_fragment_size: 100
electric_vehicle_nb_fragments: 3
electric_vehicle_smoothing_factor: 0.1
ev_energy_coef: 1.5
load_price: 3000
epsilon: 0.001
price_forecasts_types: ["Medium"]
```

## Next Steps

- [Input Objects](input-objects.md): Required input data and attributes
- [Results](results.md): Understanding outputs
