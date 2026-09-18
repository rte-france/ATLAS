# Thermal

A thermal unit cannot simply follow a price signal. It takes time to start, it must run for a
while once started, it cannot change output arbitrarily fast, and it takes time to shut down.
`ThermalDispatch` encodes those limits as a small state machine plus a set of inter-temporal
constraints.

This is the longest formulation in the layer. If you read one concept page in depth, read this
one — storage and hydro are considerably simpler.

## The operating states

At every timestep a unit sits in exactly one state:

| State | Binary variable | Meaning |
|---|---|---|
| Off | `off` | Not running, producing nothing |
| Starting | `on_start` | Climbing the startup ramp, below minimum power |
| Ramping up | `on_up` | Running, output increasing |
| Stable | `on_flat` | Running, output held constant |
| Ramping down | `on_down` | Running, output decreasing |
| Stopping | `stop` | Descending the shutdown ramp, below minimum power |

Exactly one is active, which is the **mutual exclusion** constraint:

$$
\text{off}_t + \text{on_up}_t + \text{on_down}_t
\;[+\; \text{on_flat}_t]\;[+\; \text{stop}_t]\;[+\; \text{on_start}_t] = 1
$$

The bracketed terms appear only when the corresponding phase exists for that unit — which is
what the [combinations](#the-eight-combinations) below are about.

Two derived indicators mark the transitions:

- `turned_on` — fires on the timestep the unit leaves the off state.
- `turned_off` — fires on the timestep the unit begins shutting down.

Both are the standard linearisation of a rising edge on a binary $y$, i.e.
$\text{edge}_t \le y_t$, $\text{edge}_t \le 1 - y_{t-1}$, $\text{edge}_t \ge y_t - y_{t-1}$.
They are what the minimum-time constraints hang off.

Not all transitions are legal — you cannot jump from ramping-up straight to off, for instance.
A family of **transition constraints** of the form $a_{t-1} + b_t \le 1$ forbids each illegal
pair. Which pairs are forbidden depends on the combination.

## Time parameters

Five integers, computed once in `setup()` from the unit's durations and the timestep, drive the
whole formulation:

| Symbol | Source field | Meaning |
|---|---|---|
| $T^{\text{on}}$ | `minimum_time_on` | Timesteps the unit must stay online once started |
| $T^{\text{off}}$ | `minimum_time_off` | Timesteps the unit must stay offline once stopped |
| $T^{\text{start}}$ | `startup_duration` | Length of the startup ramp |
| $T^{\text{stop}}$ | `shutdown_duration` | Length of the shutdown ramp |
| $T^{\text{stable}}$ | `minimum_stable_power_duration` | Timesteps the unit must hold a constant output once it stops ramping |

Durations that do not fill a whole timestep round away: a 20-minute startup on an hourly
timestep gives $T^{\text{start}} = 0$, and the unit is modelled as having no startup ramp.
A stable duration shorter than one timestep likewise collapses to $T^{\text{stable}} = 0$.

The gradient limit becomes a per-timestep power swing:

$$
\Delta Q = \text{maximum_gradient} \times \Delta t
$$

with `maximum_gradient` in MW per minute. When the unit declares no gradient limit, the
formulation substitutes $\Delta Q^{\text{unc}} = \max_t \overline{P}_t$ — large enough never to
bind, which keeps the constraint structure identical between constrained and unconstrained
units.

## The eight combinations

Three booleans follow from the time parameters: does the unit have a startup ramp
($T^{\text{start}} \ge 1$), a shutdown ramp ($T^{\text{stop}} \ge 1$), a stable phase
($T^{\text{stable}} \ge 1$)? Their eight combinations each produce a different set of variables
and constraints, and `ThermalDispatch` exposes the resulting index as `combination`:

| # | Start | Stop | Flat | Shape |
|:-:|:-:|:-:|:-:|---|
| 1 | — | — | — | Simplest: off / up / down only |
| 2 | — | ✓ | — | Adds the shutdown ramp |
| 3 | — | — | ✓ | Adds the stable phase and gradient tracking |
| 4 | ✓ | — | — | Adds the startup ramp |
| 5 | — | ✓ | ✓ | Shutdown ramp + stable phase |
| 6 | ✓ | — | ✓ | Startup ramp + stable phase |
| 7 | ✓ | ✓ | — | Both ramps, no stable phase |
| 8 | ✓ | ✓ | ✓ | Full formulation |

The combination is not a configuration switch — it is derived from the unit's physical data.
It matters mostly when debugging: two units with the same nameplate can generate very different
constraint sets because one has a 45-minute startup and the other a 20-minute one.

## Power bounds

Between minimum and maximum power *while online*, and pinned toward zero during the ramps:

$$
\underbrace{\underline{P}_t \cdot \sigma_t}_{\text{lower}}
\;\le\; P_t \;\le\;
\underbrace{\overline{P}_t \cdot \sigma_t}_{\text{upper}}
\qquad
\sigma_t = \text{on_up}_t + \text{on_down}_t \;[+\; \text{on_flat}_t]
$$

$\sigma_t$ is 1 exactly when the unit is online and out of its ramps, so the bounds collapse to
$0 \le P_t \le 0$ when it is off, starting or stopping. The ramps then relax that pin: with a
shutdown ramp the upper bound gains $\text{stop}_t \cdot Q^{\min}$, letting the unit sit below
minimum power on its way down, and with a startup ramp it gains
$\text{on_start}_t \cdot Q^{\min}$, where $Q^{\min} = \max_t \underline{P}_t$. Additional
`turned_off` terms step the bound down by $Q^{\min} / T^{\text{stop}}$ per timestep so the
descent is gradual rather than a cliff.

## Gradient constraints

The power swing between two consecutive timesteps is capped in both directions:

$$
P_t - P_{t-1} \;\le\; \text{up_base}_t
\qquad
P_t - P_{t-1} \;\ge\; \text{down_base}_t
$$

The bounds are not constants — they are linear expressions in the state variables, because the
allowed swing depends on what the unit is doing. Ramping up under a gradient limit allows
$\Delta Q$; climbing the startup ramp allows $Q^{\min}/T^{\text{start}}$ per step; a unit with
no gradient limit that has just turned on may jump straight to its bound.

Units with a stable phase need one more layer. Whether a swing is allowed at $t$ depends on
whether the unit was *already* ramping in the same direction at $t-1$, and that product of
binary and continuous terms is not linear. It is linearised with auxiliary variables — `up_grad`
and `down_grad` for the two directions, `aux_up_grad` and `aux_down_grad` as intermediates, and
`dd_grad` for the stable→down→stop chain — each pinned by the standard big-M bracket

$$
v \le M y,\quad v \ge -M y,\quad v \le u + M(1-y),\quad v \ge u - M(1-y)
$$

which forces $v = u \cdot y$ for binary $y$. Big-M is the unit's maximum power, so the bracket
stays tight.

!!! note "Window edges"

    Gradient and `dd_grad` constraints are added through `add_dd_and_gradient_constraints()`,
    which the caller must *not* invoke on the last two timesteps of the window — they reference
    variables past the end. This is the one lifecycle rule the class does not enforce itself.

## Minimum up and down times

Once a unit has started, it must stay online for $T^{\text{on}}$ timesteps. Rather than a
counter, the constraint is written backwards from each timestep: for every
$s \in [1, T^{\text{on}})$,

$$
\text{turned_on}_{t - (s + T^{\text{start}})\Delta t} \;\le\; \text{online}_t
$$

Read it as: *if the unit started recently enough, it must still be online now*. The
$T^{\text{start}}$ offset means the clock starts when the unit reaches minimum power, not when
it begins its startup ramp. Minimum down time mirrors this against `off`, offset by
$T^{\text{stop}}$, and the stable phase gets the same treatment against `on_flat` with
$T^{\text{stable}}$.

**Eviction constraints** close the complementary loophole: a unit cannot be shutting down at $t$
if it turned off less than $T^{\text{stop}}$ steps ago, and cannot be starting if it turned on
less than $T^{\text{start}}$ steps ago. Without them, a unit could re-enter a ramp it has
already completed.

## Daily energy cap

Units declaring `has_daily_energy_constraint` get one constraint per calendar day spanned by the
window:

$$
\sum_{t \in \text{day } d} P_t \;\le\; E^{\max}_d \cdot \Delta t_{\text{days}} \cdot |\text{day } d|
$$

This is added once over the whole window by `add_daily_energy_constraint()`, not per timestep.

## Initial conditions

Constraints at the first timestep reach back before the window — the minimum-time constraints as
far as $\max(T^{\text{on}} + T^{\text{start}},\; T^{\text{off}} + T^{\text{stop}})$ steps. Those
past values are not decisions; they are facts, and they are fixed rather than optimised.

`setup()` reconstructs them from the unit's own `power` forecast:

- **Warm start** — the forecast reaches the timestep just before the window. Each past state is
  inferred from the power level: at or above minimum power the unit was online, strictly between
  zero and minimum it was on a ramp, at zero it was off. Comparing consecutive levels then
  recovers the up/flat/down distinction and the transition indicators.
- **Day zero** — no usable history (`power` is absent, or ends before the window). Everything is
  initialised to *off at zero power*. This is the cold-start case at the beginning of a
  simulation.

!!! warning "Day zero is a modelling choice, not a fallback"

    A unit assumed off before the window cannot be constrained by a minimum up-time it was
    already serving. On a chained simulation this is exactly right for the first module run and
    wrong for every subsequent one — which is why the layer keys the decision on whether the
    power forecast actually reaches the window boundary, rather than on a flag.

## In code

- [`ThermalDispatch`](../../api/optimal-dispatch/thermal.md) — the formulation.
- [`ThermalDispatchInput`](../developer/input-contracts.md#thermal) — the fields it reads.
- [`ThermalReserveHandler`](../reserves/formulation.md#thermal) — the reserve layer built on top of it.
- [Variable naming](../developer/variable-naming.md#thermal) — every emitted name.
