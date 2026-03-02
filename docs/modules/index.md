# Modules

Atlas provides three simulation modules for electricity market modeling. Each can be run independently or chained together in workflows.

## Available Modules

### Portfolio Optimisation

Optimizes energy asset portfolios (thermal, hydro, storage, renewables) to maximize profits under market conditions.

[Learn more →](portfolio-optimisation/index.md)

### Market Clearing

Simulates market clearing to determine prices and dispatch based on supply and demand bids.

[Learn more →](market-clearing/index.md)

### Day-Ahead Orders

Generates day-ahead market orders based on asset characteristics and market forecasts.

[Learn more →](day-ahead-orders/index.md)

## Quick Start

Run a single module:

```bash
atlas run parameters.yaml \
  --module PortfolioOptimisation \
  --dataset ./data/input/
```

Chain modules in a workflow:

```bash
atlas run workflow.yaml --workflow
```

## Resources

- [Running Modules](running-modules.md) - Execution methods and CLI usage
- [Module Pattern](module-pattern.md) - Standard module structure
- [Common Parameters](common-parameters.md) - Shared parameters
- [Your First Simulation](../getting_started/first-simulation.md) - Complete tutorial
