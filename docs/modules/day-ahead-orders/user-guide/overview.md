# User Guide Overview

## Introduction

The Day-Ahead Orders module creates all market orders for the Day-Ahead market, for all equipments in the input dataset. Orders are generated for the period between `start_date` and `end_date` (by convention, `end_date` being the end of the last time step considerd), using forecasts retrieved at `execution_date`.

## What It Does

The module:

- **Generates orders and order coupling**: Creates order objects for all equipment, and link them with order coupling when necessary (to translate technical or economical constraints into standard orders).
- **Uses forecasts and known power system state**: Based on data available at execution date
- **Supports multiple asset types**: Load, non-dispatchable, storage, hydraulic, wind, solar, and thermal
- **Updates business objects**: Stores orders directly in equipment objects

## Order Types

The module generates different order types based on equipment:

- **Thermal units**: Generates thermal orders, depending on the `strategy` attribute of each equipment. An heuristic is performed for Base and Peak units, while Intermediate unit orders are formulated with an optimization problem (computing the feasible programs for each unit). Coupling links are further used to represent technical constraints into market orders. Finally, variable and eventual startup costs are included in the price of orders generated.
- **Hydro units**: Generates hydraulic orders, with an heuristic taking into account reservoir constraints and water values.
- **Storage units**: Generates storage orders with charge/discharge profiles, computed with an optimization problem. All buy (resp. sell) orders have the same price, computed so that the unit remains profitable over the optimization period.
- **Wind/Solar**: Generates orders based on maximum power forecasts, priced according to the variable cost of each unit.
- **Load**: Generates load orders based on demand forecasts.

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
