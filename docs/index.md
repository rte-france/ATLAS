---
hide:
    - navigation
    - toc
---

<h1 class="sr-only">ATLAS</h1>

<div class="hero-banner" markdown>

<p class="hero-title"><span class="atlas-accent">A</span>TLAS</p>

<p class="hero-tagline">Power market simulator for day-ahead, intraday, and reserve markets.</p>

<p class="hero-subtitle">Developed by <strong>Artelys</strong> for <strong>RTE</strong></p>

<div class="hero-badges">
  <a href="https://github.com/rte-france/ATLAS/actions/workflows/test.yml" target="_blank" rel="noopener noreferrer">
    <img src="https://github.com/rte-france/ATLAS/actions/workflows/test.yml/badge.svg" alt="Tests">
  </a>
  <a href="https://github.com/rte-france/ATLAS/actions/workflows/lint.yml" target="_blank" rel="noopener noreferrer">
    <img src="https://github.com/rte-france/ATLAS/actions/workflows/lint.yml/badge.svg" alt="Lint">
  </a>
  <img src="https://img.shields.io/badge/Python-3.13+-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/license-MPL--2.0-1b3d70?style=flat-square" alt="License MPL-2.0">
</div>

</div>

<p class="hero-description" markdown>
ATLAS is an agent-based simulator for electricity markets, covering day-ahead, intraday, and balancing markets. It models the sequential decisions of market participants — from order formulation to market clearing and portfolio optimisation — through independent modules chained into configurable workflows.
</p>

<div class="grid cards" markdown>

-   [:lucide-rocket:{ .lg .middle } **Quick Start**](getting_started/getting_started.md)

    ---

    Install ATLAS and run your first electricity market simulation in minutes.

    [:octicons-arrow-right-24: Installation](getting_started/getting_started.md)
    · [:octicons-arrow-right-24: Quickstart](getting_started/quickstart.md)

-   [:lucide-blocks:{ .lg .middle } **Market Modules**](modules/index.md)

    ---

    Explore the simulation modules — each implements an independent market mechanism chainable into workflows.

    [:octicons-arrow-right-24: Browse modules](modules/index.md)

-   [:lucide-database:{ .lg .middle } **Data Model**](data-model.md)

    ---

    Understand how market areas, equipment, orders, and portfolios are represented across the simulation.

    [:octicons-arrow-right-24: Data model](data-model.md)

-   [:lucide-file-input:{ .lg .middle } **Antares Integration**](antares-integration/index.md)

    ---

    Convert an Antares study into an Atlas-ready dataset with a single command.

    [:octicons-arrow-right-24: Overview](antares-integration/index.md)
    · [:octicons-arrow-right-24: User guide](antares-integration/user-guide.md)

-   [:lucide-flask-conical:{ .lg .middle } **Examples**](examples/atlas_dataset.md)

    ---

    Hands-on examples for datasets, timeseries, matrices, and optimisation models.

    [:octicons-arrow-right-24: Browse examples](examples/atlas_dataset.md)

</div>
