# Module Architecture

## Overview

The Market Clearing module follows ATLAS's `AbstractModule` pattern. See [Module Pattern](../../../concepts/module-pattern.md) for details on the standard module architecture.

This document describes the module-specific architecture and components.

## Module Structure

```

market_clearing/
├── main.py                              # Execution entry point
├── market_clearing_constants.py         # Global constants
├── market_clearing_parameters.py        # Configuration parameters
├── market_clearing_input_dataset.py     # Input data aggregation
├── market_clearing_output_dataset.py    # Output data aggregation
├── marker_clearing_module.py            # Core clearing module
├── price_group.py                       # group of market area with the same price for every timestep
└── models/                              # Market Clearing models
│   ├── control_block_mc.py
│   ├── critical_branch_mc.py
│   ├── market_area_mc.py
│   ├── market_area_ptdf_mc.py
│   ├── market_border_mc.py
│   ├── order_mc.py
│   └── order_coupling_mc.py
└── phases/                              # Market Clearing phases
│   ├── clearing.py                      # First phase of market clearing
│   ├── exchange_fixing.py               # second phase of market clearing
│   ├── pricing.py                       # Third phase of market clearing
│   ├── marginal_fixing.py               # Fourth phase of market clearing
│   ├── market_clearing_results.py       # Export of files
```

## Core Classes

### MarketClearingModule

Implements `AbstractModule` with methods:

- `get_parameters_class()`: Returns `MarketClearingParameters`
- `import_data()`: Creates `MarketClearingInputDataset`
- `validate_data()`: Nothing is done
- `execute()`: Run every step of the Market Clearing. Returns `MarketClearingOutputDataset`
- `validates_results()`: Nothing is done
- `export_results()`: Run `MarketClearingResults`

### MarketClearingParameters

Pydantic model inheriting from `AbstractModuleParameters`. Defines all configuration parameters (see [Parameters](../user-guide/input-data.md)).

### MarketClearingInputDataset

- Converts business models to market-clearing-specific models (more information below on the section about them)
- Filter to input to keep only useful data
### MarketClearingOutputDataset

Update dataset with the result of MarketClearing : All modification of attributes are write in docstring of MarketClearingOutput

## Models

### OrderMC

- Test if the order is feasible
- Add timestep of use
- Add information about associated OrderCoupling

### OrderCouplingMC

- Test if the OrderCoupling is feasible

### PriceGroup

Keep information of price for every timestep :

- Min/Max price
- List of MarketArea with the same price

## Data Flow

```
run(raw_data, raw_params)
  ↓
import_parameters() → MarketClearingParameters
  ↓
import_data() → MarketClearingInputDataset
  ↓
validate_data()
  ↓
execute()
  ├→ Clearing.run()
  ├→ ExchangeFixing.run()
  ├→ Pricing.run()
  ├→ MarginalFIxing.run()
  └→ MarketClearingResult.runt()
  ↓
validates_results()
  ↓
export_results() → update price value of equipments/portfolios and flow value
```

## Module-Specific Design Patterns

For common ATLAS patterns (module lifecycle, Pydantic models, solver interface), see [Module Pattern](../../../concepts/module-pattern.md).

**Four-phase Execution**: Market clearing is performed in 4 sequential phases (Clearing, Exchange Fixing, Pricing, Marginal Fixing)

**Price Groups**: Market areas with identical prices are grouped together for efficiency

**Network Constraints**: PTDF (Power Transfer Distribution Factors) model transmission constraints
