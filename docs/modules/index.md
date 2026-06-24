# Modules

Atlas currently provides four simulation modules for electricity market modeling. Each can be run
independently or chained together in [workflows](workflow.md). All modules share a common
set of [parameters](common-parameters.md) and follow the same [module pattern](module-pattern.md).

# Typical market structures
The usual simulation pattern of a **Day-Ahead market** is the following:

1. [Day-Ahead Orders](day-ahead-orders/index.md)
2. [Market Clearing](market-clearing/index.md)
3. [Portfolio Optimization](portfolio-optimisation/index.md)

**Intraday markets** are meant to be executed after a Day-Ahead market, and involve additional steps:

1. [Intraday Price Forecast](intraday-price-forecast/index.md)
2. [Portfolio Optimization 1](portfolio-optimisation/index.md), in `use_forecast` mode. The aim of this first Portfolio Optimization is to compute updated generation and consumption programs for each unit of the portfolio, at the execution date of the Intraday market. Notably, this optimality may have evolved since the last Day-Ahead market, because of forecast updates.
3. Intraday Orders (still under development), translating updates of step 2 into market orders.
4. [Market Clearing](market-clearing/index.md)
5. [Portfolio Optimization 2](portfolio-optimisation/index.md), to answer intraday market commitments resulting from step 4.


## Available Modules

<div class="grid cards" markdown>

-   :material-chart-line:{ .lg .middle } **Portfolio Optimisation**

    ---

    Optimizes energy asset portfolios (thermal, hydro, storage, renewables) to maximize profits under market conditions.

    [:octicons-arrow-right-24: Overview](portfolio-optimisation/index.md)

    [:octicons-arrow-right-24: User Guide](portfolio-optimisation/user-guide/overview.md)

    [:octicons-arrow-right-24: Architecture](portfolio-optimisation/developer/architecture.md)

-   :material-scale-balance:{ .lg .middle } **Market Clearing**

    ---

    Determines market equilibrium by matching supply and demand across multiple areas while respecting network constraints.

    [:octicons-arrow-right-24: Overview](market-clearing/index.md)

    [:octicons-arrow-right-24: User Guide](market-clearing/user-guide/overview.md)

    [:octicons-arrow-right-24: Architecture](market-clearing/developer/architecture.md)

-   :material-calendar-clock:{ .lg .middle } **Day-Ahead Orders**

    ---

    Generates day-ahead market orders for all equipment types based on asset characteristics and market forecasts.

    [:octicons-arrow-right-24: Overview](day-ahead-orders/index.md)

    [:octicons-arrow-right-24: User Guide](day-ahead-orders/user-guide/overview.md)

    [:octicons-arrow-right-24: Architecture](day-ahead-orders/developer/architecture.md)

-   :material-trending-up:{ .lg .middle } **Intraday Price Forecast**

    ---

    Computes intraday price forecasts using scenario-based sensitivity analysis between day-ahead and intraday markets.

    [:octicons-arrow-right-24: Overview](intraday-price-forecast/index.md)

    [:octicons-arrow-right-24: User Guide](intraday-price-forecast/user-guide/overview.md)

    [:octicons-arrow-right-24: Architecture](intraday-price-forecast/developer/architecture.md)

</div>

## Shared Documentation

Configuration and concepts common to every module:

<div class="grid cards" markdown>

-   :material-tune:{ .lg .middle } **Common Parameters**

    ---

    The `temporal`, `solver`, `output`, and `multiprocessing` sections shared by all modules.

    [:octicons-arrow-right-24: Common parameters](common-parameters.md)

-   :material-play-circle:{ .lg .middle } **Running Modules**

    ---

    Execute a module from Python with `ModuleRun`, or from the command line.

    [:octicons-arrow-right-24: Running modules](running-modules.md)

-   :material-shape-outline:{ .lg .middle } **Module Pattern**

    ---

    The `AbstractModule` lifecycle every module implements: import, validate, execute, export.

    [:octicons-arrow-right-24: Module pattern](module-pattern.md)

-   :material-school:{ .lg .middle } **Your First Simulation**

    ---

    A complete walkthrough running a module end to end on a sample dataset.

    [:octicons-arrow-right-24: First simulation](../getting_started/first-simulation.md)

</div>
