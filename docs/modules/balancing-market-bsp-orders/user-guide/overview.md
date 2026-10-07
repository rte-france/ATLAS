# User Guide Overview

## Introduction

The BSP Balancing Orders module creates the balancing energy orders of every eligible equipment for one balancing activation market (RR or mFRR, selected with `product_type`). Orders are generated for each timestep between `start_date` and the last timestep before `end_date`, using forecasts retrieved at `execution_date`.

## What It Does

The module:

- **Selects eligible equipment**: Keeps the units of the selected market areas, minus the excluded equipment and technologies, the non-dispatchable loads (`BASE_LOAD`, `OTHER_NON_DISPATCHABLE_LOAD`) and the thermal units in maintenance during the time frame.
- **Computes the available flexibility**: For each unit and timestep, compares the forecasted power to its power bounds and removes the volumes already procured on other reserve products.
- **Applies technical constraints**: Setup delay, maximum gradient, and technology-specific constraints (storage level, daily energy, on/off durations…).
- **Generates orders and order couplings**: Creates upward (Sell) and/or downward (Buy) orders per unit and timestep, and links thermal orders with couplings when needed.

## The Core Logic: Available Power

Every formulator starts from the same comparison:

```
upward_available   = maximum_power - forecasted_power - upward_procured
downward_available = forecasted_power - minimum_power - downward_procured
```

- **Upward order** (Sell): the unit increases its injection, or reduces its consumption.
- **Downward order** (Buy): the unit decreases its injection, or increases its consumption.

The procured volumes always include FCR and aFRR. The other balancing product is added as well, so the same flexibility is not offered twice: mFRR procured volumes when formulating RR orders, RR procured volumes when formulating mFRR orders. Missing procured forecasts count as zero.

Timesteps starting before `execution_date + setup_delay` are skipped, since the unit cannot react in time.

When `maximum_gradient` is non-zero, the available power is further limited so that the power trajectory never moves by more than one gradient step (`maximum_gradient × timestep`) between the studied timestep and its neighbours.

## Order Types by Equipment

- **Load**: Upward orders reduce consumption, downward orders increase it towards `maximum_power_forecast`. Priced at the variable cost.
- **Wind / Solar**: Downward orders curtail production down to `maximum_power_forecast × (1 - maximum_curtailment_ratio)`, priced at the variable cost. With `res_self_balancing`, upward orders are also offered, and the excess of forecasted power over `maximum_power_forecast` is offered as a dedicated downward order priced at `market_price_cap` (accepted at all costs).
- **Storage**: Orders are limited so that the stored energy stays within bounds until the next fixed market (see `conservative_stored_energy`). A pumped hydro storage cannot switch between pumping and turbining when its `transition_duration` lasts at least one timestep. Prices are the average of the previous clearing prices on the market area, increased when the energy already activated for balancing during the day becomes large.
- **Hydro**: The available power is split into price-ordered fragments. Fragment prices are the water value, interpolated at the current stored energy, plus a per-fragment spread. Daily energy limits are enforced when `has_daily_energy_constraint` is set.
- **Thermal**: The formulation depends on the unit's on/off status around each timestep:
    - **Running unit**: regular upward and downward orders, subject to the minimum stable power duration.
    - **Stopped unit**: upward orders that restart it, bounded by the neighbouring powers and the gradient. A full startup is offered as an indivisible order up to `minimum_power` carrying the startup cost, plus a divisible order above it, linked by a `PARENT_CHILDREN` coupling.
    - **Shutdown**: indivisible downward orders buying the whole output, priced with or without the startup cost depending on the on/off pattern and the minimum on/off times.

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
