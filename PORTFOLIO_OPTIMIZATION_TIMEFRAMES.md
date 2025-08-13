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
- **`add_variables()`**: `if time in parameters.target_times` ✅
- **`add_constraints()`**: `if time in parameters.target_times` ✅  
- **`add_objective()`**: `if time in parameters.target_times` ✅

### Wind Equipment (`WindPO`)
- **`add_variables()`**: `if time in parameters.target_times` ✅
- **`add_constraints()`**: `if time in parameters.target_times` ✅
- **`add_objective()`**: `if time in parameters.target_times` ✅

### Load Equipment (`LoadPO`)
- **`add_variables()`**: `if time in parameters.target_times` ✅
- **`add_constraints()`**: `if time in parameters.target_times` ✅
- **`add_objective()`**: `if time in parameters.target_times` ✅

### Hydro Equipment (`HydroPO`)
- **`add_variables()`**: `if time in parameters.hydraulic_op_times` ✅
- **`add_constraints()`**: 
  - `if time in parameters.hydraulic_op_times` ✅ (basic constraints)
  - `if time in parameters.target_times` ✅ (additional energy balance constraints)
- **`add_objective()`**: `if time in parameters.target_times` ✅ (when price forecast available)

### Storage Equipment (`StoragePO`)
- **`add_variables()`**: `if time in storage_optimisation_times` ✅
- **`add_constraints()`**: `if time in storage_optimisation_times` ✅
- **`add_objective()`**: `if time in storage_optimisation_times` ✅


#### Storage Type Mapping:
- **Battery**: `storage_optimisation_times` = `battery_op_times` (target_times + 48h)
- **Pumped Hydraulic**: `storage_optimisation_times` = `phs_op_times` (target_times + 144h)  
- **Electric Vehicle**: `storage_optimisation_times` = `ev_op_times` (target_times + 0h)

### Thermal Equipment (`ThermalPO`) 
- **`add_variables()`**: `if time in parameters.thermal_op_times` ✅
- **`add_constraints()`**: Various timeframe checks (complex logic)
- **`add_objective()`**: Various timeframe checks (complex logic)
- **Status**: ⚠️ Currently **DISABLED** in main optimization loop

### Portfolio (`PortfolioPO`)
- **`add_variables()`**: No timeframe check (always executed)
- **`add_constraints()`**: `if time in parameters.target_times` ✅
- **`add_objective()`**: `if time in parameters.target_times` ✅

## Master Model Building Process

### Main Loop in `build_model()`:
```python
for time in max_optimisation_times:  # Iterates through longest optimization period
    # 1. Portfolio variables (always executed)
    # 2. Equipment variables (equipment-specific timeframe checks)
    # 3. Equipment constraints (equipment-specific timeframe checks)  
    # 4. Equipment objectives (only for target_times)
    # 5. Portfolio constraints (only for target_times)
    # 6. Portfolio objectives (only for target_times)
```

## Timeframe Usage Summary

### Equipment Categories by Actual Timeframe Used:

#### **Only Target Times** (Market participation only):
- **Solar/Wind/Load**: All methods use `if time in parameters.target_times`
- **Portfolio**: Constraints and objectives use `if time in parameters.target_times`

#### **Extended Timeframes** (Optimization lookahead):
- **Hydro**: Variables/constraints use `hydraulic_op_times`, objectives use `target_times`
- **Storage**: All methods use equipment-specific `storage_optimisation_times`
- **Thermal**: Uses `thermal_op_times` (but currently disabled)

#### **Master Timeframe**:
- **Model Loop**: Uses `max_optimisation_times` = longest among all equipment timeframes
- **Typically**: `phs_op_times` (target_times + 144h = 6 days)

## Actual Timeframe Periods (Default Configuration)

| Equipment Type | Variables | Constraints | Objectives | Typical Extension |
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
electric_vehicle_additional_hours = 0h               # EV Storage (same as target)
pumped_hydraulic_storage_additional_hours = 144h     # PHS Storage (6 days)
timestep = 1h                                        # Time resolution
```

### Key Insight: Renewables/Load Extensions are IGNORED
Even though `renewables_load_op_times` includes `additional_hours`, the actual equipment methods only check `target_times`, making the extension unused.

## Important Notes

### Price Forecast Availability
- **Only available for `target_times`** (market participation period)
- Equipment objectives that need prices must check `if time in parameters.target_times`

### Storage Special Behavior
- Storage can operate during extended periods BUT with different objectives
- Inside `target_times`: Uses price forecasts  
- Outside `target_times`: Uses fragment-based smoothed pricing

### Master Loop Efficiency
- Loop runs for `max_optimisation_times` (typically 6+ days)
- Most equipment only active during `target_times` (typically 1 day)
- Only storage and hydro use extended periods effectively