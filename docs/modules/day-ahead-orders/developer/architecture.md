# Module Architecture

## Overview

The Day-Ahead Orders module follows ATLAS's `AbstractModule` pattern. See [Module Pattern](../../../concepts/module-pattern.md) for details on the standard module architecture.

This document describes the module-specific architecture and components.

## Module Structure

```
atlas/modules/day_ahead_orders/
├── dao_timeseries.py                    # A specific implementation of timeseries
├── input_dataset.py                     # Input data structure
├── main.py                              # Execution entry point
├── module.py                            # The module DayAheadOrdersModule (AbstractModule)
├── output_dataset.py                    # Output data structure
├── orchestrator.py                      # Orchestrates the mains steps of the module execution
├── parameters.py                        # Module parameters
├── data_models/                         # Equipment-specific models
│   ├── hydro.py
│   ├── load.py
│   ├── market_area.py
│   ├── order.py
│   ├── order_coupling.py
│   ├── portfolio.py
│   ├── solar.py
│   ├── storage.py
│   ├── thermal.py
│   └── wind.py
├── optim_models/                        # Specific optim model classes based on OptimisationModel
│   ├── battery_model.py
│   ├── electric_vehicle_model.py
│   └── storage_model.py
├── orders_formulation/                  # Steps for each type of assets lead to fomulation of orders
│   ├── thermal/                         # Thermal specific logic
│   ├── hydraulic_step.py
│   ├── load_step.py
│   ├── non_dispatchable_step.py
│   ├── storage_step.py
│   ├── thermal_bidding_step.py
│   ├── wind_pv_step.py
```

## Core Classes

### **`DayAheadOrdersModule`**

Implements `AbstractModule` with methods:

- `get_parameters_class()`: Returns `DayAheadOrdersParameters`
- `import_data()`: Creates `DayAheadOrdersInputDataset`
- `validate_data()`: Validates timestep consistency
- `execute()`: Runs optimization via `DayAheadOrdersOrchestrator`
- `validates_results()`: Nothing is done
- `export_results()`: Nothing is done

### **`DayAheadOrdersParameters`**

Pydantic model inheriting from `AbstractParameters`. Defines all configuration parameters (see [Parameters](../user-guide/input-data.md)).

### **`DayAheadOrdersInputDataset`**

Converts business models to day-ahead-orders-specific models

### **`DayAheadOrdersOutputDataset`**

Update dataset with the result of orders formulation: see the lists "orders" and "order_coupling"

## Optimizations

There are 3 optimizations executed in the module:
ElectricVehicleModel and BatteryModel are created during the formulation of storage orders (see formulate_storage_orders())
ThermalOptimizationModel is created during the formulation of thermal intermediate load orders (see formulate_thermal_intermediate_load_orders())

## Data Flow

```
run(raw_data, raw_params)
  ↓
import_parameters() → DayAheadOrdersParameters
  ↓
import_data() → DayAheadOrdersInputDataset
  ↓
validate_data() → timestep consistency check
  ↓
execute() → DayAheadOrdersOrchestrator
  ├→ execute the 6 step of orders formulation
  └→ DayAheadOrdersOutput is filled
  ↓
validates_results()
  ↓
export_results() → update order, order_coupling
```

## Module-Specific Design Patterns

For common ATLAS patterns (module lifecycle, Pydantic models, solver interface), see [Module Pattern](../../../concepts/module-pattern.md).

**Step-based Execution**: Orders are formulated in 6 distinct steps, one for each asset type

**Optimization Models**: Three specialized optimization models handle storage and thermal intermediate load orders

**Order Types**: Different order types (thermal, hydraulic, storage, non-dispatchable, load) are generated based on equipment type
