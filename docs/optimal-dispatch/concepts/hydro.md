# Hydro

A hydro reservoir is a storage unit that fills itself. Water arrives whether or not you asked
for it, and every MWh you generate today is one you cannot generate tomorrow — which makes the
interesting question not *what does it cost to run* but *what is the water worth*.

`HydroDispatch` covers the physics. The valuation lives in
[`InterpolatedMarginalValue`](#water-values), shared by the modules but deliberately kept out of
the dispatch class.

## Decisions

| Variable | Range | Meaning |
|---|---|---|
| $E_t$ | $[0,\ \overline{E}_t]$ | Reservoir energy at the end of the timestep |
| $P^{k}_t$ | $[0,\ \overline{P}_t \cdot v_k]$ | Power on bid fragment $k$ |

Unlike thermal or storage, there is no single power variable. Generation is expressed directly
as a set of **fragments**, one per segment of the unit's bid curve, each capped at its share
$v_k$ of the unit's maximum power. Total generation is their sum:

$$
P_t = \sum_{k} P^{k}_t
$$

The fragments exist because each one is priced differently — see [below](#water-values).

## Reservoir balance

$$
E_t = E_{t-1} \;-\; \left(\sum_k P^{k}_t\right) \Delta t_{\text{h}} \;+\; I_t \cdot \Delta t_{\text{d}}
$$

Energy drains as the unit generates and refills with the natural inflow $I_t$. At the first
timestep, $E_{t-1}$ comes from `initial_level` at the step before the window.

Note the two different timestep conversions: generation is a power, so it converts with
$\Delta t$ in hours; inflows are supplied as a *daily* series, so they convert with $\Delta t$
in days.

## Water values

The marginal value of stored water — how much a MWh in the reservoir is worth to keep rather
than spend — depends on how full the reservoir is. A nearly empty reservoir hoards; a nearly
full one about to spill gives its water away.

Units declare this as a table: one price curve over time per discrete storage level
(`storage_marginal_value`). For an actual energy level sitting between two table rows, the value
is **linearly interpolated** between the curves bracketing it:

$$
\mu(t) = w^{\text{lo}} \cdot \mu^{\text{lo}}(t) + w^{\text{hi}} \cdot \mu^{\text{hi}}(t)
\qquad
w^{\text{lo}} = \frac{L^{\text{hi}} - E}{L^{\text{hi}} - L^{\text{lo}}},
\quad w^{\text{hi}} = 1 - w^{\text{lo}}
$$

Outside the table, the nearest curve is used unchanged (flat extrapolation). With an empty
table, the value is zero.

The effective bid price of a fragment is then its base price plus the marginal value of the
water it would consume. That sum is an *objective-side* quantity, which is why
`HydroDispatch` does not compute it — the calling module builds it from
[`InterpolatedMarginalValue`](../../api/optimal-dispatch/marginal-pricing.md).

## Reserves

Hydro reserves reuse the renewable shape, plus two specifics: a `relaxed_reserves` slack
absorbing infeasibility when the reservoir cannot meet its declared minimum power, and
constraints coupling reserved capacity to the stored-energy state — you cannot promise upward
reserve you have no water for. See [Reserves](../reserves/formulation.md#hydro).

## In code

- [`HydroDispatch`](../../api/optimal-dispatch/hydro.md) — the formulation.
- [`InterpolatedMarginalValue`](../../api/optimal-dispatch/marginal-pricing.md) — water values.
- [`HydroDispatchInput`](../developer/input-contracts.md#hydro) — the fields it reads.
- [Variable naming](../developer/variable-naming.md#hydro) — every emitted name.
