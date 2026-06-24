# Input Objects

This page describes the input data required by the Day-Ahead Orders module.

---

## Thermal Units

| Field | Type | Description |
|---|---|---|
| `variable_cost` | `AbstractTimeseries` | Variable cost of production (€/MWh). |
| `startup_cost` | `AbstractTimeseries` | Cost of starting up the unit (€). |
| `minimum_time_on` | `Duration` | Minimum time the unit must remain on after a start-up. |
| `maximum_power` | `AbstractTimeseries` | Maximum dispatchable power (MW). |
| `minimum_power` | `AbstractTimeseries` | Minimum power output when online (MW). |
| `minimum_stable_power_duration` | `Duration` | Minimum time at stable power level between ramp events. |
| `minimum_time_off` | `Duration` | Minimum time the unit must stay off after a shutdown. |
| `additional_hours` | `Duration` | Extra optimization horizon appended after `end_date`. Controlled by the `thermal_additional_hours` parameter. |

---

## Storage Units

Supports Battery, Pumped Hydraulic Storage, and Electric Vehicle types.

| Field | Type | Description |
|---|---|---|
| `maximum_energy` | `AbstractTimeseries` | Maximum energy that can be stored (MWh). |
| `minimum_power` | `AbstractTimeseries` | Minimum charge/discharge power (MW). By convention, should be negative if the unit is able to withdraw energy from the network. |
| `maximum_power` | `AbstractTimeseries` | Maximum charge/discharge power (MW). |
| `storage_initial_level` | `float` | Initial state of charge as a fraction of `maximum_energy`. |
| `minimum_state_of_charge` | `AbstractTimeseries` | Minimum state-of-charge ratio applied to `maximum_energy`. |
| `additional_hours` | `Duration` | Extra optimization horizon appended after `end_date`. |

!!! note
    For Electric Vehicle storage, `displacement_energy` is also required.

---

## Load Units

| Field | Type | Description |
|---|---|---|
| `variable_cost` | `AbstractTimeseries` | Cost per MWh of load served (€/MWh). Used to value load-shedding orders. |

---

## Wind Units

| Field | Type | Description |
|---|---|---|
| `maximum_curtailment_ratio` | `AbstractTimeseries` | Maximum fraction of production that can be curtailed (0–1). |

---

## Solar Units

| Field | Type | Description |
|---|---|---|
| `maximum_curtailment_ratio` | `AbstractTimeseries` | Maximum fraction of production that can be curtailed (0–1). |

---

## Hydro Units

| Field | Type | Description |
|---|---|---|
| `maximum_energy` | `AbstractTimeseries` | Maximum reservoir energy storage capacity (MWh). |
| `minimum_energy` | `AbstractTimeseries` | Minimum required reservoir level (MWh). |
| `initial_level` | `AbstractTimeseries` | Reservoir energy level at the start of the optimization horizon. |
| `storage_marginal_value` | `AbstractScenarioMatrix` | Water values used to estimate the value of the energy currently stored in the reservoir (€/MWh). |
| `maximum_power` | `AbstractTimeseries` | Maximum generation power (MW). |
| `fragment_prices` | `list[float]` | Price spreads (one per fragment) applied to water values to build offer prices. |
| `fragment_volumes` | `list[float]` | Fractional volumes (one per fragment) dividing the power range into order fragments. Must match the length of `fragment_prices`. |

---

## Orders

| Field | Type | Description |
|---|---|---|
| `equipment` | `Equipment` | Associated equipment. |
| `execution_date` | `DateTime` | Date when the order is submitted. |
| `start_date` | `DateTime` | Order activation start. |
| `end_date` | `DateTime` | Order activation end. |

---

## Order Couplings

| Field | Type | Description |
|---|---|---|
| `coupling_type` | `CouplingType` | Type of coupling constraint: `EXCLUSION`, `COMPLEMENT`, `IDENTICAL_VOLUME`, or `PARENT_CHILDREN`. |

---

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
