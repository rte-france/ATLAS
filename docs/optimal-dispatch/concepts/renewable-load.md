# Renewable & Load

Wind, solar and load have no state and no memory. Their formulation is one variable per
timestep, bounded by a forecast. They are documented together because their only real subtlety
is the same one: which direction the bound points.

## Renewable

Wind and solar produce what the weather allows. The decision is not *how much to generate* but
*how much of the available production to accept*:

$$
(1 - c_t) \cdot \widehat{P}_t \;\le\; P_t \;\le\; \widehat{P}_t
$$

where $\widehat{P}_t$ is the forecast production and $c_t$ the
`maximum_curtailment_ratio` — the fraction of available production the unit is permitted to
spill. With $c_t = 0$ the unit is a must-take: lower and upper bound coincide and the forecast
is imposed. With $c_t = 1$ it can be curtailed to zero.

Curtailment is what makes a renewable unit a *decision* rather than a given. Without it, a
negative-price hour would force the model to keep injecting at a loss.

!!! note "The forecast must be pre-fetched"

    `RenewableDispatch` reads the forecast from the equipment's `_cached_forecast`, which the
    calling step is expected to populate (via `prefetch_forecasts()`) before any dispatch method
    runs. An empty cache yields a maximum power of zero — a silently idle unit rather than an
    error. Wiring a new renewable step, this is the first thing to check when a unit produces
    nothing.

## Load

Load is consumption, so its power is negative:

$$
\widehat{P}_t \;\le\; P_t \;\le\; 0
\qquad \widehat{P}_t \le 0
$$

The forecast *is* the lower bound. A load may consume less than forecast — that is demand-side
flexibility — but never more, and never inject.

Unlike renewables, `LoadDispatch` falls back to querying `maximum_power_forecast` directly when
the cache is empty, so it stays valid even if `prefetch_forecasts()` was not called.

Loads do not participate in reserve markets in this model, so there is no `LoadReserveHandler`.

## Redundant constraints

Both classes emit their bounds twice: once as variable bounds, which the solver enforces
directly, and once as explicit constraints. The duplication is deliberate — it keeps the
generated LP files byte-comparable with the reference files used in regression tests. It costs
two rows per unit per timestep and changes no solution.

## Wind and solar share no base class

`RenewableDispatchInput` is a `typing.Protocol`, not a Pydantic model, because `Wind` and
`Solar` do not descend from a common ancestor in the
[data model](../../data-model.md). Any object exposing `name`,
`maximum_curtailment_ratio` and `_cached_forecast` satisfies it, with no inheritance required —
so the day-ahead and portfolio-optimisation wind and solar objects all qualify as they stand.
See [Input contracts](../developer/input-contracts.md#renewable).

## In code

- [`RenewableDispatch`](../../api/optimal-dispatch/renewable.md),
  [`LoadDispatch`](../../api/optimal-dispatch/load.md) — the formulations.
- [`RenewableReserveHandler`](../reserves/formulation.md#renewable) — the reserve layer for wind and solar.
- [Variable naming](../developer/variable-naming.md#renewable-and-load) — every emitted name.
