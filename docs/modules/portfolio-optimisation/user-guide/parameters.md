# Parameters

The Portfolio Optimisation module is configured through `PortfolioOptimisationParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

For common parameters (`temporal`, `solver`, `output`, `multiprocessing`), see [Common Parameters](../../common-parameters.md).

---

## Optimization Scope

| Parameter | Type | Default | Description |
|---|---|---|---|
| `is_portfolio_bidding` | `bool` | `True` | `True`: optimize at portfolio level. `False`: optimize individual units. |
| `use_forecast` | `bool` | `False` | `True`: use price forecasts (before market). `False`: use actual prices. |

## Exclusions

| Parameter | Type | Default | Description |
|---|---|---|---|
| `excluded_market_areas` | `list[str]` | `None` | Market areas to exclude. Accepts explicit names, `["all"]`, or `["none"]`. |
| `excluded_technologies` | `list[str]` | `None` | Equipment types to exclude: `"thermal"`, `"storage"`, `"wind"`, `"solar"`, `"hydro"`, `"load"`, `"other_non_dispatchable"`, `["all"]`, `["none"]`. |
| `excluded_thermal_strategy` | `list[str]` | `None` | Thermal strategies to exclude: `"Peak"`, `"Intermediate"`, `"Base"`, `["all"]`, `["none"]`. |

## Penalties & Pricing

| Parameter | Type | Default | Description |
|---|---|---|---|
| `imbalance_penalty_offset` | `float` | `10` €/MWh | Offset when forecasting imbalance settlement price. |
| `isp_forecast_lower_bound` | `float` | `10` €/MWh | Lower bound of the absolute ISP forecast. |
| `small_imbalance_penalty` | `float` | `0.1` | Coefficient for small imbalance ISP. |
| `large_imbalance_penalty` | `float` | `0.2` | Coefficient for large imbalance ISP. |
| `small_imbalance_size` | `float` | `0.15` | Fraction of portfolio energy considered "small". |
| `maximum_imbalance` | `float` | `100 000` MW | Maximum allowed imbalance. |
| `automated_unprocured_reserves_penalty` | `float` | `30 000` €/MW/h | Penalty for not providing automated reserves. |
| `manual_unprocured_reserves_penalty` | `float` | `30 000` €/MW/h | Penalty for not providing manual reserves. |

## Storage Equipment

### Battery

| Parameter | Type | Default | Description |
|---|---|---|---|
| `battery_number_of_fragments` | `int` | `3` | Number of power offer fragments per timestep. |
| `battery_smoothing_factor` | `float` | `0.2` | Smoothing factor for the power curve (0–1). |
| `battery_reserve_duration` | `Duration` | `60 min` | Manual reserve duration. |
| `battery_automated_reserve_duration` | `Duration` | `60 min` | Automated reserve duration. |

### Pumped Hydraulic Storage

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pumped_hydraulic_number_of_fragments` | `int` | `3` | Number of power offer fragments per timestep. |
| `pumped_hydraulic_smoothing_factor` | `float` | `0.2` | Smoothing factor for the power curve (0–1). |
| `pumped_hydraulic_reserve_duration` | `Duration` | `60 min` | Manual reserve duration. |
| `pumped_hydraulic_automated_reserve_duration` | `Duration` | `60 min` | Automated reserve duration. |
| `hydraulic_minimal_fragment_size` | `int` | `100` MW | Offers below this threshold are removed and remaining fragments renormalized. |

### Electric Vehicle

| Parameter | Type | Default | Description |
|---|---|---|---|
| `electric_vehicle_number_of_fragments` | `int` | `3` | Number of power offer fragments per timestep. |
| `electric_vehicle_smoothing_factor` | `float` | `0.2` | Smoothing factor for the power curve (0–1). |
| `electric_vehicle_reserve_duration` | `Duration` | `1 min` | Manual reserve duration. |
| `electric_vehicle_automated_reserve_duration` | `Duration` | `1 min` | Automated reserve duration. |

## Numerical Stability

| Parameter | Type | Default | Description |
|---|---|---|---|
| `allowed_round_off_error` | `float` | `0.01` MW | Accepted power values below this threshold are treated as zero. |

---

## Example Configuration

```yaml
temporal:
  start_date: "2028-09-27 00:00:00"
  end_date: "2028-09-28 00:00:00"
  execution_date: "2028-09-26 12:00:00"
  timestep: "PT1H"
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
market: DayAhead
is_portfolio_bidding: true
use_forecast: false
excluded_market_areas: ["FR", "DE"]
excluded_technologies: ["thermal"]
excluded_thermal_strategy: ["Peak"]
```

## Next Steps

- [Results](results.md): Understanding outputs
