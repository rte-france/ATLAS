# Parameters

The BSP Balancing Orders module is configured through `BSPBalancingOrdersParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

For common parameters (`temporal`, `export`), see [Common Parameters](../../common-parameters.md).

---

## Market

| Parameter | Type | Default | Description |
|---|---|---|---|
| `product_type` | `MarketType` | `RRActivation` | Balancing product to formulate orders for: `RRActivation` or `MFRRActivation`. Also decides which other procured reserve is removed from the available power (mFRR for RR, RR for mFRR). |
| `market_price_cap` | `float` | `15 000` €/MWh | Symmetric price cap: every order price is clipped to `[-market_price_cap, market_price_cap]`. Also used as the price of "at all costs" orders (wind/solar self-balancing). Usual values: `10 000` for RR, `15 000` for mFRR. |

---

## Scope

| Parameter | Type | Default | Description |
|---|---|---|---|
| `market_area_names` | `str \| list[str]` | `"all"` | Market areas to include. `"all"` keeps every market area; otherwise a list (`[FR, BE]`, as a YAML list or as a string). The equipment of the control blocks of these market areas is kept. |
| `excluded_equipments` | `ExclusionList` | `[]` | Equipment names to exclude, as a list or a semicolon-separated string. `None` and `["none"]` resolve to an empty list. |
| `excluded_technologies` | `ExclusionList` | `[]` | Technology names to exclude (e.g. `thermal`, `hydro`), as a list or a semicolon-separated string. `None` and `["none"]` resolve to an empty list. |

---

## Storage

| Parameter | Type | Default | Description |
|---|---|---|---|
| `conservative_stored_energy` | `bool` | `true` | If `true`, storage units only offer reserves if their stored energy constraints are respected until the next Day-Ahead or Intraday market execution. If `false`, the constraint only covers the balancing time frame. |
| `with_fixed_id_markets` | `bool` | `true` | Whether the simulation includes fixed intraday markets. Sets the horizon of the conservative storage constraint: when `true`, 12:00 the same day if `execution_date` is before 10:00, otherwise the next midnight; when `false`, the next midnight if `execution_date` is before 12:00, otherwise the midnight after. |
| `storage_price_threshold` | `float` | `0.1` | Fraction of the average `maximum_energy` above which the energy already activated for balancing during the day is considered excessive. Beyond it, storage order prices are increased proportionally to the activated energy. Must be ≥ 0. |

---

## Renewables

| Parameter | Type | Default | Description |
|---|---|---|---|
| `res_self_balancing` | `bool` | `false` | Whether wind and solar units follow the self-balancing strategy. When `true`, upward orders are offered, and the excess of forecasted power over `maximum_power_forecast` is offered as a downward order at `market_price_cap`. |

---

## Example Configuration

```yaml
temporal:
  start_date: "2028-09-27 10:00:00"
  end_date: "2028-09-27 11:00:00"
  execution_date: "2028-09-27 09:30:00"
  timestep: "PT15M"
export:
  export_results: true
  export_dataset: true
product_type: RRActivation
market_price_cap: 10000
market_area_names: "[FR, BE]"
excluded_equipments: None
excluded_technologies: None
conservative_stored_energy: true
with_fixed_id_markets: true
storage_price_threshold: 0.1
res_self_balancing: false
```

## Next Steps

- [Input Objects](input-objects.md): Required input data and attributes
- [Results](results.md): Understanding outputs
