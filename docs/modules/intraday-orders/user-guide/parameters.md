# Parameters

The Intraday Orders module is configured through `IntradayOrdersParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

For common parameters (`temporal`, `output`), see [Common Parameters](../../common-parameters.md).

---

## Pricing & Tolerances

| Parameter | Type | Default | Description |
|---|---|---|---|
| `load_price` | `float` | `3 000` €/MWh | Price applied to all standard consumption (load) orders. |
| `large_imbalance_penalty` | `float` | `0.2` | Imbalance-settlement uplift used to price buy-back orders for wind, solar and non-dispatchable units. The buy price is `price_forecast * (1 + large_imbalance_penalty)`, reflecting the cost of being caught short on the balancing market. |
| `hydraulic_minimal_fragment_size` | `float` | `150` MW | Minimum size of a hydro offer fragment. Fragments below this threshold at a given timestep are dropped and their volume is redistributed proportionally over the remaining fragments. |
| `allowed_round_off_error` | `float` | `0.001` MW | Threshold below which an order volume is treated as zero and no order is created. Typical values: `0.001`, `0.0001`, `0.00001`. |

---

## Example Configuration

```yaml
temporal:
  start_date: "2028-09-27 00:00:00"
  end_date: "2028-09-28 00:00:00"
  execution_date: "2028-09-26 22:00:00"
  timestep: "PT1H"
output:
  export_result: true
  export_output_dataset: true
load_price: 3000.0
large_imbalance_penalty: 0.2
hydraulic_minimal_fragment_size: 150.0
allowed_round_off_error: 0.001
```

## Next Steps

- [Input Objects](input-objects.md): Required input data and attributes
- [Results](results.md): Understanding outputs
