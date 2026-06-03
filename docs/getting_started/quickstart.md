# Quick Start Tutorial

Get up and running with Atlas in 5 minutes.

## Prerequisites

Before starting, ensure you have Atlas installed. If not, see the [Installation Guide](getting_started.md).

## Your First Command

Check that Atlas is properly installed:

```bash
atlas version
```

You should see output like:
```
Atlas version : 0.1.0
```

## Running a Simple Module

In the current version, Atlas provides three main modules for electricity market simulation. They correspond to the chain of modules simulating the Day-Ahead market:

- **DayAheadOrders** - Generates day-ahead market orders
- **MarketClearing** - Performs a market clearing, based on a set of market orders
- **PortfolioOptimisation** - Defines optimal generation and consumption plans to anwser results from MarketClearing


### Basic Module Execution

To run a module, you need:

1. A **parameters file** (YAML) - defines simulation settings for the current module
2. An **input dataset** - contains power system data (asset characteristics, geographical representation, market specificties, etc.)

```bash
atlas run parameters.yaml \
  --module PortfolioOptimisation \
  --dataset ./data/input/
```

## Running a Workflow

An electricity market is by nature comprised of several, sequential steps. For (relatively cnocise) multi-step simulations, use workflows:

```bash
atlas run workflow.yaml --workflow
```

Workflows chain multiple modules together, with outputs from one step feeding into the next.

## Next Steps

Now that you've got the basics, explore:

- [Your First Simulation](first-simulation.md) - Complete walkthrough with sample data
- [Module Pattern](../modules/module-pattern.md) - Understand Atlas architecture
- [CLI Reference](../cli.md) - Full command-line documentation
- [Examples](../examples/atlas_dataset.md) - Code examples and tutorials

## Getting Help

- Run `atlas --help` for command-line help
- Check the [API Reference](../api/io/atlas_dataset.md) for detailed documentation
- Visit the [GitHub repository](https://github.com/rte-france/ATLAS) for issues and discussions
