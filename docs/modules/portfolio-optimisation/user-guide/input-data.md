# Parameters

## Overview

The Portfolio Optimisation module is configured through `PortfolioOptimisationParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

## Required Parameters

These parameters are inherited from `AbstractParameters`:

- **`start_date`** (DateTime): Start of the optimization period
- **`end_date`** (DateTime): End of the optimization period
- **`execution_date`** (DateTime): Date when the optimization is executed
- **`export_result`** (bool): Whether to export results

## Optimization Parameters

### Market & Solver

- **`timestep`** (Duration, default: 1 hour): Time step of the market

- **`market`** (MarketType, default: `dayahead`): Market type for optimization
    * Options: `"DayAhead"`, `"Intraday"`, `"RRActivation"`, `"MFRRActivation"`

- **`solver_name`** (SolverEnum, default: `XPRESS`): Optimization solver to use
    * Options: `"XPRESS"`, `"PNE"`, `"GLOP"`, `"SCIP"`, `"CP-SAT"`

- **`solver_timeout`** (Duration, default: 60 seconds): Maximum solve time

- **`solver_duality_gap`** (float, default: 0.0001): Duality gap for optimization

- **`use_presolve`** (bool, default: False): Enable solver presolve mode

### Optimization Scope

- **`is_portfolio_bidding`** (bool, default: True):
    * `True`: Optimize at portfolio level
    * `False`: Optimize individual units

- **`use_forecast`** (bool, default: False):
    * `True`: Use price forecasts (optimization before market)
    * `False`: Use actual prices

### Exclusions

- **`excluded_market_areas`** (list[str], default: None): Market areas to exclude from optimization
    * Format: List of strings (e.g., `["FR", "DE"]`)
    * Special values: `["all"]` or `["none"]`

- **`excluded_technologies`** (list[str], default: None): Equipment types to exclude
    * Format: List of strings (e.g., `["thermal", "wind"]`)
    * Options: `"thermal"`, `"storage"`, `"wind"`, `"solar"`, `"hydro"`, `"load"`, `"other_non_dispatchable"`
    * Special values: `["all"]` or `["none"]`

- **`excluded_thermal_strategy`** (list[str], default: None): Thermal strategies to manually activate
    * Format: List of strings (e.g., `["Peak", "Base"]`)
    * Options: `["Peak"]`, `["Intermediate"]`, `["Base"]`, `["all"]`, `["none"]`, or `None`


## Penalties & Pricing

### Imbalance Penalties

- **`imbalance_penalty_offset`** (float, default: 10 €/MWh): Offset when forecasting imbalance settlement price

- **`isp_forecast_lower_bound`** (float, default: 10 €/MWh): Lower bound of absolute ISP forecast

- **`small_imbalance_penalty`** (float, default: 0.1): Coefficient for small imbalance ISP

- **`large_imbalance_penalty`** (float, default: 0.2): Coefficient for large imbalance ISP

- **`small_imbalance_size`** (float, default: 0.15): Percentage of portfolio energy considered "small"

- **`maximum_imbalance`** (float, default: 100000 MW): Maximum allowed imbalance

### Reserve Penalties

- **`automated_unprocured_reserves_penalty`** (float, default: 30000 €/MW/h): Penalty for not providing automated reserves

- **`manual_unprocured_reserves_penalty`** (float, default: 30000 €/MW/h): Penalty for not providing manual reserves

## Storage Equipment Parameters

### Battery

- **`battery_number_of_fragments`** (int, default: 3): Number of power offer fragments

- **`battery_smoothing_factor`** (float, default: 0.2): Smoothing factor for power curve (0-1)

- **`battery_reserve_duration`** (Duration, default: 60 minutes): Manual reserve duration

- **`battery_automated_reserve_duration`** (Duration, default: 60 minutes): Automated reserve duration

### Pumped Hydraulic Storage

- **`pumped_hydraulic_number_of_fragments`** (int, default: 3): Number of power offer fragments

- **`pumped_hydraulic_smoothing_factor`** (float, default: 0.2): Smoothing factor for power curve

- **`pumped_hydraulic_reserve_duration`** (Duration, default: 60 minutes): Manual reserve duration

- **`pumped_hydraulic_automated_reserve_duration`** (Duration, default: 60 minutes): Automated reserve duration

- **`hydraulic_minimal_fragment_size`** (int, default: 100 MW): Minimal power for offers

### Electric Vehicle

- **`electric_vehicle_number_of_fragments`** (int, default: 3): Number of power offer fragments

- **`electric_vehicle_smoothing_factor`** (float, default: 0.2): Smoothing factor for power curve

- **`electric_vehicle_reserve_duration`** (Duration, default: 1 minute): Manual reserve duration

- **`electric_vehicle_automated_reserve_duration`** (Duration, default: 1 minute): Automated reserve duration

## Performance Parameters

- **`use_multiprocessing`** (bool, default: True): Use parallel processing for portfolios

- **`max_workers`** (int, default: None): Max parallel processes (None = CPU count)

- **`allowed_round_off_error`** (float, default: 0.01 MW): Rounding error threshold

## Example Configuration

```json
{
  "start_date": "2024-01-01T00:00:00",
  "end_date": "2024-01-02T00:00:00",
  "execution_date": "2023-12-31T12:00:00",
  "export_result": true,
  "market": "DayAhead",
  "solver_name": "XPRESS",
  "solver_timeout": "PT60S",
  "timestep": "PT1H",
  "is_portfolio_bidding": true,
  "use_forecast": false,
  "use_multiprocessing": true,
  "excluded_market_areas": ["FR", "DE"],
  "excluded_technologies": ["thermal"],
  "excluded_thermal_strategy": ["Peak"]
}
```

## Next Steps

- [Running](running.md): How to execute the module
- [Results](results.md): Understanding outputs
