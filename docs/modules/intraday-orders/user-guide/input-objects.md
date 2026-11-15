# Input Objects

This page describes the input data required by the Intraday Orders module.

---

## Common Engagement Attributes

Every equipment relies on the same notion of *engagement* — what the unit is already committed to — and a *target planning* it wants to move towards.

| Field | Type | Description |
|---|---|---|
| `da_cleared_quantity` | `AbstractTimeseries` | Day-Ahead cleared quantity (MW). Required for every unit. |
| `total_id_cleared_quantity` | `AbstractTimeseries \| None` | Cumulative intraday cleared quantity over all prior sessions. `None` before the first intraday clearing (counted as zero). |
| `id_po_for_orders` | `ForecastingMatrix` | The new intraday target planning forecast, indexed by execution date (thermal and storage). |
| `maximum_power_forecast` | `ForecastingMatrix` | The new intraday production/consumption plan forecast (renewables, non-dispatchable, load). |

The *cleared engagement* used by every formulator is `da_cleared_quantity + total_id_cleared_quantity`. Buy/sell orders express the difference between the target planning and this engagement.

!!! note
    The intraday price forecast is read from `equipment.portfolio.market_area.id_price_forecast`. When it is absent, price-dependent formulators (storage, wind, solar, non-dispatchable) produce no orders for that unit.

---

## Thermal Units

| Field | Type | Description |
|---|---|---|
| `strategy` | `ThermalStrategy` | `BASE`, `INTERMEDIATE` or `PEAK`. Drives the formulation path. |
| `id_po_for_orders` | `ForecastingMatrix` | New intraday target planning. |
| `minimum_power` | `AbstractTimeseries` | Minimum power output when online (MW), used to detect startups/shutdowns. |
| `maximum_power` | `AbstractTimeseries` | Maximum dispatchable power (MW). |
| `startup_cost` | `AbstractTimeseries` | Start-up cost (€), amortised into the price of inflexible order blocks. |
| `variable_cost` | `AbstractTimeseries` | Variable cost of production (€/MWh), used as the base order price. |
| `minimum_time_on` | `Duration` | Minimum run duration; used by PEAK units to amortise the start-up cost. |

---

## Storage Units

| Field | Type | Description |
|---|---|---|
| `storage_type` | `StorageType` | Storage technology (e.g. Battery). |
| `id_po_for_orders` | `ForecastingMatrix` | New intraday target planning. |
| `minimum_power` | `AbstractTimeseries` | Minimum charge/discharge power (MW). |
| `maximum_power` | `AbstractTimeseries` | Maximum charge/discharge power (MW). |
| `discharge_efficiency` | `float` | Discharge efficiency, used in the round-trip price adjustment. |
| `charge_efficiency` | `float` | Charge efficiency, used in the round-trip price adjustment. |
| `variable_cost` | `AbstractTimeseries` | Variable cost (€/MWh). |

---

## Hydro Units

| Field | Type | Description |
|---|---|---|
| `fragment_volumes` | `list[float]` | Fractional volumes (one per fragment) dividing the available power into order fragments. |
| `fragment_prices` | `list[float]` | Price spreads (one per fragment) added to the water value to build offer prices. Must match the length of `fragment_volumes`. |
| `initial_level` | `AbstractTimeseries` | Reservoir energy level at the start of the horizon, used when no stored-energy forecast is available. |
| `storage_marginal_value` | `AbstractScenarioMatrix` | Water-value curve (€/MWh) interpolated at the current energy level. |
| `maximum_power` | `AbstractTimeseries` | Maximum generation power (MW). |

---

## Load Units

| Field | Type | Description |
|---|---|---|
| `load_type` | `LoadType` | Standard or `POWER_TO_GAS`. `POWER_TO_GAS` loads can both increase (buy) and reduce (sell) consumption. |
| `maximum_power_forecast` | `ForecastingMatrix` | New intraday demand forecast. |
| `variable_cost` | `AbstractTimeseries` | Cost per MWh (€/MWh), used to price `POWER_TO_GAS` orders. |

---

## Wind & Solar Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | New intraday production forecast. |
| `maximum_curtailment_ratio` | `AbstractTimeseries` | Maximum fraction of production that can be curtailed (0–1). |
| `variable_cost` | `AbstractTimeseries` | Variable cost of production (€/MWh). |

---

## Non-Dispatchable Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | New intraday production forecast. |
| `variable_cost` | `AbstractTimeseries` | Variable cost of production (€/MWh). |

---

## Orders

| Field | Type | Description |
|---|---|---|
| `equipment` | `Equipment` | Associated equipment. |
| `product` | `Product` | Always `Intraday` for this module. |
| `order_type` | `OrderType` | `Buy` or `Sell`. |
| `qmin` / `qmax` | `float` | Minimum and maximum order volume (MW). `qmin > 0` marks an inflexible block. |
| `price` | `float` | Order price (€/MWh). |
| `execution_date` | `DateTime` | Date when the order is submitted. |
| `start_date` / `end_date` | `DateTime` | Order activation window (one timestep). |

---

## Order Couplings

| Field | Type | Description |
|---|---|---|
| `coupling_type` | `CouplingType` | Type of coupling constraint: `EXCLUSION`, `COMPLEMENT`, `IDENTICAL_VOLUME`, or `PARENT_CHILDREN`. |
| `orders` | `list[Order]` | The orders linked by the coupling (e.g. a flexible block and its inflexible parent). |

---

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
