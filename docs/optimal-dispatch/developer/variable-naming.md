# Variable & Constraint Naming

Every variable and constraint in the layer is identified by a string. Solutions are read back by
name (`model.get_variable_value(...)`), exported LP files show nothing else, and regression tests
compare names byte for byte. The conventions below are therefore part of the public contract.

Throughout: `{n}` is the equipment name, `{t}` a `DateTime` rendered by `str()`.

!!! warning "The field order is not uniform"

    Thermal state booleans are named `{prefix}_{n}_{t}`, while the stable and gradient variables
    are named `{prefix}_{t}_{n}` — name and time swapped. This is inherited from the original
    module formulations and preserved on purpose so migrated modules produce identical LP files.
    Check the table before constructing a name by hand.

## Thermal

### Variables

| Name | Type | Meaning |
|---|---|---|
| `{n}_power_level_{t}` | continuous | Power output |
| `off_{n}_{t}` | binary | Unit is off |
| `on_start_{n}_{t}` | binary | On the startup ramp |
| `on_up_{n}_{t}` | binary | Online, ramping up |
| `on_flat_{n}_{t}` | binary | Online, stable |
| `on_down_{n}_{t}` | binary | Online, ramping down |
| `stop_{n}_{t}` | binary | On the shutdown ramp |
| `t_on_{n}_{t}` | binary | Turned on at this step |
| `t_off_{n}_{t}` | binary | Turned off at this step |
| `stable_{t}_{n}` | binary | Entered the stable phase |
| `entered_up_{t}_{n}` | binary | Entered the ramping-up phase |
| `entered_down_{t}_{n}` | binary | Entered the ramping-down phase |
| `flat_down_stop_{t}_{n}` | binary | Stable → down → stop chain |
| `down_to_stop_grad_{t}_{n}` | binary | Down → stop transition |
| `up_grad_{t}_{n}`, `down_grad_{t}_{n}` | continuous | Linearised directional gradients |
| `aux_up_grad_{t}_{n}`, `aux_down_grad_{t}_{n}` | continuous | Big-M intermediates |
| `dd_grad_{t}_{n}` | continuous | Gradient at the stable → stop chain |

Which of these exist depends on the unit's [combination](../concepts/thermal.md#the-eight-combinations).
Only `power_level`, `off`, `on_up`, `on_down`, `t_on` and `t_off` are always present.

### Constraints

| Name | Enforces |
|---|---|
| `t_on_evol_{1,2,3}_{t}_{n}` | Rising-edge linearisation of `t_on` |
| `t_off_evol_{1,2,3}_{t}_{n}` | Rising-edge linearisation of `t_off` |
| `stable_evol_{1,2,3}_{t}_{n}` | Rising-edge linearisation of `stable` |
| `entered_up_evol_{1,2,3}_{t}_{n}` | Rising-edge linearisation of `entered_up` |
| `entered_down_evol_{1,2,3}_{t}_{n}` | Rising-edge linearisation of `entered_down` |
| `mutual_exclusion_{t}_{n}` | Exactly one state active |
| `transition_constraint_{k}_{t}_{n}` | Forbidden state transitions ($k$ depends on the combination) |
| `lower_bound_{n}_{t}`, `upper_bound_{n}_{t}` | Power envelope, ramp-adjusted |
| `minimum_time_on_{n}_{local}_{t}` | Minimum up time, one row per lookback step |
| `minimum_time_off_{n}_{local}_{t}` | Minimum down time |
| `minimum_time_stable_{n}_{local}_{t}` | Minimum stable duration |
| `startup_ramp_{n}_{local}_{t}` / `start_up_ramp_…` | Startup ramp duration (second spelling when the unit has a stable phase) |
| `shutdown_ramp_{n}_{local}_{t}` | Shutdown ramp duration |
| `eviction_constraint_{t}_{n}` | Cannot re-enter a completed ramp |
| `stop_eviction_constraint_…`, `start_eviction_constraint_…` | Same, when the unit has both ramps |
| `tilde_U_evol_{1..4}_{t}_{n}`, `tilde_D_evol_{1..4}_{t}_{n}` | Big-M brackets for the gradient intermediates |
| `U_evol_{1..4}_{t}_{n}`, `D_evol_{1..4}_{t}_{n}` | Big-M brackets for the gradients |
| `DD_evol_{1..4}_{t}_{n}` | Big-M bracket for `dd_grad` |
| `flat_down_stop_evol_{1..4}_{t}_{n}` / `flat_down_stop_{1..4}_…` | Stable → down → stop chain (second spelling when the unit has a startup ramp) |
| `down_to_stop_evol_{1,2,3}_{t}_{n}` / `t_stop_evol_{1,2,3}_…` | Down → stop transition |
| `upward_gradient_{n}_{t}`, `downward_gradient_{n}_{t}` | Ramp rate limits |
| `unconstrained_upward_gradient_{n}_{t}`, `unconstrained_downward_gradient_{n}_{t}` | Same, for units with no declared gradient |
| `energy_limit_of_{n}_at_{day}` | Daily energy cap (one per calendar day) |

The `{local}` component in the minimum-time names is the timestep being looked *back* to, so each
row is uniquely identified by the pair (lookback step, current step).

## Storage

### Variables

| Name | Type | Meaning |
|---|---|---|
| `{n}_power_level_sell_{t}` | continuous ≥ 0 | Discharge power |
| `{n}_power_level_buy_{t}` | continuous ≤ 0 | Charge power |
| `{n}_is_sell_{t}` | binary | Discharging (1) vs charging (0) |
| `{n}_stored_energy_{t}` | continuous | State of charge |
| `{n}_power_level_sell_n_{i}_{t}` | continuous | Sell fragment $i$ |
| `{n}_power_level_buy_n_{i}_{t}` | continuous | Buy fragment $i$ |

### Constraints

| Name | Enforces |
|---|---|
| `storage_level_evol_{t}_{n}` | State-of-charge evolution |
| `relative_power_max_{t}_{n}` | `sell ≤ max_sell × is_sell` |
| `relative_power_min_{t}_{n}` | `buy ≥ min_buy × (1 − is_sell)` |
| `cycle_balance_{n}` | Horizon-wide energy balance (one per unit) |
| `sell_fragment_sum_{t}_{n}`, `buy_fragment_sum_{t}_{n}` | Fragments sum to the aggregate |

## Hydro

| Name | Type / enforces |
|---|---|
| `{n}_stored_energy_{t}` | continuous — reservoir energy |
| `{n}_power_level_frag_{category}_{t}` | continuous — power on bid fragment `category` |
| `storage_level_evol_{t}_{n}` | Reservoir energy balance |

Hydro deliberately reuses storage's `storage_level_evol` and `{n}_stored_energy_{t}` names — the
two never coexist on the same unit.

## Renewable and Load

| Name | Type / enforces |
|---|---|
| `{n}_power_level_{t}` | continuous — power output (negative for load) |
| `power_max_{t}_{n}` | Upper bound (forecast for renewable, 0 for load) |
| `power_min_{t}_{n}` | Lower bound (curtailment floor for renewable, forecast for load) |

Both are redundant with the variable bounds — see [LP parity](usage.md#lp-parity).

## Reserves

All reserve variables follow `{prefix}_{n}_{t}`, built by `ReserveHandler.var(prefix, time)`.
Use that method rather than formatting the string yourself.

| Prefix | Present on |
|---|---|
| `reserves_up`, `reserves_down` | all |
| `automated_reserves_up`, `automated_reserves_down` | all |
| `unprovided_reserves_up`, `unprovided_reserves_down` | all |
| `relaxed_reserves` | thermal, hydro |

### Constraints

| Name | Technology | Enforces |
|---|---|---|
| `up_fillup_{1,2}_{t}_{n}` | thermal | Upward fill-up equality (tolerance pair) |
| `down_fillup_{1,2}_{t}_{n}` | thermal | Downward fill-up equality |
| `generic_power_max_{t}_{n}` | storage | Upward fill-up inequality |
| `generic_power_min_{t}_{n}` | storage | Downward fill-up inequality |
| `reserves_up_max_{t}_{n}`, `reserves_down_max_{t}_{n}` | all | Manual reserve capacity |
| `automated_reserves_up_max_{t}_{n}`, `automated_reserves_down_max_{t}_{n}` | all | Automated reserve capacity |
| `relaxed_reserves_{t}_{n}` | thermal, hydro | Relaxed reserve bound |
| `min_storage_level_{t}_{n}`, `max_storage_level_{t}_{n}` | storage, hydro | Stored energy sufficient for committed reserve |

## Adding names

Two rules when writing a new dispatch or handler:

1. **Every constraint gets a name, and the name must be unique.** A collision silently replaces
   the earlier constraint rather than raising — the class of bug that shows up as an unexplained
   feasible solution. Where a loop can emit the same (name, time) pair twice, suffix with a
   distinguishing timestep; `_add_minimum_time_constraints` carries a comment explaining one such
   case.
2. **Include both the unit name and the timestep.** Models are built per portfolio across many
   units; a name missing either collides across units or across steps.

## See also

- [Usage — reading results](usage.md#reading-results)
- [Extending](extending.md)
