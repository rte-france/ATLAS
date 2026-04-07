# User Guide Overview

## Introduction

The Market Clearing module determines market equilibrium by matching supply and demand across multiple market areas while respecting economic and network constraints.

## What It Does

The module:

- **Matches supply and demand**: Finds equilibrium across market areas
- **Computes clearing prices**: Determines prices for each market area
- **Optimizes exchanges**: Calculates cross-border flows
- **Respects constraints**: Honors transmission capacity and economic limits

## How to Use

See [Running Modules](../../../concepts/running-modules.md) for the standard ATLAS module execution pattern.

## Module-Specific Workflow

Beyond the standard module lifecycle (see [Module Pattern](../../../concepts/module-pattern.md)), this module:

1. **Processes market orders**: Collects buy/sell orders from all equipment
2. **Builds optimization model**: Creates market clearing optimization
3. **Solves market**: Finds equilibrium prices and quantities
4. **Updates results**: Writes clearing prices to equipment/portfolios and flows to interconnections

## Key Outputs

The module produces:

- **Market clearing prices**: Price per market area and timestep
- **Accepted quantities**: Accepted portion of each order
- **Cross-border flows**: Power exchanges between market areas

## Market Mechanism

The module uses an **economic dispatch** approach:

- Maximizes social welfare (consumer surplus + producer surplus)
- Respects transmission capacity constraints
- Handles multiple interconnected market areas
- Determines locational marginal prices

## Next Steps

- [Parameters](input-data.md): Module-specific configuration options
- [Running](running.md): Execution details
