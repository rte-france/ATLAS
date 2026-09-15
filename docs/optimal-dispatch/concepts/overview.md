# The Dispatch Problem

This page fixes the vocabulary, the conventions and the general shape of the problem. Every
other concept page assumes it.

## What is decided

A dispatch problem is posed over a **time window** — an ordered list of timesteps
$\mathcal{T} = \{t_1, \dots, t_N\}$ of constant duration $\Delta t$, derived from
`parameters.temporal` (`start_date`, `end_date`, `timestep`).

For each unit and each $t \in \mathcal{T}$, the solver decides a **power level** $P_t$. Depending
on the technology, that headline decision drags in companions:

| Technology | Decisions per timestep |
|---|---|
| Thermal | power level, plus a set of binary operating-state variables |
| Storage | discharge power, charge power, a discharge/charge binary, stored energy |
| Hydro | one power variable per bid fragment, plus reservoir stored energy |
| Renewable | power level, bounded by forecast and curtailment |
| Load | power level (negative), bounded by forecast |

When reserves are modelled, each unit additionally decides how much **capacity it holds back**
for upward and downward reserve — see [Reserves](../reserves/index.md).

The result is a mixed-integer linear program: continuous power and energy variables, binary
state variables, linear constraints. ATLAS builds it through
[`OptimisationModel`](../../api/solver/interface.md) and hands it to OR-Tools.

## Conventions

These hold throughout the layer, and violating them silently produces a wrong model rather than
an error.

**Sign.** Power is positive when injected into the grid and negative when withdrawn from it.
So a load's power variable is bounded by $[\,\overline{P}_t,\, 0\,]$ with $\overline{P}_t \le 0$,
and a storage unit's *buy* variable is bounded above by zero. A consequence worth internalising:
storage charging energy is written $-P^{\text{buy}}_t$, and reading that minus sign as an error
is a common first mistake.

**Units.** Power in MW, energy in MWh, durations as `pendulum` objects. Converting between the
two always goes through the timestep: $E = P \cdot \Delta t$, with $\Delta t$ expressed in hours
(`timestep.total_hours()`). A handful of series are daily rather than per-timestep — hydro
inflows, thermal daily energy caps — and those convert with `timestep.total_days()` instead.


## The general shape

Ignoring technology specifics, every module builds the same skeleton:

$$
\begin{aligned}
\min_{P,\,x} \quad & f(P) && \text{(module-specific objective)} \\
\text{s.t.} \quad & \underline{P}_t \cdot x_t \le P_t \le \overline{P}_t \cdot x_t
  && \forall t \in \mathcal{T} \\
& g(P_t, P_{t-1}, x_t, x_{t-1}) \le 0 && \forall t \in \mathcal{T} \\
& h(P_{t_1}, \dots, P_{t_N}) \le 0 &&
\end{aligned}
$$

where $x_t$ collects the binary state variables, $g$ the inter-temporal coupling (ramps, state
transitions, stored-energy evolution) and $h$ the horizon-wide constraints (cycle balance, daily
energy caps).

The common layer owns the constraints. The objective $f$ stays with the module:

- **Day-Ahead Orders** maximises $\sum_t \pi_t \cdot P_t$ against a price forecast $\pi$.
- **Portfolio Optimisation** minimises $\sum_t c_t \cdot P_t$ plus imbalance penalties, under a
  portfolio balance constraint tying each unit's power to the portfolio's market commitment.

That is the whole reason the split exists: the two modules disagree on $f$ and agree on
everything else.


## Next

- [Thermal](thermal.md) — the richest formulation, and the one worth reading first.
- [Storage](storage.md), [Hydro](hydro.md), [Renewable & Load](renewable-load.md).
- [Reserves](../reserves/index.md) — the capacity layer on top of all of them.
