# User Guide Overview

## Introduction

The Intraday Price Forecast module computes intraday price forecasts for each market area based on the difference between day-ahead and intraday consumption forecasts, weighted by price sensitivity ratios derived from high/low price scenarios.

## What It Does

The module:

- **Computes price sensitivity ratios**: Calculates how price changes with consumption variations using high/low scenarios
- **Calculates consumption deltas**: Determines differences between day-ahead and intraday residual consumption forecasts
- **Estimates price impact**: Applies sensitivity ratios to consumption changes to forecast price variations
- **Applies price caps**: Ensures forecasts stay within market-defined upper and lower bounds
- **Updates forecasting matrices**: Stores results in market area price forecast matrices

## How to Use

See [Running Modules](../../../concepts/running-modules.md) for the standard ATLAS module execution pattern.

## Module-Specific Workflow

Beyond the standard module lifecycle (see [Module Pattern](../../../concepts/module-pattern.md)), this module:

1. **Filters assets by market area**: Separates loads, solar, and wind by market area
2. **Computes price sensitivity ratio**: Uses high/low price and consumption scenarios
3. **Calculates consumption delta**: Compares intraday vs day-ahead residual consumption
4. **Determines baseline price**: Selects latest intraday or day-ahead price
5. **Forecasts new prices**: Combines baseline, sensitivity ratio, and consumption delta
6. **Applies constraints**: Ensures non-negativity and respects price caps
7. **Saves results**: Updates market area forecasting matrices

## Key Outputs

The module produces:

- **Intraday price forecasts**: Price forecasts per market area and execution date
- **Updated forecasting matrices**: Added to market area `id_price_forecast` attribute

## Price Forecasting Mechanism

The module uses a **sensitivity-based** approach:

- Calculates price sensitivity from scenario data: `(price_high - price_low) / (consumption_low - consumption_high)`
- Computes residual consumption change: `intraday_consumption - day_ahead_consumption`
- Estimates price impact: `price_sensitivity_ratio × consumption_delta`
- Adds impact to baseline price
- Scales if price caps are exceeded

## Next Steps

- [Parameters](input-data.md): Module-specific configuration options
- [Running](running.md): Execution details
