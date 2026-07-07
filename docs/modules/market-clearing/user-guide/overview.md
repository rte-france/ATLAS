# User Guide Overview

## Introduction

The Market Clearing module determines market equilibrium by matching supply and demand across multiple market areas while respecting economic and network constraints. It is suited for different types of product (wholesale energy markets, reserve procurement or reserve activation), and can deal with ATC or Flow-based modes for network constraints management.

## What It Does

The module:

- **Matches supply and demand**: Finds equilibrium across market areas
- **Computes clearing prices**: Determines prices for each market area
- **Optimizes exchanges**: Calculates cross-border flows
- **Respects constraints**: Honors transmission capacity and economic limits

## Key Outputs

The module produces:

- **Market clearing prices**: Price per market area and timestep
- **Accepted quantities**: On each market order, respecting its constraints and coupling links
- **Cross-border flows**: Power exchanges between market areas

## Market Mechanism

The module uses an **economic dispatch** approach, similar to Market Clearing algorithms of actual markets:

- Maximizes social welfare (consumer surplus + producer surplus)
- Respects transmission capacity constraints
- Handles multiple interconnected market areas
- Determines locational marginal prices

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
