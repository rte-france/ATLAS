# Atlas Data Model

The Atlas data model is built around a set of interconnected **business objects** that represent the physical and market entities of an electricity system. All objects extend `BusinessModel` and are identified by a unique `name` field.

## Object Hierarchy

Objects depend on each other through typed reference fields. The diagram below shows who depends on whom — an arrow means "holds a reference to":

```
ControlBlock
    ├── MarketArea         (ControlBlock)
    │   ├── Node           (ControlBlock + MarketArea)
    │   │   └── Equipment  (Node + Portfolio)
    │   │       ├── Thermal
    │   │       ├── Hydro
    │   │       ├── Solar
    │   │       ├── Wind
    │   │       ├── Storage
    │   │       ├── Load
    │   │       └── OtherNonDispatchable
    │   └── MarketBorder   (2× ControlBlock + 2× MarketArea)
    └── Portfolio          (ControlBlock + MarketArea)
```

**Loading order**: when building a dataset from scratch, always create objects in dependency order — `ControlBlock` first, then `MarketArea`, then `Node` and `Portfolio`, then equipment types.

---

## Objects

<div class="grid cards" markdown>

-   **ControlBlock**

    ---

    Top-level operator entity representing a Transmission System Operator (TSO) control zone. Holds balancing needs, reserve procurement requirements, and imbalance settlement prices.

    No dependency on other Atlas objects.

    [:octicons-arrow-right-24: API Reference](api/models/network_operator/control_block.md)

-   **MarketArea**

    ---

    A bidding zone in the electricity market (e.g. FR, DE). Holds price forecasts, day-ahead and intraday prices, and balance positions.

    **Depends on**: `ControlBlock`

    [:octicons-arrow-right-24: API Reference](api/models/market/market_area.md)

-   **Node**

    ---

    A physical network node within a market area. Stores nodal injection data and balance forecasts.

    **Depends on**: `ControlBlock`, `MarketArea`

    [:octicons-arrow-right-24: API Reference](api/models/network/node.md)

-   **Portfolio**

    ---

    A market operator's portfolio grouping a set of equipment units. Aggregates power, cleared quantities, and imbalance across all assets.

    **Depends on**: `ControlBlock`, `MarketArea`

    [:octicons-arrow-right-24: API Reference](api/models/market_operator/portfolio.md)

-   **MarketBorder**

    ---

    A cross-border interconnection between two market areas. Holds flow limits, actual flows, and shadow prices for day-ahead and intraday markets.

    **Depends on**: `ControlBlock` (×2), `MarketArea` (×2)

    [:octicons-arrow-right-24: API Reference](api/models/market/market_border.md)

-   **Equipment** (base)

    ---

    Base class for all generation and consumption assets. Holds reserve volumes, production schedules, and CO₂ emissions. Never instantiated directly — use a concrete subclass.

    **Depends on**: `Node`, `Portfolio`

    [:octicons-arrow-right-24: API Reference](api/models/equipment/equipment.md)

-   **Thermal**

    ---

    Thermal generation unit or cluster (nuclear, gas, coal…). Adds dispatch constraints: minimum time on/off, start-up duration, ramp rates, and outage probabilities.

    **Extends**: `Equipment`

    [:octicons-arrow-right-24: API Reference](api/models/equipment/thermal.md)

-   **Hydro**

    ---

    Hydroelectric plant with reservoir. Adds inflows, energy storage levels, and fragment-based water value representation.

    **Extends**: `Equipment`

    [:octicons-arrow-right-24: API Reference](api/models/equipment/hydro.md)

-   **Solar**

    ---

    Solar photovoltaic unit. Typically driven by an availability timeseries representing irradiance-based generation profiles.

    **Extends**: `Equipment`

    [:octicons-arrow-right-24: API Reference](api/models/equipment/solar.md)

-   **Wind**

    ---

    Wind power unit (on- or offshore). Driven by availability and capacity timeseries from wind forecasts.

    **Extends**: `Equipment`

    [:octicons-arrow-right-24: API Reference](api/models/equipment/wind.md)

-   **Storage**

    ---

    Battery or pumped-storage unit. Adds charge/discharge efficiency, capacity, and state-of-charge constraints.

    **Extends**: `Equipment`

    [:octicons-arrow-right-24: API Reference](api/models/equipment/storage.md)

-   **Load**

    ---

    Consumption unit. Represents demand that must be served by the system, with flexibility for demand-response modeling.

    **Extends**: `Equipment`

    [:octicons-arrow-right-24: API Reference](api/models/equipment/load.md)

-   **OtherNonDispatchable**

    ---

    Catch-all for non-dispatchable assets that don't fit the other categories (run-of-river, must-run contracts…).

    **Extends**: `Equipment`

    [:octicons-arrow-right-24: API Reference](api/models/equipment/other_non_dispatchable.md)

</div>

---

## Time-Varying Data

Each business object can carry three types of time-varying data alongside its scalar fields:

| Type | Class | Use case |
|---|---|---|
| Deterministic series | `Timeseries` / `LazyTimeseries` | Single realization over time (prices, availability) |
| Stochastic scenarios | `ScenarioMatrix` / `LazyScenarioMatrix` | Multiple parallel scenarios (hydro inflows) |
| Forecast horizons | `ForecastingMatrix` / `LazyForecastingMatrix` | Data indexed by both time and forecast horizon (price forecasts, production plans) |

Lazy variants defer file loading until the data is first accessed — use them for large datasets.

See the [Examples](examples/timeseries.md) section for usage patterns.

---

## Dataset Container

All business objects are stored together in an [`AtlasDataset`](api/io/atlas_dataset.md), which provides typed accessors and handles serialization to/from disk.

```python
from atlas import AtlasDataset

dataset = AtlasDataset.from_directory("my-dataset/")

# Typed access
thermals = dataset.thermal.all()
fr_area  = dataset.market_area.get("fr")

# Cross-type iteration
for unit in dataset.iter_by_types("thermal", "hydro"):
    print(unit.name, unit.node.name)
```

See the [AtlasDataset examples](examples/atlas_dataset.md) for a complete guide including how to add, update, and remove objects.
