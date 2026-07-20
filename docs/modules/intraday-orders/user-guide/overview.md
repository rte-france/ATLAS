# User Guide Overview

## Introduction

The Intraday Orders module creates all market orders for the Intraday market, for every equipment in the input dataset. Orders are generated for the period between `start_date` and `penultimate_date` (the last time step before `end_date`), using forecasts retrieved at `execution_date`.

## What It Does

The module:

- **Generates orders and order couplings**: Creates order objects for all equipment, and links them with order couplings when needed (to translate technical or economical constraints into standard orders).
- **Works from the cleared engagement**: For each unit it compares the *cleared engagement* (Day-Ahead plus all prior intraday clearings) to the *target planning* (the new intraday plan), and only offers the difference.
- **Supports multiple asset types**: Load, non-dispatchable, storage, hydraulic, wind, solar, and thermal.
- **Updates business objects**: Stores per-session and cumulative submitted volumes (`id_*_submitted_volume`, `total_id_*_submitted_volume`) directly on each equipment.

## The Core Logic: Selling a Surplus, Buying Back a Shortfall

Every formulator turns the same comparison into orders:

```
delta = target_planning - cleared_engagement
```

- `delta > 0`: the unit plans to produce/consume **more** than it is currently engaged for → **Sell** the surplus.
- `delta < 0`: the unit plans **less** than it is engaged for → **Buy** back the shortfall.

Volumes below `allowed_round_off_error` are ignored.

## Order Types by Equipment

- **Thermal units**: Behaviour depends on the `strategy` attribute. **Base** and **Intermediate** units are processed window by window — consecutive timesteps sharing the same change (startup, shutdown, modulation) are grouped into a classified *order window* (`NEW_START`, `BRIDGE_UP`, `EXTENDED_END`, …). Each window emits paired flexible/inflexible orders chained with couplings to express the commitment structure, with start-up costs amortised into the price. **Peak** units are offered independently per timestep.
- **Hydro units**: The available power is split into price-ordered fragments. Fragment prices are interpolated from the reservoir water-value curve at the current energy level. Fragments straddling the cleared engagement are split into a buy part and a sell part.
- **Storage units**: A single sell price and a single buy price are computed for the whole session, adjusted for round-trip efficiency so a full charge/discharge cycle stays profitable. Orders offer the per-timestep delta.
- **Wind / Solar**: Offer the production delta plus a separate curtailment order capturing the available (or over-committed) curtailment margin. Buy-backs are priced at the variable cost plus an imbalance-settlement penalty.
- **Non-dispatchable**: Same production-delta logic as wind/solar, without curtailment.
- **Load**: Standard loads compare cleared consumption to the new demand forecast. `POWER_TO_GAS` loads are flexible and can both increase (buy) and reduce (sell) consumption.

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
