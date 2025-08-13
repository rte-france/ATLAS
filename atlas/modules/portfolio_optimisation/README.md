# Portfolio Optimization Module - Timeframe Guide

This document provides a comprehensive mapping of optimization timeframes used across different equipment types in the Portfolio Optimization module.

## Overview

The Portfolio Optimization module uses different optimization horizons for different equipment types, allowing each technology to optimize according to its operational characteristics and market participation needs.

## Core Timeframe Architecture

### 1. Master Timeframe (`max_optimisation_times`)

**Location**: `input_dataset.py:67,80-82`
```python
self.max_optimisation_times = self._get_longest_optimization_period()
```

- **Definition**: The longest optimization period among all equipment types
- **Usage**: Used by `PortfolioOptimisationModel.build_model()` as the master loop timeframe
- **Source**: `max(all_optimization_times, key=len)` - automatically selects the longest period
- **Purpose**: Ensures the optimization model covers the full timespan needed by any equipment

### 2. Base Time Properties (`parameters.py`)

| Property | Definition | Usage |
|----------|------------|--------|
| `target_times` | `start_date` to `adjusted_end_date` | Main market participation period |
| `adjusted_end_date` | `end_date - timestep` | Base for calculating extended periods |
| `timestep` | Time resolution (default: 1 hour) | Step size for all time series |

## Equipment-Specific Optimization Timeframes

### Renewable Energy & Load Equipment

#### Solar & Wind (`SolarPO`, `WindPO`)
- **Timeframe**: `renewables_load_op_times` = `target_times + additional_hours`
- **Default Extension**: `additional_hours` = 12 hours
- **Code References**: 
  - `solar.py:30` - Variables only when `time in parameters.target_times`
  - `wind.py:28` - Variables only when `time in parameters.target_times`
- **Key Behavior**: Only operates during target times (no extended optimization)

#### Load (`LoadPO`)
- **Timeframe**: `renewables_load_op_times` = `target_times + additional_hours`
- **Default Extension**: `additional_hours` = 12 hours
- **Code Reference**: `load.py:27` - Variables/constraints only when `time in parameters.target_times`
- **Key Behavior**: Only operates during target times

### Storage Equipment

Storage equipment uses the most complex timeframe logic with type-specific optimization periods and fragment-based bidding.

#### Battery Storage
- **Timeframe**: `battery_op_times` = `target_times + battery_additional_hours`
- **Default Extension**: `battery_additional_hours` = 48 hours (2 days)
- **Fragments**: `battery_number_of_fragments` = 3
- **Smoothing**: `battery_smoothing_factor` = 0.2
- **Code Reference**: `storage.py:33-38`

#### Pumped Hydraulic Storage (PHS)
- **Timeframe**: `phs_op_times` = `target_times + pumped_hydraulic_storage_additional_hours`
- **Default Extension**: `pumped_hydraulic_storage_additional_hours` = 144 hours (6 days)
- **Fragments**: `pumped_hydraulic_number_of_fragments` = 3
- **Smoothing**: `pumped_hydraulic_smoothing_factor` = 0.2
- **Rationale**: Longest optimization period due to weekly pumping cycles

#### Electric Vehicle (EV)
- **Timeframe**: `ev_op_times` = `target_times + electric_vehicle_additional_hours`
- **Default Extension**: `electric_vehicle_additional_hours` = 0 hours
- **Fragments**: `electric_vehicle_number_of_fragments` = 3
- **Smoothing**: `electric_vehicle_smoothing_factor` = 0.2
- **Rationale**: No extension needed due to daily charging patterns

#### Storage Mapping (`parameters.py:274-292`)
```python
storage_mapping = {
    StorageType.BATTERY: {
        "optimisation_times": self.battery_op_times,
        "nb_fragment": self.battery_number_of_fragments,
        "smoothing_factor": self.battery_smoothing_factor,
    },
    StorageType.PUMPED_HYDRAULIC_STORAGE: {
        "optimisation_times": self.phs_op_times,
        "nb_fragment": self.pumped_hydraulic_number_of_fragments,  
        "smoothing_factor": self.pumped_hydraulic_smoothing_factor,
    },
    StorageType.ELECTRIC_VEHICLE: {
        "optimisation_times": self.ev_op_times,
        "nb_fragment": self.electric_vehicle_number_of_fragments,
        "smoothing_factor": self.electric_vehicle_smoothing_factor,
    },
}
```

### Hydro Equipment (`HydroPO`)

- **Timeframe**: `hydraulic_op_times` = `target_times + hydraulic_additional_hours`
- **Default Extension**: `hydraulic_additional_hours` = 12 hours
- **Code References**: 
  - `hydro.py:37` - Variables when `time in parameters.hydraulic_op_times`
  - `hydro.py:90` - Constraints when `time in parameters.hydraulic_op_times`
  - `hydro.py:113` - Additional constraints when `time in parameters.target_times`
- **Key Behavior**: Dual timeframe logic for variables vs constraints

### Thermal Equipment (`ThermalPO`)

- **Timeframe**: `thermal_op_times` = `target_times + thermal_additional_hours`
- **Default Extension**: `thermal_additional_hours` = 12 hours
- **Current Status**: ⚠️ **Disabled** - See `main.py:49-50` (TODO comment)
- **Optimization Period**: `thermal_optimization_period` = `len(target_times) + thermal_additional_hours/timestep`

## Model Building Process (`main.py:33-84`)

### Master Loop
```python
def build_model(self, max_optimisation_times: list[DateTime]) -> None:
    for time in max_optimisation_times:  # Uses longest optimization period
        # Add variables for all equipment
        # Add constraints for all equipment  
        # Add objectives for target_times only
```

### Key Behaviors

1. **Variables**: Added based on equipment-specific timeframes
2. **Constraints**: Added based on equipment-specific timeframes
3. **Objectives**: Only added for `target_times` (market participation period)
4. **Price Forecasts**: Only available for `target_times`

### Equipment Processing Order (`main.py:47-76`)
1. Portfolio variables
2. Equipment variables (by type)
3. Equipment constraints (by type)
4. Equipment objectives (target_times only, with price forecasts)
5. Portfolio constraints
6. Portfolio objectives

## Time Distinction Patterns

### Target Times vs Extended Times

| Aspect | Target Times | Extended Times |
|--------|-------------|----------------|
| **Purpose** | Market participation | Optimization lookahead |
| **Price Forecasts** | ✅ Available | ❌ Not available |
| **Objectives** | Full objectives | Simplified/no objectives |
| **Equipment Behavior** | All features active | Limited features |

### Equipment Behavior Patterns

1. **Simple Equipment** (Solar/Wind/Load): 
   - Only operate during `target_times`
   - Extended timeframes unused

2. **Complex Storage**: 
   - Operate during full extended periods
   - Different objectives inside/outside `target_times`
   - Fragment-based bidding with smoothing factors

3. **Hydro**: 
   - Uses both `hydraulic_op_times` and `target_times`
   - Different constraint sets for each timeframe

## Timeframe Hierarchy (Typical Length Order)

1. **EV Storage**: `target_times` only (0h extension)
2. **Renewables/Load/Hydro/Thermal**: `target_times + 12h`
3. **Battery Storage**: `target_times + 48h` (2 days)
4. **Pumped Hydraulic Storage**: `target_times + 144h` (6 days) ← Usually `max_optimisation_times`

## Configuration Parameters

### Duration Parameters (`parameters.py`)
```python
# Base extensions
additional_hours: Duration = 12h                    # Renewables, Load
hydraulic_additional_hours: Duration = 12h          # Hydro
thermal_additional_hours: Duration = 12h            # Thermal (disabled)

# Storage extensions  
battery_additional_hours: Duration = 48h            # Battery (2 days)
electric_vehicle_additional_hours: Duration = 0h    # EV (same day)
pumped_hydraulic_storage_additional_hours: Duration = 144h  # PHS (6 days)

# Time resolution
timestep: Duration = 1h                             # Optimization step size
```

### Storage Fragments & Smoothing
```python
# Number of bid fragments (for price curves)
battery_number_of_fragments: int = 3
pumped_hydraulic_number_of_fragments: int = 3  
electric_vehicle_number_of_fragments: int = 3

# Smoothing factors (0-1, for bid curve differentiation)
battery_smoothing_factor: float = 0.2
pumped_hydraulic_smoothing_factor: float = 0.2
electric_vehicle_smoothing_factor: float = 0.2
```

## Usage Examples

### Checking Equipment Timeframe Usage
```python
# In equipment model files:
if time in parameters.target_times:
    # Market participation logic
    add_objective_with_price_forecast()

if time in parameters.hydraulic_op_times:  # Equipment-specific
    # Extended optimization logic
    add_variables_and_constraints()
```

### Storage Type-Specific Logic
```python
# In storage.py:
storage_optimisation_times = parameters.storage_mapping[self.storage_type]["optimisation_times"]
if time in storage_optimisation_times:
    # Storage-specific optimization
```

---

## Files Referenced

- `main.py` - Master optimization model and timeframe usage
- `parameters.py` - Timeframe definitions and configuration
- `input_dataset.py` - Timeframe collection and max calculation
- `models/solar.py`, `models/wind.py` - Renewable equipment timeframes
- `models/load.py` - Load equipment timeframes  
- `models/hydro.py` - Hydro equipment dual timeframe logic
- `models/storage.py` - Storage equipment complex timeframe logic
- `models/thermal.py` - Thermal equipment timeframes (disabled)