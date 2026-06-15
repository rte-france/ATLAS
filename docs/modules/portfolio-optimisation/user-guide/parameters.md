# Parameters

The Portfolio Optimisation module is configured through `PortfolioOptimisationParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

For common parameters (`temporal`, `solver`, `output`, `multiprocessing`), see [Common Parameters](../../common-parameters.md).

---

## Optimization Scope

| Parameter | Type | Default | Description |
|---|---|---|---|
| `is_portfolio_bidding` | `bool` | `True` | `True`: optimization performed at the portfolio level. `False`: unit-based optimization. |
| `use_forecast` | `bool` | `False` | `True`: use price forecasts (when used in the order formulation step at the beggining of a market). `False`: use actual market prices, when the module is used after a Market Clearing. |

## Exclusions

| Parameter | Type | Default | Description |
|---|---|---|---|
| `excluded_market_areas` | `list[str]` | `None` | Market areas to exclude. Accepts explicit names, `["all"]`, or `["none"]`. |
| `excluded_technologies` | `list[str]` | `None` | Equipment types to exclude: `"thermal"`, `"storage"`, `"wind"`, `"solar"`, `"hydro"`, `"load"`, `"other_non_dispatchable"`, `["all"]`, `["none"]`. |
| `excluded_thermal_strategy` | `list[str]` | `None` | Thermal strategies to exclude: `"Peak"`, `"Intermediate"`, `"Base"`, `["all"]`, `["none"]`. |

## Penalties & Pricing

| Parameter | Type | Default | Description |
|---|---|---|---|
| `imbalance_penalty_offset` | `float` | `10` €/MWh | Offset when forecasting imbalance settlement price. **CURRENTLY DEPRECATED** |
| `isp_forecast_lower_bound` | `float` | `10` €/MWh | Lower bound of the absolute value of the Imbalance Settlement Price forecast. Recommanded value: 0 €/MWh |
| `small_imbalance_penalty` | `float` | `0.1` | Penalty coefficient applied to the forecasted ISP for "small" imbalances (this notion is defined by the parameter `small_imbalance_size`). The resulting penalty will be 1+coeff (resp. 1-coeff) for small positive (resp. negative) imbalances |
| `large_imbalance_penalty` | `float` | `0.2` | Similar to `small_imbalance_penalty`, but for the "large" part of the imbalance (above the `small_imbalance_size`). |
| `small_imbalance_size` | `float` | `0.15` | Ratio applied to the total installed capacity of the portfolio, that defines "small" imbalances (imbalances smaller than this ratio) and "large" imbalances (greater than this ratio). |
| `maximum_imbalance` | `float` | `100 000` MW | Maximum allowed imbalance on the portfolio. |
| `automated_unprocured_reserves_penalty` | `float` | `30 000` €/MW/h | Penalty for not providing automated reserves. |
| `manual_unprocured_reserves_penalty` | `float` | `30 000` €/MW/h | Penalty for not providing manual reserves. |

## Storage Equipment

### Battery

| Parameter | Type | Default | Description |
|---|---|---|---|
| `battery_number_of_fragments` | `int` | `3` | In the optimization process, the total available power range of the battery is separated into fragments. This parameter defines the number of power. |
| `battery_smoothing_factor` | `float` | `0.2` | Smoothing factor for the power curve (value has to be between 0 and 1). |
| `battery_reserve_duration` | `Duration` | `60 min` | Manual reserve duration. |
| `battery_automated_reserve_duration` | `Duration` | `60 min` | Automated reserve duration. |

### Pumped Hydraulic Storage

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pumped_hydraulic_number_of_fragments` | `int` | `3` | See the similar parameter for batteries. |
| `pumped_hydraulic_smoothing_factor` | `float` | `0.2` | Smoothing factor for the power curve (value has to be between 0 and 1). |
| `pumped_hydraulic_reserve_duration` | `Duration` | `60 min` | Manual reserve duration. |
| `pumped_hydraulic_automated_reserve_duration` | `Duration` | `60 min` | Automated reserve duration. |
| `hydraulic_minimal_fragment_size` | `int` | `100` MW | Offers below this threshold are removed and remaining fragments renormalized. |

### Electric Vehicle

| Parameter | Type | Default | Description |
|---|---|---|---|
| `electric_vehicle_number_of_fragments` | `int` | `3` | See the similar parameter for batteries. |
| `electric_vehicle_smoothing_factor` | `float` | `0.2` | Smoothing factor for the power curve (value has to be between 0 and 1). |
| `electric_vehicle_reserve_duration` | `Duration` | `1 min` | Manual reserve duration. |
| `electric_vehicle_automated_reserve_duration` | `Duration` | `1 min` | Automated reserve duration. |

## Numerical Stability

| Parameter | Type | Default | Description |
|---|---|---|---|
| `allowed_round_off_error` | `float` | `0.01` MW | Below this value, optimization results will be rounded. |

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

- [Input Objects](input-objects.md): Required input data and attributes
- [Results](results.md): Understanding outputs
