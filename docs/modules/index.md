# Modules

Atlas provides four simulation modules for electricity market modeling. Each can be run independently or chained together in workflows.

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

## Resources

- [Running Modules](running-modules.md) - Execution methods and CLI usage
- [Module Pattern](module-pattern.md) - Standard module structure
- [Common Parameters](common-parameters.md) - Shared parameters
- [Your First Simulation](../getting_started/first-simulation.md) - Complete tutorial
