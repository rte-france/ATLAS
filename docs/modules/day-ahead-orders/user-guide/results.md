# Results

## Overview

Results are stored in business model objects after order formulation completes.

## Accessing Results

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.day_ahead_orders import DayAheadOrdersModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=DayAheadOrdersModule(),
    dataset=dataset,
    parameters="parameters.yml",
).run()

# Orders generated for each equipment
for order in result.orders:
    print(order.equipment_name, order.quantity, order.price)

# Order couplings (block orders)
for coupling in result.order_couplings:
    print(coupling)
```

## Key Outputs

- **Orders**: Market orders per equipment and timestep (stored in `result.orders`)
- **Order couplings**: Linked block orders (stored in `result.order_couplings`)

## Order Types by Equipment

| Equipment Type | Order Type |
|---------------|------------|
| Thermal | Thermal orders with cost curves |
| Hydro | Hydraulic orders with reservoir constraints |
| Storage (Battery, EV, PHS) | Storage orders with charge/discharge profiles |
| Wind / Solar | Non-dispatchable orders based on forecasts |
| Load | Load orders based on demand forecasts |

## Troubleshooting

**Missing orders for equipment**: Check that the equipment has valid forecast data at `execution_date`.

**Zero-quantity orders**: Verify that power forecast values are non-zero and within installed capacity bounds.
