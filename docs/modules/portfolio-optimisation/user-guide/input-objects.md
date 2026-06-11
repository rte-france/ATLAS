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
| `price_forecast_medium` | `ForecastingMatrix` | Medium price scenario used when `use_forecast = True`. |

The following fields are conditionally required depending on the `market` and `use_forecast` parameters:

| Field | Type | Condition |
|---|---|---|
| `da_price` | `AbstractTimeseries` | Required when `market = DayAhead` and `use_forecast = False`. |
| `id_price` | `ForecastingMatrix` | Required when `market = Intraday` and `use_forecast = False`. |
| `id_price_forecast` | `ForecastingMatrix` | Required when `market = Intraday` and `use_forecast = True`. |
| `rr_activation_price` | `AbstractTimeseries` | Required when `market = rr_activation`. |
| `mfrr_activation_price` | `AbstractTimeseries` | Required when `market = mfrr_activation`. |

---

## Thermal Units

| Field | Type | Default | Description |
|---|---|---|---|
| `maximum_power` | `AbstractTimeseries` | — | Maximum dispatchable power (MW). |
| `variable_cost` | `AbstractTimeseries` | — | Variable production cost (€/MWh). |
| `maximum_fcr` | `float` | — | Maximum FCR (Frequency Containment Reserve) capacity (MW). |
| `maximum_afrr` | `float` | — | Maximum aFRR (automatic Frequency Restoration Reserve) capacity (MW). |
| `maximum_gradient` | `float` | `0.0` | Maximum power ramp rate. `0` means unconstrained. |
| `has_daily_energy_constraint` | `bool` | `False` | Whether a daily energy cap applies to this unit. |
| `minimum_stable_power_duration` | `Duration` | — | Minimum time at stable power level between ramp events. |
| `minimum_time_on` | `Duration` | — | Minimum time the unit must stay on after a start-up. |
| `minimum_time_off` | `Duration` | — | Minimum time the unit must stay off after a shutdown. |

---

## Storage Units

Supports Battery, Pumped Hydraulic Storage, and Electric Vehicle types.

| Field | Type | Description |
|---|---|---|
| `storage_type` | `StorageType` | Storage technology type (`BATTERY`, `PUMPED_HYDRO`, `ELECTRIC_VEHICLE`). |
| `maximum_power` | `AbstractTimeseries` | Maximum charge/discharge power (MW). |
| `minimum_power` | `AbstractTimeseries` | Minimum charge/discharge power (MW). |
| `maximum_energy` | `AbstractTimeseries` | Maximum energy that can be stored (MWh). |
| `minimum_state_of_charge` | `AbstractTimeseries` | Minimum state-of-charge ratio applied to `maximum_energy`. |
| `discharge_efficiency` | `float` | Ratio of energy injected to the system to energy withdrawn from storage. |
| `charge_efficiency` | `float` | Ratio of energy stored to energy withdrawn from the grid. |
| `maximum_fcr` | `float` | Maximum FCR capacity (MW). |
| `maximum_afrr` | `float` | Maximum aFRR capacity (MW). |
| `additional_hours` | `Duration` | Extra optimization horizon appended after `end_date`. |

---

## Hydro Units

| Field | Type | Description |
|---|---|---|
| `maximum_energy` | `AbstractTimeseries` | Maximum reservoir energy storage capacity (MWh). |
| `minimum_energy` | `AbstractTimeseries` | Minimum required reservoir level (MWh). |
| `maximum_power` | `AbstractTimeseries` | Maximum generation power (MW). |
| `minimum_power` | `AbstractTimeseries` | Minimum generation power (MW). |
| `initial_level` | `AbstractTimeseries` | Reservoir energy level at the start of the optimization horizon. |
| `storage_marginal_value` | `AbstractScenarioMatrix` | Water values used to price reservoir depletion (€/MWh). |
| `maximum_fcr` | `float` | Maximum FCR capacity (MW). |
| `maximum_afrr` | `float` | Maximum aFRR capacity (MW). |
| `additional_hours` | `Duration` | Extra optimization horizon appended after `end_date`. |

---

## Load Units

Dispatchable and non-dispatchable loads are handled separately based on `load_type`.

| Field | Type | Description |
|---|---|---|
| `load_type` | `LoadType` | Determines whether the unit is dispatchable or not. |
| `maximum_power_forecast` | `ForecastingMatrix` | Power forecasts indexed by execution date. |
| `additional_hours` | `Duration` | Extra optimization horizon appended after `end_date`. |

---

## Wind Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Power forecasts indexed by execution date. |
| `maximum_curtailment_ratio` | `AbstractTimeseries` | Maximum fraction of production that can be curtailed (0–1). |
| `maximum_fcr` | `float` | Maximum FCR capacity (MW). |
| `maximum_afrr` | `float` | Maximum aFRR capacity (MW). |
| `additional_hours` | `Duration` | Extra optimization horizon appended after `end_date`. |

---

## Solar Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Power forecasts indexed by execution date. |
| `maximum_curtailment_ratio` | `AbstractTimeseries` | Maximum fraction of production that can be curtailed (0–1). |
| `maximum_fcr` | `float` | Maximum FCR capacity (MW). |
| `maximum_afrr` | `float` | Maximum aFRR capacity (MW). |
| `additional_hours` | `Duration` | Extra optimization horizon appended after `end_date`. |

---

## Other Non-Dispatchable Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Power forecasts indexed by execution date. |
| `additional_hours` | `Duration` | Extra optimization horizon appended after `end_date`. |

---

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
