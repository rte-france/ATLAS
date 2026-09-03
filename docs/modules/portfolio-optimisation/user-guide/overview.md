# User Guide Overview

## Introduction

The Portfolio Optimisation module optimizes energy portfolios to determine optimal dispatch strategies for thermal, hydro, solar, wind, storage, and load assets. It can be run in two different modes:

- **Within the order formulation step** (currently, only for the Intraday market). In that case, **the optimal dipatch** obtained is based on market price forecasts, and **is then translated into market orders** by a later module.
- After the Market Clearing step, **to simulate the response of Balancing Responsible Parties to market results**. In that case, an estimation of the future Imbalance Settlement Price is performed within the module (based on the latest market prices available), and is used to penalize deviations from market commitments.

## What It Does

The module:

- **Optimizes dispatch**: Determines optimal power output for each asset
- **Handles multiple portfolios**: Processes all portfolios in the input dataset
- **Considers market conditions**: Accounts for prices, estimations of imbalance penalties, and operating constraints on each asset (ensuring that their output program is always feasible)
- **Supports multiple asset types**: Thermal, hydro, storage, solar, wind, and load

## Optimization Modes

**Portfolio-level** (`is_portfolio_bidding=true`):

- Optimizes entire portfolio considering the sum of market commitments of all its assets
- Coordinates assets within the portfolio
- Accounts for portfolio-level constraints

**Individual units** (`is_portfolio_bidding=false`):

- Optimizes each unit independently, based on individual market commitments
- No portfolio-level coordination
- Simpler but may be suboptimal

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
