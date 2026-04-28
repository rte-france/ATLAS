# Results

## Overview

Results are stored in business model objects after market clearing completes.

## Accessing Results

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.market_clearing import MarketClearingModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=MarketClearingModule(),
    dataset=dataset,
    parameters="parameters.yml",
).run()

# Market clearing prices per market area
for market_area in result.market_areas:
    print(market_area.name, market_area.da_price)

# Accepted quantities per order
for order in result.orders:
    print(order.accepted_quantity)
```

## Key Outputs

- **Market clearing prices**: Price per market area and timestep (stored in `market_area.da_price`)
- **Accepted quantities**: Accepted portion of each order (stored in `order.accepted_quantity`)
- **Cross-border flows**: Power exchanges between market areas (stored in `market_border.exchange`)

## Troubleshooting

**No accepted orders**: Verify that orders exist in the input dataset (run Day-Ahead Orders first).

**Infeasible clearing**: Check that market area capacities and transmission limits are consistent with the order quantities.
