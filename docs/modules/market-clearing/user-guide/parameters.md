# Parameters

The Market Clearing module is configured through `MarketClearingParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

For common parameters (`temporal`, `solver`, `output`), see [Common Parameters](../../common-parameters.md).

---

## Market Definition

| Parameter | Type | Default | Description |
|---|---|---|---|
| `market` | `Product` | `DayAhead` | Type of product that should be cleared. Only orders matching this market name are considered (not case-sensitive). |
| `timestep` | `Duration` | `PT1H` | Time resolution of the studied market. Must be strictly greater than 0. |
| `execution_datetime_tolerance` | `int` | `5 min` | Tolerance window for overlapping markets (notably Intraday or Balancing). Only the orders with an `execution_date` within the range [`clearing_execution_date` - `tolerance`, `clearing_execution_date` + `tolerance`] will be considered. |

## Market Scope

| Parameter | Type | Default | Description |
|---|---|---|---|
| `market_area_names` | `str \| list[str]` | `"All"` | Market areas included in clearing. `"All"` includes everything; pass a list for explicit selection (e.g. `["FR", "DE"]`). |
| `control_block_names` | `str \| list[str]` | `"All"` | Control blocks included in clearing. Same syntax as `market_area_names`. |

## Exchange & Network Constraints

| Parameter | Type | Default | Description |
|---|---|---|---|
| `exchange_constraints_type` | `ExchangeConstraintsType` | `ATC` | `ATC`: Available Transfer Capacity. `FB`: Flow-Based constraints. FB requires additional information on CriticalBranches and PTDFs in the input dataset. |
| `prevent_adverse_flows` | `bool` | `False` | Prevent adverse flows during the pricing phase. Unused in Flow-Based configurations. |
| `activate_constrained_tso_quantity` | `bool` | `False` | Balancing markets only. Enforces that TSO quantities can only be accepted if sufficient opposite offers exist. |

## Objective Function Modifiers

| Parameter | Type | Default | Description |
|---|---|---|---|
| `price_modifier_lambda_1` | `float` | `0` | Artificial price adjustment to improve convergence or stability. |
| `flow_penalty_lambda_2` | `float` | `0` | Penalizes total exchanges through borders. |
| `flow_penalty_lambda_3` | `float` | `0` | Penalizes non-maximal exchanges through borders. |
| `flow_penalty_lambda_4` | `float` | `0` | Penalizes non-minimal exchanges through borders. |
| `market_price_penalty_alpha` | `float` | `10` | Penalty coefficient favouring minimisation of individual market prices. |
| `market_price_penalty_beta` | `float` | `20` | Penalty coefficient favouring minimisation of absolute market prices. |

## Constraints

| Parameter | Type | Default | Description |
|---|---|---|---|
| `fb_branch_load_slack_penalty` | `float` | `200` | Penalty on slack variables for flow-based branch constraints during pricing. |
| `paradoxically_accepted_penalty_M` | `float` | `10 000` | Large penalty to minimise paradoxically accepted bids during price fixing. |
| `paradoxically_rejected_penalty_N` | `float` | `1 000` | Large penalty to minimise paradoxically rejected bids during price fixing. |

## Numerical Stability

| Parameter | Type | Default | Description |
|---|---|---|---|
| `allowed_round_off_error` | `float` | `0.001` MW | Accepted power values below this threshold are treated as zero. Typical values: `0.001`, `0.0001`, `0.00001`. |
| `initial_max_price` | `int` | `100 000 000` | Initial upper bound for market prices. |
| `initial_min_price` | `int` | `-100 000 000` | Initial lower bound for market prices. |

---

## Example Configuration

```yaml
temporal:
  start_date: "2028-09-27 00:00:00"
  end_date: "2028-09-28 00:00:00"
  execution_date: "2028-09-26 12:00:00"
  timestep: "PT1H"
solver:
  solver_name: "SCIP"
  use_presolve: true
  export_lp: true
output:
  export_result: true
  export_output_dataset: true
market: DayAhead
exchange_constraints_type: ATC
market_area_names: "All"
control_block_names: "All"
prevent_adverse_flows: false
activate_constrained_tso_quantity: false
price_modifier_lambda_1: 0
flow_penalty_lambda_2: 0
flow_penalty_lambda_3: 0
flow_penalty_lambda_4: 0
market_price_penalty_alpha: 10
market_price_penalty_beta: 20
fb_branch_load_slack_penalty: 200
paradoxically_accepted_penalty_M: 10000
paradoxically_rejected_penalty_N: 1000
allowed_round_off_error: 1e-3
```

## Next Steps

- [Input Objects](input-objects.md): Required input data and attributes
- [Results](results.md): Understanding outputs
