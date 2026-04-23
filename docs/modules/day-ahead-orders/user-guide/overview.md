# User Guide Overview

## Introduction

The Day-Ahead Orders module computes all market orders based on equipment in the input dataset. Orders are generated for the period between `start_date` and `end_date`, using forecasts made at `execution_date`.

## What It Does

The module:

- **Generates orders**: Creates order objects for all equipment
- **Uses forecasts**: Based on data available at execution date
- **Supports multiple asset types**: Load, non-dispatchable, storage, hydraulic, wind, solar, and thermal
- **Updates business objects**: Stores orders directly in equipment objects

## How to Use

See [Running Modules](../../../concepts/running-modules.md) for the standard ATLAS module execution pattern.

## Module-Specific Workflow

Beyond the standard module lifecycle (see [Module Pattern](../../../concepts/module-pattern.md)), this module:

1. **Identifies equipment**: Finds all equipment in the input dataset
2. **Generates orders**: Creates appropriate orders for each equipment type
3. **Applies forecasts**: Uses forecast data from execution date
4. **Stores results**: Updates equipment with generated orders

## Order Types

The module generates different order types based on equipment:

- **Thermal units**: Generates thermal orders with cost curves
- **Hydro units**: Generates hydraulic orders with reservoir constraints
- **Storage units**: Generates storage orders with charge/discharge profiles
- **Wind/Solar**: Generates non-dispatchable orders based on forecasts
- **Load**: Generates load orders based on demand forecasts

## Next Steps

- [Parameters](input-data.md): Module-specific configuration options
- [Running](running.md): Execution details
