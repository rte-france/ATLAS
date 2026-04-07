# Module Architecture

## Overview

The Portfolio Optimisation module follows ATLAS's `AbstractModule` pattern. See [Module Pattern](../../../concepts/module-pattern.md) for details on the standard module architecture.

This document describes the module-specific architecture and components.

## Module Structure

```
atlas/modules/portfolio_optimisation/
├── module.py                            # PortfolioOptimisationModule (AbstractModule)
├── parameters.py                        # PortfolioOptimisationParameters
├── input_dataset.py                     # PortfolioOptimisationInputDataset
├── output_dataset.py                    # PortfolioOptimisationOutputDataset
├── portfolio_orchestrator.py            # Orchestrates portfolio optimization
├── portfolio_optimisation_model.py      # OptimisationModel for single portfolio
├── models/                              # Equipment-specific models
│   ├── portfolio.py                     # PortfolioPO
│   ├── portfolio_equipments.py          # Equipment container
│   ├── thermal/                         # Thermal models
│   ├── hydro.py, storage.py, etc.       # Other equipment models
└── utils/                               # Utility functions
```

## Core Classes

### **`PortfolioOptimisationModule`**

Implements `AbstractModule` with methods:

- `get_parameters_class()`: Returns `PortfolioOptimisationParameters`
- `import_data()`: Creates `PortfolioOptimisationInputDataset`
- `validate_data()`: Validates timestep consistency
- `execute()`: Runs optimization via `PortfolioOptimisationOrchestrator`
- `validates_results()`: Validates outputs
- `export_results()`: Updates equipment and portfolio forecasts

### **`PortfolioOptimisationParameters`**

Pydantic model inheriting from `AbstractModuleParameters`. Defines all configuration parameters (see [Parameters](../user-guide/input-data.md)).

### **`PortfolioOptimisationInputDataset`**

Converts business models to portfolio-optimisation-specific models:

- Groups equipment by portfolio
- Applies manual activation rules
- Creates PO-specific models (ThermalPO, HydroPO, StoragePO, etc.)
- Calculates optimization time windows

### **`PortfolioOptimisationOrchestrator`**

Coordinates optimization for multiple portfolios:

- Creates `PortfolioOptimisationModel` for each portfolio
- Handles multiprocessing if enabled
- Returns optimization results

### **`PortfolioOptimisationModel`**

Extends `OptimisationModel` (solver interface):

- Builds optimization variables, constraints, and objectives
- Calls solver
- Returns solution

### **`PortfolioOptimisationOutputDataset`**

Processes optimization results:

- Extracts variable values
- Updates equipment `power` forecasts
- Updates portfolio `imbalance`

## Equipment Models

Each equipment type has a PO-specific model (e.g., `ThermalPO`, `HydroPO`) that implements:

- `add_variables()`: Create decision variables
- `add_constraints()`: Add equipment constraints
- `add_objective()`: Add cost/revenue terms
- `prefetch_forecasts()`: Load forecast data

## Data Flow

```
run(raw_data, raw_params)
  ↓
import_parameters() → PortfolioOptimisationParameters
  ↓
import_data() → PortfolioOptimisationInputDataset
  ↓
validate_data() → timestep consistency check
  ↓
execute() → PortfolioOptimisationOrchestrator
  ├→ PortfolioOptimisationModel.build()
  ├→ PortfolioOptimisationModel.solve()
  └→ PortfolioOptimisationResult
  ↓
validates_results()
  ↓
export_results() → update equipment.power, portfolio.imbalance
```

## Module-Specific Design Patterns

For common ATLAS patterns (module lifecycle, Pydantic models, solver interface), see [Module Pattern](../../../concepts/module-pattern.md).

**Multiprocessing**: Portfolios can be optimized in parallel when `use_multiprocessing=true`

**Equipment Models**: Each asset type (thermal, hydro, etc.) has a specialized model implementing optimization variables, constraints, and objectives

**Portfolio-level Coordination**: Imbalance penalties and portfolio constraints coordinate assets within a portfolio
