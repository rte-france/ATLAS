# Input Objects

This page describes the input data required by the BSP Balancing Orders module. Each eligible equipment is validated into a module-specific subclass (`BalancingHydro`, `BalancingThermal`, …) that makes the attributes below mandatory.

---

## Common Attributes

Every equipment relies on the same attributes to compute its available power.

| Field | Type | Description |
|---|---|---|
| `power` | `ForecastingMatrix` | Forecasted power schedule (MW), read at `execution_date`. Loads are negative (consumption). |
| `variable_cost` | `AbstractTimeseries` | Variable cost (€/MWh), used as the base order price. Not required for hydro. |
| `setup_delay` | `float` | Time needed to react to an activation order, in hours. Timesteps starting before `execution_date + setup_delay` get no order. |
| `maximum_gradient` | `float` | Maximum power variation per minute (MW/min). `0` means no gradient constraint. |
| `fcr_up_procured` / `fcr_down_procured` | `ForecastingMatrix \| None` | FCR volumes already procured (MW). Optional, zero if missing. |
| `afrr_up_procured` / `afrr_down_procured` | `ForecastingMatrix \| None` | aFRR volumes already procured (MW). Optional, zero if missing. |
| `mfrr_up_procured` / `mfrr_down_procured` | `ForecastingMatrix \| None` | mFRR volumes already procured (MW). Only used when `product_type` is `RRActivation`. Optional. |
| `rr_up_procured` / `rr_down_procured` | `ForecastingMatrix \| None` | RR volumes already procured (MW). Only used when `product_type` is `MFRRActivation`. Optional. |

!!! note
    Equipment is filtered before formulation: only the market areas listed in `market_area_names` are kept, minus `excluded_equipments` and `excluded_technologies`.

---

## Load Units

| Field | Type | Description |
|---|---|---|
| `load_type` | `LoadType` | `BASE_LOAD` and `OTHER_NON_DISPATCHABLE_LOAD` units are excluded from the module. |
| `maximum_power_forecast` | `ForecastingMatrix` | Maximum consumption forecast (MW, negative). Bounds the downward (consumption increase) orders. |

---

## Wind & Solar Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Maximum production forecast (MW). Bounds the upward orders and triggers self-balancing orders when exceeded by `power`. |
| `maximum_curtailment_ratio` | `AbstractTimeseries` | Maximum fraction of `maximum_power_forecast` that can be curtailed (0–1). |

---

## Storage Units

| Field | Type | Description |
|---|---|---|
| `storage_type` | `StorageType` | Storage technology. `PUMPED_HYDRAULIC_STORAGE` enables the transition constraint. |
| `maximum_power` / `minimum_power` | `AbstractTimeseries` | Discharge / charge power bounds (MW). `minimum_power` is negative when the unit can charge. |
| `stored_energy` | `ForecastingMatrix` | Stored energy forecast (MWh) over the storage constraint horizon. |
| `maximum_energy` | `AbstractTimeseries` | Energy capacity (MWh). |
| `minimum_state_of_charge` | `AbstractTimeseries` | Minimum stored energy, as a fraction of `maximum_energy`. |
| `charge_efficiency` / `discharge_efficiency` | `float` | Efficiencies used to convert the stored energy margin into power. |
| `transition_duration` | `Duration` | Time needed to switch between pumping and turbining (pumped hydro storage only). |
| `rr_activated` / `mfrr_activated` / `afrr_activated` / `fcr_activated` | `AbstractTimeseries` | Power activated on each balancing product during the current day (MW). |
| `specific_activated_power` | `ForecastingMatrix` | Other activated power during the current day (MW). |

!!! note
    Storage prices are computed from the market area of the unit's portfolio: `da_price` is required, `id_price` and `rr_activation_price` are averaged in when available.

---

## Hydro Units

| Field | Type | Description |
|---|---|---|
| `maximum_power` / `minimum_power` | `AbstractTimeseries` | Generation power bounds (MW). |
| `stored_energy` | `ForecastingMatrix` | Reservoir energy forecast (MWh), used to interpolate the water value. |
| `storage_marginal_value` | `AbstractScenarioMatrix` | Water-value curve (€/MWh) interpolated at the current stored energy. |
| `fragment_volumes` | `list[float]` | Fractions of `maximum_power` splitting the power range into order fragments. |
| `fragment_prices` | `list[float]` | Price spread added to the water value for each fragment. Must match the length of `fragment_volumes`. |
| `has_daily_energy_constraint` | `bool` | Whether the daily energy limits below apply. |
| `maximum_daily_energy` / `minimum_daily_energy` | `AbstractTimeseries` | Daily energy bounds (MWh). Required when `has_daily_energy_constraint` is `true`. |

---

## Thermal Units

| Field | Type | Description |
|---|---|---|
| `maximum_power` | `AbstractTimeseries` | Maximum power (MW). A unit with `maximum_power < 0.01` MW or below `minimum_power` at any timestep is considered in maintenance and excluded. |
| `minimum_power` | `AbstractTimeseries` | Minimum power when online (MW), used to detect startups and shutdowns and to size the indivisible startup order. |
| `startup_cost` | `AbstractTimeseries \| None` | Startup cost (€), spread over the quantity and duration of startup and shutdown orders. Zero if missing. |
| `startup_duration` | `Duration` | Time needed to start the unit. Orders restarting a unit that was off at the previous timestep are only offered once this time has elapsed since `execution_date`. Also used by the Case 4 shutdown check (see [Architecture](../developer/architecture.md#thermal-specifics)). |
| `minimum_time_on` / `minimum_time_off` | `Duration` | Minimum run and stop durations, checked around startup and shutdown orders. |
| `minimum_stable_power_duration` | `Duration` | Time the unit must stay at a constant power before (and after) a change. When longer than the timestep, it can make an order indivisible or invalid. |

---

## Orders

| Field | Type | Description |
|---|---|---|
| `equipment` | `Equipment` | Associated equipment. |
| `product` | `Product` | `RRActivation` or `MFRRActivation`, from `product_type`. |
| `order_type` | `OrderType` | `Sell` (upward) or `Buy` (downward). |
| `qmin` / `qmax` | `float` | Minimum and maximum order volume, rounded to the MW. `qmin == qmax` marks an indivisible order. |
| `price` | `float` | Order price (€/MWh), rounded to 2 decimals and capped by `market_price_cap`. |
| `execution_date` | `DateTime` | Date when the order is submitted. |
| `start_date` / `end_date` | `DateTime` | Order activation window (one timestep). |

---

## Order Couplings

| Field | Type | Description |
|---|---|---|
| `coupling_type` | `CouplingType` | `PARENT_CHILDREN` (thermal startup orders) or `EXCLUSION` (thermal orders on adjacent timesteps). |
| `orders` | `list[Order]` | The orders linked by the coupling. |

---

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
