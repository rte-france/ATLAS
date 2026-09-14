# Storage

A storage unit is an energy accumulator: it withdraws power from the grid to fill up, injects
power to empty out, and loses a fraction of the energy in each direction. `StorageDispatch`
tracks its state of charge and forbids it from doing both at once.

The same class covers batteries, pumped hydro and electric-vehicle fleets — the last of those
with a few specifics, flagged below.

## Decisions

Four variables per timestep:

| Variable | Range | Meaning |
|---|---|---|
| $P^{\text{sell}}_t$ | $[0,\ \overline{P}_t]$ | Discharge power, injected into the grid |
| $P^{\text{buy}}_t$ | $[\underline{P}_t,\ 0]$ | Charge power, withdrawn from the grid (**negative**) |
| $s_t$ | binary | 1 when discharging, 0 when charging |
| $E_t$ | $[\text{SOC}^{\min}_t \cdot \overline{E}_t,\ \overline{E}_t]$ | Stored energy at the end of the timestep |

The sign convention from the [overview](overview.md#conventions) is doing real work here:
$P^{\text{buy}}_t$ is negative, so energy entering the unit is written $-P^{\text{buy}}_t$.

## State of charge

The central constraint. Stored energy carries over, gains what was charged, loses what was
discharged:

$$
E_t = E_{t-1} \cdot \rho_t
\;+\; \underbrace{\left(-P^{\text{buy}}_t\right) \cdot \eta^{\text{c}} \cdot \Delta t}_{\text{charged}}
\;-\; \underbrace{\frac{P^{\text{sell}}_t \cdot \Delta t}{\eta^{\text{d}}}}_{\text{discharged}}
\;-\; \Delta D_t
$$

Four things to note:

- **Efficiencies bite in opposite directions.** Charging *multiplies* by $\eta^{\text{c}}$
  (part of what you draw never reaches the store); discharging *divides* by $\eta^{\text{d}}$
  (you must drain more than you deliver). Both are constrained strictly positive in the input
  contract, because the formulation divides by one of them.
- **$\rho_t = \overline{E}_t / \overline{E}_{t-1}$** rescales the carried-over energy when the
  unit's capacity varies over time — the case that matters for an EV fleet whose size changes
  hour to hour. It is 1 for a fixed-capacity battery.
- **$\Delta D_t$** is the change in `displacement_energy`: energy that left the unit without
  passing through the grid. For an EV fleet, this is the energy consumed by driving.
- **At the first timestep**, $E_{t-1}$ is replaced by the initial stock — read from the unit's
  `stored_energy` forecast when available, otherwise `storage_initial_level` × maximum energy.

## No simultaneous charge and discharge

Nothing in the SOC equation stops a unit from charging and discharging at once to burn energy
through the efficiency losses. The binary $s_t$ forbids it:

$$
P^{\text{sell}}_t \le \overline{P}^{\text{sell}}_t \cdot s_t
\qquad
P^{\text{buy}}_t \ge \underline{P}^{\text{buy}}_t \cdot (1 - s_t)
$$

When $s_t = 1$ the charge variable is pinned to zero, and vice versa.

!!! note "Electric vehicles are exempt"

    `add_constraints()` skips this pair for `StorageType.ELECTRIC_VEHICLE`. The two modules
    govern an EV's charge/discharge split differently — the day-ahead fill-up and the
    portfolio-optimisation reserve fill-up each impose their own version — so the common layer
    leaves it to the caller rather than picking one. Adding the generic separation on top of
    either would over-constrain the unit.

## Cycle balance

Over the whole horizon, what goes in must come out:

$$
\sum_{t} \left(-P^{\text{buy}}_t\right) \eta^{\text{c}} \Delta t
\;=\;
\sum_{t} \frac{P^{\text{sell}}_t \Delta t}{\eta^{\text{d}}}
\;-\; \Delta D
$$

This leaves the unit at the same state of charge it started from, so a simulation does not
quietly finance itself by emptying its reservoirs. $\Delta D$ is the displacement accumulated
over the window — the telescoped sum of the per-timestep terms in the SOC equation. Dropping it
contradicts the level evolution and makes the model infeasible as soon as a vehicle drives.

!!! warning "Not for EVs in a day-ahead context"

    Day-Ahead Orders does not apply cycle balance to electric vehicles. It bounds purchases from
    below instead — enough to pay back the driving, but free to end the horizon above or below
    the starting charge. That is a strictly *weaker* constraint, not a variant of this one, so
    `add_cycle_balance_constraint()` must not be called for EV units in that context.

## Electric-vehicle specifics

Three things differ from a stationary battery:

- **V2G gating.** An EV can only discharge to the grid if it is vehicle-to-grid capable. The
  effective discharge ceiling is $\text{is\_v2g} \times \overline{P}_t$, which is zero for a
  fleet that only charges.
- **Displacement energy** leaves the battery through the wheels, as described above.
- **Charge/discharge separation** is left to the caller.

## Bid fragments

A unit bidding into a market rarely offers its whole capacity at one price. `StorageDispatch`
can split each of $P^{\text{sell}}_t$ and $P^{\text{buy}}_t$ into $n$ equal-width **fragments**,
each of which the module can price independently:

$$
P^{\text{sell}}_t = \sum_{i=1}^{n} P^{\text{sell},i}_t
\qquad
P^{\text{buy}}_t = \sum_{i=1}^{n} P^{\text{buy},i}_t
$$

with each fragment bounded by $\overline{P}_t / n$ (or $\underline{P}_t / n$ for buy). This is
the piecewise-linear approximation of a bid curve. Fragments are opt-in: pass `nb_fragments` to
`setup()`, and the fragment methods become no-ops when it is zero.

## In code

- [`StorageDispatch`](../../api/optimal-dispatch/storage.md) — the formulation.
- [`StorageDispatchInput`](../developer/input-contracts.md#storage) — the fields it reads.
- [`StorageReserveHandler`](../reserves/formulation.md#storage) — reserve capacity against state of charge.
- [Variable naming](../developer/variable-naming.md#storage) — every emitted name.
