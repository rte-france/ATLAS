# Module Architecture

## Overview

The Market Clearing module follows ATLAS's `AbstractModule` pattern. See [Module Pattern](../../module-pattern.md) for details on the standard module architecture.

This document describes the module-specific architecture and components.

## Module Structure

```
market_clearing/
├── module.py                            # MarketClearingModule: runs the phases
├── parameters.py                        # MarketClearingParameters
├── input_dataset.py                     # MarketClearingInputDataset: input data aggregation
├── result.py                            # MarketClearingResult (builds change sets)
├── data_classes.py                      # PriceGroup, OrderLinks, ClearingOutputs...
├── order_links.py                       # OrderLinkResolver: links between orders
├── constants.py                         # Names of the constraints shared between phases
├── input_objects/                       # Market Clearing models
│   ├── critical_branch.py
│   ├── market_area.py
│   ├── market_area_ptdf.py
│   ├── market_border.py
│   ├── order.py
│   └── order_coupling.py
└── phases/                              # Market Clearing phases
    ├── clearing.py                      # First phase of market clearing
    ├── exchanges_fixing.py              # Second phase of market clearing
    ├── pricing/                         # Third phase of market clearing, in up to three attempts
    │   ├── pricing.py                   #   Pricing: runs the attempts until the model is feasible
    │   ├── first_attempt.py
    │   ├── second_attempt.py
    │   ├── third_attempt.py
    │   └── _types.py                    #   Variables and constraints handed from one attempt to the next
    ├── marginal_fixing.py               # Fourth phase of market clearing
    ├── market_clearing_results.py       # Export of files
    ├── _border_variables.py             # Border variables shared by Clearing and ExchangesFixing
    └── _helpers.py                      # Price group indexing, saturated critical branches
```

## Core Classes

### MarketClearingModule

Implements `AbstractModule` with methods:

- `get_parameters_class()`: Returns `MarketClearingParameters`
- `import_data()`: Creates `MarketClearingInputDataset`
- `validate_data()`: Nothing is done
- `execute()`: Run every step of the Market Clearing. Returns `MarketClearingResult`
- `validates_results()`: Nothing is done
- `export_results()`: Run `MarketClearingResults`

### MarketClearingParameters

Pydantic model inheriting from `AbstractModuleParameters`. Defines all configuration parameters (see [Parameters](../user-guide/parameters.md)).

### MarketClearingInputDataset

- Converts business models to market-clearing-specific models (more information below on the section about them)
- Filter to input to keep only useful data
### MarketClearingResult

Update dataset with the result of MarketClearing. The attributes updated for each market are listed in the tables at the top of `result.py` (`EQUIPMENT_FIELDS`, `PORTFOLIO_FIELDS`, `MARKET_AREA_PRICE_FIELDS`...), together with how the cleared window is merged into the history of each one: `APPEND`, `CUMULATE` or `FORECAST`.

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
  ├→ Clearing.compute()
  ├→ ExchangesFixing.compute()
  ├→ Pricing.compute()
  ├→ MarginalFixing.compute()
  └→ MarketClearingResult(...)
  ↓
validates_results()
  ↓
export_results() → update price value of equipments/portfolios and flow value
```

## Module-Specific Design Patterns

For common ATLAS patterns (module lifecycle, Pydantic models, solver interface), see [Module Pattern](../../module-pattern.md).

**Four-phase Execution**: Market clearing is performed in 4 sequential phases (Clearing, Exchange Fixing, Pricing, Marginal Fixing)

**Temporal Variables**: the phases declare their time-indexed variables as `TemporalVariable` families with `OptimisationModel.add_temporal_variable`, and hand the solved values to the next phase as one timeseries per market area, border or critical branch (`ClearingOutputs`)

**Price Groups**: Market areas with identical prices are grouped together for efficiency

**Network Constraints**: PTDF (Power Transfer Distribution Factors) model transmission constraints
