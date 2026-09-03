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

- **Market clearing prices**: Price per market area and timestep (stored in `market_area.da_price` when `market` == "DayAhead", for instance)
- **Accepted quantities**: Accepted portion of each order (stored in `order.accepted_quantity`)
- **Cross-border flows**: Power exchanges between market areas (stored in `market_border.exchange`)

## Troubleshooting

**No accepted orders**:

- Verify that orders exist in the input dataset (run Day-Ahead Orders first).
- Check that the temporal parameters are correct (`start_date`, `end_date` and `execution_date`)
- Check the parameters `market_area_names` and `control_block_names`, to ensure that there is no error on filters applied to areas.

**Infeasible clearing**:

- Look for errors in market order characteristics (i.e. `qmin` > `qmax`, or `qmax` = 0).
- Look for coupling links that may be infeasible.

**Prices at the upper price cap (3000€/MWh for instance)**:

- This may indicate that input power system is not correctly designed, with a lack of generation / excess of consumption.
- Check transmission line (or critical branches) capacities to see whether exchanges between areas are possible or not.
