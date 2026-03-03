# User Guide Overview

## Introduction

The Portfolio Optimisation module optimizes energy portfolios to determine optimal dispatch strategies for thermal, hydro, solar, wind, storage, and load assets.

## What It Does

The module:
- **Optimizes dispatch**: Determines optimal power output for each asset
- **Handles multiple portfolios**: Processes all portfolios in the input dataset
- **Considers market conditions**: Accounts for prices, imbalance penalties, and constraints
- **Supports multiple asset types**: Thermal, hydro, storage, solar, wind, and load

## How to Use

See [Running Modules](../../../concepts/running-modules.md) for the standard ATLAS module execution pattern.

## Module-Specific Workflow

Beyond the standard module lifecycle (see [Module Pattern](../../../concepts/module-pattern.md)), this module:

1. **Groups equipment by portfolio**: Organizes assets into portfolios
2. **Applies manual activation rules**: Excludes equipment based on configuration
3. **Runs optimization**: Uses solver to find optimal dispatch
4. **Updates results**: Writes `power` forecasts to equipment and `imbalance` to portfolios

## Optimization Modes

**Portfolio-level** (`is_portfolio_bidding=true`):
- Optimizes entire portfolio considering imbalance penalties
- Coordinates assets within the portfolio
- Accounts for portfolio-level constraints

**Individual units** (`is_portfolio_bidding=false`):
- Optimizes each unit independently
- No portfolio-level coordination
- Simpler but may be suboptimal

## Next Steps

- [Parameters](input-data.md): Module-specific configuration options
- [Running](running.md): Execution modes and options
- [Results](results.md): Accessing outputs
