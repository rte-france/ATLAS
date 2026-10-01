# Reserves

Dispatch decides what a unit produces. **Reserves** decide what it holds back — capacity kept
available so the system operator can correct the imbalance that remains once the market has
cleared and reality has diverged from the schedule.

A unit running flat out has no upward reserve to offer. A unit at minimum has no downward
reserve. Reserve is therefore not a separate market bolted on the side of the dispatch: it
competes with energy for the same megawatts, and the two have to be decided together. That is
why the reserve layer lives inside `atlas/common/optimal_dispatch/` rather than beside it.

## The three pages

<div class="grid cards" markdown>

-   :material-transmission-tower:{ .lg .middle } **Products**

    ---

    What FCR, aFRR, mFRR and RR actually are — what each corrects, how fast, who activates it —
    and why ATLAS groups them into *automated* and *manual*.

    [:octicons-arrow-right-24: Read](products.md)

-   :material-function-variant:{ .lg .middle } **Formulation**

    ---

    The variables and constraints: fill-up, capacity limits, state-of-charge coupling, and the
    slack variables that keep the model solvable.

    [:octicons-arrow-right-24: Read](formulation.md)

-   :material-code-braces:{ .lg .middle } **Developer guide**

    ---

    Handler lifecycle, `ReserveFactory`, reading dispatch state, and adding a handler for a new
    technology.

    [:octicons-arrow-right-24: Read](developer.md)

</div>

## In one table

| | Automated | Manual |
|---|---|---|
| Products | FCR, aFRR | mFRR, RR |
| Activated by | the grid itself, or an automatic TSO signal | a TSO dispatch order |
| Capacity cap | `maximum_fcr + maximum_afrr` | the unit's available power |
| Variables | `automated_reserves_up`, `automated_reserves_down` | `reserves_up`, `reserves_down` |

Both families exist in Day-Ahead Orders **and** in Portfolio Optimisation. They are formulated
differently in places — thermal fill-up is an equality, storage fill-up an inequality — but the
split above is what lets a single set of handlers serve both modules.

## Where reserves touch the rest of ATLAS

- **Equipment** carries the capability caps (`maximum_fcr`, `maximum_afrr`) and, per product,
  the procured, activated and submitted volumes. See the [data model](../../data-model.md).
- **Portfolio** and **ControlBlock** aggregate procurement and needs.
- **Module parameters** set the penalties for unprovided reserve
  (`automated_unprocured_reserves_penalty`, `manual_unprocured_reserves_penalty`) and, for
  storage, how long a reserve must be sustainable (`battery_reserve_duration`,
  `battery_automated_reserve_duration`). See
  [Formulation](formulation.md#capacity-constraints).
