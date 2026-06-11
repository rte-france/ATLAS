# User Guide Overview

## Introduction

The Portfolio Optimisation module optimizes energy portfolios to determine optimal dispatch strategies for thermal, hydro, solar, wind, storage, and load assets.

## What It Does

The module:
- **Optimizes dispatch**: Determines optimal power output for each asset
- **Handles multiple portfolios**: Processes all portfolios in the input dataset
- **Considers market conditions**: Accounts for prices, imbalance penalties, and constraints
- **Supports multiple asset types**: Thermal, hydro, storage, solar, wind, and load

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

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
