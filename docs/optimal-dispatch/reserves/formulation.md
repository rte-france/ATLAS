# Reserve Formulation

The variables and constraints the reserve layer adds on top of a dispatch. For what the products
are and why they are grouped in two families, read [Products](products.md) first.

## Variables

Each unit that can provide reserve gets six variables per timestep, plus a seventh for thermal
and hydro:

| Variable | Family | Meaning |
|---|---|---|
| `reserves_up`, `reserves_down` | manual | Capacity held for mFRR + RR |
| `automated_reserves_up`, `automated_reserves_down` | automated | Capacity held for FCR + aFRR, capped by `maximum_automated` |
| `unprovided_reserves_up`, `unprovided_reserves_down` | slack | Committed reserve the unit cannot physically supply |
| `relaxed_reserves` | slack | Thermal and hydro only — see [below](#slack-variables) |

The automated cap comes from the equipment:

$$
\text{maximum_automated} = \text{maximum_fcr} + \text{maximum_afrr}
$$

computed by [`ReserveFactory`](developer.md#the-factory) when it builds the handler.

## Slack variables

Two escape hatches keep the model solvable when the physics cannot deliver what was promised.

**`unprovided_reserves_up` / `unprovided_reserves_down`** — reserve that was committed but cannot
be supplied. The module penalises it in the objective at
`automated_unprocured_reserves_penalty` / `manual_unprocured_reserves_penalty` (30 000 €/MW/h by
default), so the solver reaches for it only when there is no alternative. A non-zero value in the
results is a signal, not a bug: it says the fleet was short.

**`relaxed_reserves`** (thermal and hydro) — absorbs the infeasibility of a unit that is offline,
or cannot reach its declared minimum power. The two technologies share the name and little else.

For thermal the variable is bounded $[0,\ \underline{P}_t]$ and forced to zero whenever the unit
*is* online:

$$
\text{relaxed_reserves}_t \le \underline{P}_t \cdot (1 - \text{online}_t)
$$

where $\text{online}_t$ sums `on_up`, `on_down` and, when the unit has one, `on_flat`.

Hydro has no operating state to gate on. Its variable is bounded $[\underline{P}_t,\ 0]$ and the
constraint is the plain $\text{relaxed_reserves}_t \le \underline{P}_t$.

Without these, one badly parameterised unit makes the whole portfolio infeasible, and you get no
solution at all rather than a diagnosable one.

## Fill-up: carving reserve out of the dispatch

The core coupling. Energy plus reserve must fit inside the unit's physical envelope.

### Thermal

Thermal fill-up is an **equality** — the unit's whole range is allocated, every MW either
produced or reserved:

$$
P_t + r^{\uparrow}_t + a^{\uparrow}_t + u^{\uparrow}_t = \overline{P}_t
$$

$$
P_t - r^{\downarrow}_t - a^{\downarrow}_t - u^{\downarrow}_t + \text{relaxed}_t = \underline{P}_t
$$

where $r$ is manual, $a$ automated and $u$ unprovided reserve. Both are implemented as a pair of
inequalities with a tolerance $\varepsilon$, so floating-point round-off in the bounds does not
make the model infeasible.

### Storage

Storage fill-up is an **inequality**, because a storage unit is not obliged to fill its range:

$$
P^{\text{sell}}_t + r^{\uparrow}_t + a^{\uparrow}_t + u^{\uparrow}_t \le \overline{P}^{\text{sell}}_t
$$

$$
P^{\text{buy}}_t - r^{\downarrow}_t - a^{\downarrow}_t - u^{\downarrow}_t \ge \underline{P}^{\text{buy}}_t
$$

Upward reserve eats into discharge headroom, downward reserve into charge headroom. The bounds
are the *effective* ones — accounting for V2G gating on an electric-vehicle fleet, which cannot
offer upward reserve at all if it cannot discharge.

## Capacity constraints

Fill-up bounds reserve by *power*. A second family bounds it by *availability* and, for
energy-limited units, by *stored energy*.

### Thermal

A unit that is off, starting or stopping cannot provide automated reserve at all:

$$
a^{\uparrow}_t,\ a^{\downarrow}_t \;\le\; \text{maximum_automated} \cdot (1 - \text{unavailable}_t)
$$

with $\text{unavailable}_t = \text{off}_t + \text{on_start}_t + \text{stop}_t$. For units with a
stable phase, manual reserve is additionally zeroed while ramping — a unit already moving cannot
credibly promise to move further on demand.

This is where reserve handling stops being generic: `ThermalReserveHandler` holds a reference to
its `ThermalDispatch` and reads its state variables directly. See
[Reading dispatch state](developer.md#reading-dispatch-state).

### Storage

A battery can only promise upward reserve it has the energy to deliver, for as long as the
product requires:

$$
E_t \;\ge\; \text{SOC}^{\min}_t \cdot \overline{E}_t + r^{\uparrow}_t \cdot d_r + a^{\uparrow}_t \cdot d_a
$$

$$
E_t \;\le\; \overline{E}_t - r^{\downarrow}_t \cdot d_r - a^{\downarrow}_t \cdot d_a
$$

where $d_r$ and $d_a$ are the durations the manual and automated products must be sustainable
for, in hours — `battery_reserve_duration` and `battery_automated_reserve_duration` in the module
parameters. Two MW of a one-hour product needs two MWh in the tank;
downward reserve symmetrically needs room to absorb.

All three of storage's downward variables are **bidirectional** — they start at a negative lower
bound rather than at zero, because a unit can provide downward reserve while discharging *or*
while charging. `automated_reserves_down` is bounded
$[-\text{maximum_automated}, +\text{maximum_automated}]$; `reserves_down` and
`unprovided_reserves_down` are bounded $[\underline{P}_t,\ \overline{P}_t]$, with
$\underline{P}_t$ the unit's (negative) charge floor. The upward variables all start at zero.

### Hydro

Same idea against the reservoir:

$$
E_t \ge E^{\min} + r^{\uparrow}_t + a^{\uparrow}_t
\qquad
E_t \le E^{\max} - r^{\downarrow}_t - a^{\downarrow}_t
$$

### Renewable

Wind and solar get the standard variable set and plain capacity bounds — no state coupling, since
there is no state to couple to.

## Which constraints apply where

| | Thermal | Storage | Hydro | Renewable |
|---|:-:|:-:|:-:|:-:|
| Fill-up (equality) | ✓ | | | |
| Fill-up (inequality) | | ✓ | | |
| Availability-gated capacity | ✓ | | | |
| Plain capacity bounds | | ✓ | ✓ | ✓ |
| Stored-energy coupling | | ✓ | ✓ | |
| `relaxed_reserves` | ✓ | | ✓ | |

Loads do not participate in reserve markets in this model, so there is no load handler.

## Next

- [Developer guide](developer.md) — building on the handlers.
- [Variable naming](../developer/variable-naming.md#reserves) — every emitted name.
