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

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
