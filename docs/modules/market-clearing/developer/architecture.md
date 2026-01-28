# Module Architecture

## Overview

The Market Clearing module follows ATLAS's `AbstractModule` pattern, implementing standard lifecycle methods for data import, validation, execution, and export.

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

Pydantic model inheriting from `AbstractParameters`. Defines all configuration parameters (see [Parameters](../user-guide/input-data.md)).

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
-
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

## Key Design Patterns

**Module Pattern**: Follows `AbstractModule` for consistent lifecycle

**Pydantic Models**: Parameters and data validated via Pydantic

**Solver Interface**: Uses ATLAS `OptimisationModel` for solver abstraction
