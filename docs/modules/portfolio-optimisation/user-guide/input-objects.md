# Input Objects

This page describes the input data required by the Portfolio Optimisation module.

---

## Portfolio

The top-level container aggregating a market area, a control block, and all associated equipment.

| Field | Type | Description |
|---|---|---|
| `market_area` | `MarketArea` | Associated market area with price forecast data. |
| `control_block` | `ControlBlock` | Associated control block. |
| `equipments` | `PortfolioEquipments` | Typed container grouping all equipment by technology. |

---

## Market Areas

| Field | Type | Description |
|---|---|---|
| `price_forecast_medium` | `ForecastingMatrix` | Medium day-ahead price scenario, used as the price reference in the extended optimization time frame of storage and thermal equipments. |

The following fields are conditionally required depending on the `market` and `use_forecast` parameters:

| Field | Type | Condition |
|---|---|---|
| `da_price` | `AbstractTimeseries` | Required when `market = DayAhead` and `use_forecast = False`. Used to estimate the Imbalance Settlement Price. |
| `id_price` | `ForecastingMatrix` | Required when `market = Intraday` and `use_forecast = False`. Used to estimate the Imbalance Settlement Price. |
| `id_price_forecast` | `ForecastingMatrix` | Required when `market = Intraday` and `use_forecast = True`. |
| `rr_activation_price` | `AbstractTimeseries` | Required when `market = rr_activation`. Used to estimate the Imbalance Settlement Price. |
| `mfrr_activation_price` | `AbstractTimeseries` | Required when `market = mfrr_activation`. Used to estimate the Imbalance Settlement Price. |

---

## Thermal Units

| Field | Type | Default | Description |
|---|---|---|---|
| `maximum_power` | `AbstractTimeseries` | — | Maximum dispatchable power (MW). |
| `variable_cost` | `AbstractTimeseries` | — | Variable production cost (€/MWh). |
| `maximum_fcr` | `float` | — | Maximum FCR (Frequency Containment Reserve) capacity, as a ratio of `maximum_power`. |
| `maximum_afrr` | `float` | — | Maximum aFRR (automatic Frequency Restoration Reserve) capacity, as a ratio of `maximum_power`. |
| `maximum_gradient` | `float` | `0.0` | Maximum power ramp rate. `0` means unconstrained. |
| `has_daily_energy_constraint` | `bool` | `False` | Whether a daily energy cap is applied to this unit. |
| `minimum_stable_power_duration` | `Duration` | — | Minimum duration at a stable power level between ramps. |
| `minimum_time_on` | `Duration` | — | Minimum duration for which the unit must stay ON after a start-up. |
| `minimum_time_off` | `Duration` | — | Minimum duration for which the unit must stay OFF after a shutdown. |

---

## Storage Units

Includes Battery, Pumped Hydraulic Storage, and Electric Vehicle types.

| Field | Type | Description |
|---|---|---|
| `storage_type` | `StorageType` | Storage technology type (`BATTERY`, `PUMPED_HYDRO`, `ELECTRIC_VEHICLE`). |
| `maximum_power` | `AbstractTimeseries` | Maximum discharging power (MW), as generation is positive by convention in Atlas. |
| `minimum_power` | `AbstractTimeseries` | Maximum charging power (MW). |
| `maximum_energy` | `AbstractTimeseries` | Maximum reservoir storage capacity (MWh). |
| `minimum_state_of_charge` | `AbstractTimeseries` | Minimum state-of-charge, as a ratio applied to `maximum_energy`. |
| `discharge_efficiency` | `float` | Ratio of energy injected to the system to energy withdrawn from storage. |
| `charge_efficiency` | `float` | Ratio of energy stored to energy withdrawn from the grid. |
| `maximum_fcr` | `float` | Maximum FCR capacity, as a ratio of `maximum_power`. |
| `maximum_afrr` | `float` | Maximum aFRR capacity (MW), as a ratio of `maximum_power`. |
| `additional_hours` | `Duration` | Extended optimization horizon appended after `end_date`, to ensure that decisions made during the interval [`start_date`, `end_date`] are relevant with the following time steps. |

---

## Hydro Units

| Field | Type | Description |
|---|---|---|
| `maximum_energy` | `AbstractTimeseries` | Maximum reservoir storage capacity (MWh). |
| `minimum_energy` | `AbstractTimeseries` | Minimum required reservoir level (MWh). Usually relevant to represent regulatory constraints, can be set to 0 otherwise. |
| `maximum_power` | `AbstractTimeseries` | Maximum generation power (MW). |
| `minimum_power` | `AbstractTimeseries` | Minimum generation power (MW). |
| `initial_level` | `AbstractTimeseries` | Reservoir energy level at the start of the optimization horizon. |
| `storage_marginal_value` | `AbstractScenarioMatrix` | Water values used to represent the value of the energy currently stored (taking into account possible gains if used on future markets) (€/MWh). |
| `maximum_fcr` | `float` | Maximum FCR capacity (MW), as a ratio of `maximum_power`. |
| `maximum_afrr` | `float` | Maximum aFRR capacity (MW), as a ratio of `maximum_power`. |
| `additional_hours` | `Duration` | Extended optimization horizon appended after `end_date`. |

---

## Load Units

Dispatchable and non-dispatchable loads are handled separately based on `load_type`.

| Field | Type | Description |
|---|---|---|
| `load_type` | `LoadType` | Determines whether the unit is dispatchable or not. Expected values : `BASELOAD`, `POWER_TO_GAS` or `NON_DISPATCHABLE_LOAD`. |
| `maximum_power_forecast` | `ForecastingMatrix` | Forecasts of the maximum power that can be produced by the unit, indexed by execution date (should be negative by Atlas convention) (MW). |
| `additional_hours` | `Duration` | Extended optimization horizon appended after `end_date`. |

---

## Wind Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Forecasts of the maximum power that can be produced by the unit, indexed by execution date (MW). |
| `maximum_curtailment_ratio` | `AbstractTimeseries` | Ratio of `maximum_power_forecast` that can be curtailed. 0 indicates that the unit cannot be curtailed at all, while 1 indicates that the unit is fully flexible. |
| `maximum_fcr` | `float` | Maximum FCR capacity (MW), as a ratio of `maximum_power_forecast` for the current `execution_date`. |
| `maximum_afrr` | `float` | Maximum aFRR capacity (MW), as a ratio of `maximum_power_forecast` for the current `execution_date`. |
| `additional_hours` | `Duration` | Extended optimization horizon appended after `end_date` (in hours). |

---

## Solar Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Forecasts of the maximum power that can be produced by the unit, indexed by execution date (MW). |
| `maximum_curtailment_ratio` | `AbstractTimeseries` | Ratio of `maximum_power_forecast` that can be curtailed. 0 indicates that the unit cannot be curtailed at all, while 1 indicates that the unit is fully flexible. |
| `maximum_fcr` | `float` | Maximum FCR capacity (MW), as a ratio of `maximum_power_forecast` for the current `execution_date`. |
| `maximum_afrr` | `float` | Maximum aFRR capacity (MW), as a ratio of `maximum_power_forecast` for the current `execution_date`. |
| `additional_hours` | `Duration` | Extended optimization horizon appended after `end_date` (in hours). |

---

## Other Non-Dispatchable Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Forecasts of the maximum power that can be produced by the unit, indexed by execution date (MW). |
| `additional_hours` | `Duration` | Extended optimization horizon appended after `end_date` (in hours). |

---

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
