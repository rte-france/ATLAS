# Module Architecture

## Overview

The Intraday Orders module follows ATLAS's `AbstractModule` pattern. See [Module Pattern](../../module-pattern.md) for details on the standard module architecture.

This document describes the module-specific architecture and components. Unlike the Day-Ahead module, no optimisation problem is solved — every asset type is handled by a dedicated heuristic *formulator*.

## Module Structure

```
atlas/modules/intraday_orders/
├── module.py                            # IntradayOrdersModule (AbstractModule)
├── parameters.py                        # IntradayOrdersParameters
├── input_dataset.py                     # IntradayOrdersInputDataset
├── output_dataset.py                    # IntradayOrdersOutputDataset (builds change sets)
├── utils.py                             # engaged_quantity(), build_intraday_order()
├── models/
│   ├── enums.py                         # PlanningDelta, WindowType, InflexibleChaining
│   └── thermal_order_window.py          # ThermalOrderWindow
├── input_objects/                       # Equipment-specific models (one per asset)
│   ├── hydro.py
│   ├── load.py
│   ├── other_non_dispatchable.py
│   ├── solar.py
│   ├── storage.py
│   ├── thermal.py
│   └── wind.py
└── orders_formulation/                  # One formulator per asset type
    ├── abstract_orders.py               # AbstractOrdersFormulator (base)
    ├── abstract_orders_with_curtailment.py  # shared wind/solar logic
    ├── hydro.py
    ├── load.py
    ├── non_dispatchable.py
    ├── solar.py
    ├── storage.py
    ├── thermal.py
    └── wind.py
```

## Core Classes

### **`IntradayOrdersModule`**

Implements `AbstractModule` with methods:

- `get_parameters_class()`: Returns `IntradayOrdersParameters`
- `import_data()`: Creates `IntradayOrdersInputDataset` (after harmonising the input frequency to the timestep)
- `validate_data()`: Currently a no-op (returns `True`)
- `execute()`: Runs every formulator over the order window and collects orders and couplings
- `validates_results()`: No-op
- `export_results()`: No-op

### **`IntradayOrdersParameters`**

Pydantic model inheriting from `AbstractModuleParameters`. Defines the module parameters (see [Parameters](../user-guide/parameters.md)) and the derived `penultimate_date` (the last time step before `end_date`).

### **`IntradayOrdersInputDataset`**

Converts core business models into intraday-orders-specific input objects (`HydroIDO`, `ThermalIDO`, …).

### **`IntradayOrdersOutputDataset`**

Collects the generated `order` / `order_coupling` lists and, in `build_change_sets()`, emits `AddObject` change sets for them plus `UpdateObject` change sets writing each unit's submitted volumes back onto the equipment.

### **`AbstractOrdersFormulator`**

Base class for all formulators. `formulate()` loops over the equipments; `process_equipment()` calls the abstract `formulate_equipment_orders()` and then accumulates the per-session and cumulative submitted volumes onto the equipment. Each concrete formulator implements `formulate_equipment_orders()`.

## Shared Helpers (`utils.py`)

- **`engaged_quantity(equipment, parameters)`**: Computes the cleared engagement (`da_cleared_quantity + total_id_cleared_quantity`) over the order window, zero-filled where Day-Ahead data does not cover it.
- **`build_intraday_order(...)`**: Factory building an `Order` with `Product.Intraday` for a single timestep.

## Thermal Specifics

The thermal formulator is the most involved:

1. **`compute_planning_delta()`** classifies each timestep as `STARTUP`, `SHUTDOWN`, `MODULATION_UP/DOWN` or `NO_CHANGE` by comparing the cleared engagement to the target planning against `minimum_power`.
2. **`build_order_windows()`** groups consecutive timesteps of the same delta code into runs and labels each run with a `WindowType` (`NEW_START`, `BRIDGE_UP`, `EXTENDED_END`, …) depending on whether the unit was running just before/after the window.
3. The **`_WINDOW_CONFIGS`** table maps each `WindowType` to its bidding configuration (order side, iteration direction, start-up cost sign, inflexible chaining, flex/inflex coupling type), driving order and coupling generation.

`PEAK` units bypass the window machinery and are offered independently per timestep.

## Data Flow

```
run(raw_data, raw_params)
  ↓
import_parameters() → IntradayOrdersParameters
  ↓
import_data() → IntradayOrdersInputDataset
  ↓
validate_data()
  ↓
execute()
  ├→ for each asset formulator: formulate(equipments, order_window, parameters)
  │     ├→ build Orders and OrderCouplings (the target_planning − cleared_engagement delta)
  │     └→ accumulate id_*/total_id_* submitted volumes onto each equipment
  └→ IntradayOrdersOutputDataset is filled
  ↓
build_change_sets() → AddObject(order/coupling) + UpdateObject(submitted volumes)
  ↓
export_results()
```

## Module-Specific Design Patterns

For common ATLAS patterns (module lifecycle, Pydantic models), see [Module Pattern](../../module-pattern.md).

- **Formulator per asset**: Each equipment type has an independent formulator sharing the `AbstractOrdersFormulator` interface; wind and solar share `AbstractOrdersFormulatorWithCurtailment`.
- **Heuristic, not optimisation**: All orders are derived analytically from the engagement/target-planning delta — there is no solver call.
- **Cumulative engagement**: Submitted volumes accumulate across successive intraday sessions via the `total_id_*` attributes.
