# Input Objects

This page describes the input data required by the Market Clearing module.

---

## Market Areas

| Field | Type | Description |
|---|---|---|
| `mc_orders` | `dict[str, Order]` | All orders assigned to this market area, indexed by order name. |

The following fields are optional and used when present:

| Field | Type | Default | Description |
|---|---|---|---|
| `reference_balance` | `AbstractTimeseries` | `0` | Zonal reference net position for flow-based constraints. |
| `maximum_price` | `AbstractTimeseries` | `initial_max_price` | Price cap for this market area. |
| `minimum_price` | `AbstractTimeseries` | `initial_min_price` | Minimum price for this market area. |

---

## Market Borders

The following fields are optional and used when present:

| Field | Type | Default | Description |
|---|---|---|---|
| `maximum_flow` | `AbstractTimeseries` | `10 000 MW` | Maximum flow from uphill to downhill area. |
| `minimum_flow` | `AbstractTimeseries` | `-10 000 MW` | Minimum flow (negative = reverse direction). |
| `reference_flow` | `AbstractTimeseries` | — | Reference flow in the base case. Subtracted from capacity bounds when present. |
| `loss_factor` | `float` | — | Network loss factor applied to border flows. |
| `time_resolution` | `float` | — | Border-specific time resolution (minutes). Rounded to the nearest multiple of `timestep` if needed. |

---

## Critical Branches (Flow-Based)

Used only when `exchange_constraints_type = FB`.

| Field | Type | Description |
|---|---|---|
| `maximum_flow` | `AbstractTimeseries` | Maximum power allowed on the branch (MW). |
| `flow_reliability_margin` | `AbstractTimeseries` | Safety margin subtracted from `maximum_flow` to account for forecast uncertainties. |
| `reference_flow` | `AbstractTimeseries` | Reference flow subtracted from `maximum_flow` in the base case. |

---

## Market Area PTDFs (Flow-Based)

Used only when `exchange_constraints_type = FB`.

| Field | Type | Description |
|---|---|---|
| `da_ptdf` | `AbstractTimeseries` | Zonal PTDF (Power Transfer Distribution Factor) for the Day-Ahead Flow-Based market. |

---

## Orders

| Field | Type | Description |
|---|---|---|
| `execution_date` | `DateTime` | Date when the order was submitted. |
| `start_date` | `DateTime` | Offer activation start. |
| `end_date` | `DateTime` | Offer activation end. |
| `product` | `Product` | Market product type (e.g. `DayAhead`, `Intraday`). Must match the `market` parameter. |
| `order_type` | `OrderType` | `Sell` or `Buy`. |
| `qmax` | `float` | Maximum accepted quantity (MW). |
| `qmin` | `float` | Minimum accepted quantity (MW). |

Orders are filtered at loading time based on dates, product match, market area scope, and the `execution_datetime_tolerance` parameter.

---

## Order Couplings

| Field | Type | Description |
|---|---|---|
| `coupling_type` | `CouplingType` | Coupling constraint type: `EXCLUSION`, `COMPLEMENT`, `IDENTICAL_VOLUME`, or `PARENT_CHILDREN`. |
| `complement_direction` | `ComplementDirection \| None` | Direction for complement constraints: `EqualTo`, `LesserThan`, or `GreaterThan`. |

---

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
