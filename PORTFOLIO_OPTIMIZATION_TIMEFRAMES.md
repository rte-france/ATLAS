# Portfolio Optimization Module - Timeframe

## Core Timeframe Architecture

### 1. Master Timeframe (`max_optimisation_times`)

```python
self.max_optimisation_times = self._get_longest_optimization_period()
```

- **Definition**: The longest optimization period among all equipment types
- **Usage**: Used by `PortfolioOptimisationModel.build_model()` as the master loop timeframe
- **Purpose**: Ensures the optimization model covers the full timespan needed by any equipment

### 2. Base Time Properties

| Property | Definition | Usage |
|----------|------------|--------|
| `target_times` | `start_date` to `adjusted_end_date` | Main market participation period |
| `adjusted_end_date` | `end_date - timestep` | Base for calculating extended periods |
| `timestep` | Time resolution (default: 1 hour) | Step size for all time series |

## Equipment Methods - Actual Timeframes Used

### Solar Equipment (`SolarPO`)
- **`add_variables()`**: `if time in parameters.target_times` 
- **`add_constraints()`**: `if time in parameters.target_times`   
- **`add_objective()`**: `if time in parameters.target_times` 

### Wind Equipment (`WindPO`)
- **`add_variables()`**: `if time in parameters.target_times` 
- **`add_constraints()`**: `if time in parameters.target_times` 
- **`add_objective()`**: `if time in parameters.target_times` 

### Load Equipment (`LoadPO`)
- **`add_variables()`**: `if time in parameters.target_times` 
- **`add_constraints()`**: `if time in parameters.target_times` 
- **`add_objective()`**: `if time in parameters.target_times` 

### Hydro Equipment (`HydroPO`)
- **`add_variables()`**: `if time in parameters.hydraulic_op_times` 
- **`add_constraints()`**: 
  - `if time in parameters.hydraulic_op_times`  (basic constraints)
  - `if time in parameters.target_times`  (additional energy balance constraints)
- **`add_objective()`**: `if time in parameters.target_times` 

### Storage Equipment (`StoragePO`)
- **`add_variables()`**: `if time in storage_optimisation_times` 
- **`add_constraints()`**: `if time in storage_optimisation_times` 
- **`add_objective()`**: `if time in storage_optimisation_times` 


#### Storage Type Mapping:
- **Battery**: `storage_optimisation_times` = `battery_op_times` (target_times + 48h)
- **Pumped Hydraulic**: `storage_optimisation_times` = `phs_op_times` (target_times + 144h)  
- **Electric Vehicle**: `storage_optimisation_times` = `ev_op_times` (target_times + 24h)

### Thermal Equipment (`ThermalPO`) 
- **`add_variables()`**: `if time in parameters.thermal_op_times` 
- **`add_constraints()`**: Various timeframe checks (complex logic)
- **`add_objective()`**: Various timeframe checks (complex logic)
- **Status**: ⚠️ Currently **DISABLED** in main optimization loop

### Portfolio (`PortfolioPO`)
- **`add_variables()`**: No timeframe check (always executed)
- **`add_constraints()`**: `if time in parameters.target_times` 
- **`add_objective()`**: `if time in parameters.target_times` 


## Timeframe Summary Table

| Equipment Type | Variables | Constraints | Objectives | Default extension |
|---------------|-----------|-------------|------------|------------------|
| **Solar** | target_times | target_times | target_times | None (market only) |
| **Wind** | target_times | target_times | target_times | None (market only) |
| **Load** | target_times | target_times | target_times | None (market only) |
| **Hydro** | hydraulic_op_times | hydraulic_op_times + target_times | target_times | +12 hours |
| **Battery Storage** | battery_op_times | battery_op_times | battery_op_times | +48 hours (2 days) |
| **PHS Storage** | phs_op_times | phs_op_times | phs_op_times | +144 hours (6 days) |
| **EV Storage** | ev_op_times | ev_op_times | ev_op_times | +0 hours (same as target) |
| **Thermal** | thermal_op_times | thermal_op_times | thermal_op_times | +12 hours (DISABLED) |
| **Portfolio** | Always | target_times | target_times | None |

## Default Configuration Parameters

### Duration Extensions (added to target_times)
```python
additional_hours = 12h                               # Renewables, Load (UNUSED in practice)
hydraulic_additional_hours = 12h                     # Hydro 
thermal_additional_hours = 12h                       # Thermal (disabled)
battery_additional_hours = 48h                       # Battery Storage (2 days)
electric_vehicle_additional_hours = 24h               # EV Storage (same as target)
pumped_hydraulic_storage_additional_hours = 144h     # PHS Storage (6 days)
timestep = 1h                                        # Time resolution
```

## Important Notes

### Storage Special Behavior
- Storage can operate during extended periods BUT with different objectives
- Inside `target_times`: Don't use the price forecast, uses only fragment prices
- Outside `target_times`: Uses the price forecast and fragment prices

### Master Loop Efficiency
- Loop runs for `max_optimisation_times` (typically 6+ days)
- Most equipment only active during `target_times` (typically 1 day)
- Only storage and hydro use extended periods effectively