# Results

## Overview

`ModuleRun.run()` returns the updated `AtlasDataset`. The generated orders and couplings are added to it through change sets. The module does not write anything back onto the equipment.

## Accessing Results

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.balancing_market_bsp_orders.module import BSPBalancingOrdersModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=BSPBalancingOrdersModule(),
    dataset=dataset,
    parameters="parameters.yml",
).run()

# Orders generated for each equipment
for order in result.order:
    print(order.equipment.name, order.order_type, order.qmin, order.qmax, order.price)

# Order couplings (thermal only)
for coupling in result.order_coupling:
    print(coupling.coupling_type, [o.name for o in coupling.orders])
```

## Key Outputs

- **Orders**: Balancing buy/sell orders per equipment and timestep (stored in `result.order`).
- **Order couplings**: Links between thermal orders (stored in `result.order_coupling`):
    - `PARENT_CHILDREN`: the indivisible `_start1` order and the divisible `_start2` order of a full startup.
    - `EXCLUSION`: prevents a thermal order from being accepted together with an upward order of the adjacent timestep.

## Order Naming

Orders are named `{equipment}_{market}_{direction}_{start}_{end}_at_{execution}{suffix}`, in lowercase, where:

- `market` is `rr` or `mfrr`;
- `direction` is `u` (upward, Sell), `d` (downward, Buy) or `s` (thermal shutdown);
- `start`, `end` and `execution` are formatted as `HH_MM`;
- `suffix` identifies specific orders: `_selfbal` (wind/solar self-balancing), `_frag_{i}` (hydro fragment `i`), `_start1` / `_start2` (thermal full startup).

Couplings are named `{coupling_type}{n}_{order_name}`, where `n` is a counter per equipment and coupling type.

## Order Types by Equipment

| Equipment Type | Formulation |
|---|---|
| Load | One upward and one downward order per timestep, at the variable cost |
| Wind / Solar | Curtailment (downward) orders; upward and self-balancing orders with `res_self_balancing` |
| Storage | Upward/downward orders bounded by the stored energy horizon, priced from previous clearing prices |
| Hydro | Price-ordered fragment orders based on water values |
| Thermal | Regular, startup (Cases 1/2/3/5) and shutdown orders, with `PARENT_CHILDREN` and `EXCLUSION` couplings |

## Troubleshooting

**No orders for an equipment**: Check that the unit belongs to a selected market area, is not excluded, and has a `power` forecast at `execution_date`. Thermal units in maintenance at any timestep of the time frame are excluded.

**No orders on the first timesteps**: Timesteps starting before `execution_date + setup_delay` are skipped by design.

**Small volumes dropped**: Volumes are rounded to the MW. Most formulators ignore available volumes below 1 MW.

**Storage without orders in one direction**: With `conservative_stored_energy`, a unit whose stored energy already reaches its minimum (or maximum) over the constraint horizon cannot offer upward (or downward) orders.
