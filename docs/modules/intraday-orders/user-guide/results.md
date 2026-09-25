# Results

## Overview

`ModuleRun.run()` returns the updated `AtlasDataset`. The generated orders and couplings are applied to it through change sets, and the per-unit submitted volumes are written back onto each equipment.

## Accessing Results

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.intraday_orders.module import IntradayOrdersModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=IntradayOrdersModule(),
    dataset=dataset,
    parameters="parameters.yml",
).run()

# Orders generated for each equipment
for order in result.order:
    print(order.equipment.name, order.order_type, order.qmax, order.price)

# Order couplings (block orders)
for coupling in result.order_coupling:
    print(coupling.coupling_type, [o.name for o in coupling.orders])
```

## Key Outputs

- **Orders**: Intraday buy/sell orders per equipment and timestep (stored in `result.order`).
- **Order couplings**: Linked block orders expressing technical/economical constraints (stored in `result.order_coupling`).
- **Submitted volumes** (written back on each equipment):
    - `id_buy_submitted_volume` / `id_sell_submitted_volume`: volumes submitted in the current intraday session.
    - `total_id_buy_submitted_volume` / `total_id_sell_submitted_volume`: cumulative volumes across all intraday sessions.

## Order Types by Equipment

| Equipment Type | Formulation |
|---|---|
| Thermal | Window-based flex/inflex orders with couplings (Base/Intermediate); per-timestep orders (Peak) |
| Hydro | Price-ordered fragment offers based on water values |
| Storage | Single efficiency-adjusted buy/sell price, per-timestep delta |
| Wind / Solar | Production-delta orders plus curtailment orders |
| Non-dispatchable | Production-delta orders |
| Load | Demand-delta orders (standard); flexible buy/sell (`POWER_TO_GAS`) |

## Troubleshooting

**No orders for an equipment**: Check that the unit has a Day-Ahead cleared quantity (`da_cleared_quantity`) and a target planning forecast at `execution_date`. Price-dependent units (storage, wind, solar, non-dispatchable) also require `market_area.id_price_forecast`.

**Empty order window**: If `start_date` equals `end_date` (a single timestep), the order window is empty and the module returns no orders, logging a warning.

**Zero-volume orders dropped**: Volumes below `allowed_round_off_error` are intentionally not emitted.
