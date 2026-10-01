# Optimal Dispatch

**Optimal dispatch** is the problem of deciding how much power every unit of a fleet produces
or consumes at every timestep of a horizon, subject to the physical limits of each unit.

Two ATLAS modules solve that problem:

- [Day-Ahead Orders](../modules/day-ahead-orders/index.md) dispatches against a *price forecast*
  and turns the result into market orders.
- [Portfolio Optimisation](../modules/portfolio-optimisation/index.md) dispatches against
  *market commitments* and penalises deviation from them.

They ask different questions, but they obey the same physics. A thermal unit has the same
minimum up-time whether you are bidding it into the day-ahead auction or re-optimising it
after clearing. `atlas/common/optimal_dispatch/` is where that shared physics lives.

!!! quote "The guiding principle"

    The common layer does not know **why** you dispatch. It only knows **how** to respect
    the physics.

Concretely, the split is:

| Concern | Owner |
|---|---|
| Decision variables (power, on/off state, stored energy, reserves) | `common/optimal_dispatch/` |
| Physical constraints (ramps, min up/down, SOC evolution, energy balance) | `common/optimal_dispatch/` |
| Objective function (maximise revenue / minimise cost) | the calling module |
| Post-processing (order formulation, imbalance accounting) | the calling module |

There is deliberately no `add_objective()` and no `add_reserves()` on a dispatch class. Modules
compose what they need from the public accessors.

!!! info "Adoption status"

    The common layer is **built but not yet wired in**. `ThermalDispatch`, `StorageDispatch`,
    `HydroDispatch`, `RenewableDispatch`, `LoadDispatch`, the reserve handlers and the
    `*DispatchInput` contracts all exist and are unit-tested, but no module under
    `atlas/modules/` imports them yet — Day-Ahead Orders and Portfolio Optimisation still carry
    their own formulations.

    These pages document the shared layer as the target architecture. When reading a module's
    current source, expect a duplicate of the formulation described here rather than a call into
    it. Migration is tracked in
    [issue #266](https://github.com/rte-france/ATLAS/issues/266).

## The subject

Start here if you want to understand what is being modelled.

<div class="grid cards" markdown>

-   :material-function-variant:{ .lg .middle } **Overview**

    ---

    The dispatch problem: what is decided, over what horizon, and the sign and unit conventions
    that every other page assumes.

    [:octicons-arrow-right-24: Read](concepts/overview.md)

-   :material-fire:{ .lg .middle } **Thermal**

    ---

    The operating-state machine, minimum up and down times, startup and shutdown ramps, and
    gradient limits.

    [:octicons-arrow-right-24: Read](concepts/thermal.md)

-   :material-battery-charging:{ .lg .middle } **Storage**

    ---

    Charge/discharge separation, state-of-charge evolution, cycle balance, and electric-vehicle
    specifics.

    [:octicons-arrow-right-24: Read](concepts/storage.md)

-   :material-water:{ .lg .middle } **Hydro**

    ---

    Reservoir energy balance, piecewise bid fragments, and water values.

    [:octicons-arrow-right-24: Read](concepts/hydro.md)

-   :material-weather-windy:{ .lg .middle } **Renewable & Load**

    ---

    Forecast-driven bounds, curtailment, and the consumption sign convention.

    [:octicons-arrow-right-24: Read](concepts/renewable-load.md)

</div>

## Reserves

Capacity held back rather than produced. It has its own section, because it spans a market
subject, a formulation and a developer interface.

<div class="grid cards" markdown>

-   :material-transmission-tower:{ .lg .middle } **Products**

    ---

    FCR, aFRR, mFRR and RR — what each corrects, how fast, who activates it, and why ATLAS
    groups them into automated and manual.

    [:octicons-arrow-right-24: Read](reserves/products.md)

-   :material-scale-balance:{ .lg .middle } **Formulation**

    ---

    Fill-up, capacity limits, state-of-charge coupling, and the slack variables that keep the
    model solvable.

    [:octicons-arrow-right-24: Read](reserves/formulation.md)

-   :material-code-braces:{ .lg .middle } **Developer guide**

    ---

    Handler lifecycle, `ReserveFactory`, reading dispatch state, adding a handler.

    [:octicons-arrow-right-24: Read](reserves/developer.md)

</div>

## Using the layer

Start here if you are writing or migrating a module.

<div class="grid cards" markdown>

-   :material-file-tree:{ .lg .middle } **Architecture**

    ---

    Package layout, who owns which responsibility, and how a module composes dispatch and
    reserves.

    [:octicons-arrow-right-24: Read](developer/architecture.md)

-   :material-code-braces:{ .lg .middle } **Usage**

    ---

    The `setup → add_variables → add_constraints` lifecycle, with a full worked example.

    [:octicons-arrow-right-24: Read](developer/usage.md)

-   :material-clipboard-check:{ .lg .middle } **Input contracts**

    ---

    The `*DispatchInput` models, the rule that decides what belongs in them, and the renewable
    `Protocol`.

    [:octicons-arrow-right-24: Read](developer/input-contracts.md)

-   :material-tag-text:{ .lg .middle } **Variable naming**

    ---

    Every solver variable and constraint name the layer emits — the page to open when reading an
    LP file.

    [:octicons-arrow-right-24: Read](developer/variable-naming.md)

-   :material-plus-box:{ .lg .middle } **Extending**

    ---

    Adding a technology: dispatch class, input contract, reserve handler, factory method, tests.

    [:octicons-arrow-right-24: Read](developer/extending.md)

</div>
