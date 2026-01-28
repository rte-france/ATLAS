# Parameters

## Overview

The Market Clearing module is configured through `MarketClearingParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

## Required Parameters

These parameters are inherited from `AbstractParameters`:

- **`start_date`** (DateTime): Start of the optimization period
- **`end_date`** (DateTime): End of the optimization period
- **`execution_date`** (DateTime): Date when the optimization is executed

# Market Clearing – Parameters

This document describes all configuration parameters available for the **Market Clearing** module. The structure, level of detail, and wording are aligned with the parameter documentation of the **Market Clearing** module to ensure consistency across the project.

---
## Solver Configuration

* **`solver_name`** (`SolverEnum`, default: `XPRESS`): Optimization solver used for the market clearing problem.

  * Options: `"XPRESS"`, `"PNE"`, `"GLOP"`, `"SCIP"`, `"CP-SAT"`, `"CBC"`

* **`use_presolve`** (`bool`, default: `True`): Enable a presolve step before executing all optimization in the market clearing.

  * `True`: Presolve is applied (recommended for performance)
  * `False`: Presolve is skipped

* **`export_lp`** (`bool`, default: `False`): Export solver LP files for debugging and analysis.

---

## Market Definition

* **`market`** (`Product`, default: `DayAhead`): What type of clearing is execute.

  * Only orders matching this market name are considered
  * Not case-sensitive

* **`time_step`** (`Duration`, default: `1 hour`): Time resolution of the studied market.

  * Must be strictly greater than 0

* **`execution_datetime_tolerance`** (`int`, default: `5 minutes`): Tolerance window used to handle overlapping markets (Intraday or Balancing).

  * Must be greater than the execution date difference between consecutive order formulation and clearing

---

## Market Scope

* **`market_area_names`** (`str | list[str]`, default: `"All"`): Market areas included in the Market Clearing.

  * `"All"`: All market areas are included
  * List of strings: Explicit selection (e.g. `["FR", "DE"]`)

* **`control_block_names`** (`str | list[str]`, default: `"All"`): Control blocks included in the Market Clearing.

  * `"All"`: All control blocks are included
  * List of strings: Explicit selection (e.g. `["CB_FR", "CB_DE"]`)

---

## Exchange & Network Constraints

* **`exchange_constraints_type`** (`ExchangeConstraintsType`, default: `ATC`): Type of constraints applied to exchanges between market areas.

  * `ATC`: Available Transfer Capacity
  * `FB`: Flow-Based constraints

* **`prevent_adverse_flows`** (`bool`, default: `False`): Prevent adverse flows during the pricing phase.

  * Not used in Flow-Based configurations

* **`activate_constrained_tso_quantity`** (`bool`, default: `False`): Used in Balancing markets only.

  * Enforces constraint on TSO sold/bought quantities
  * TSO quantities can only be accepted if sufficient opposite offers exist

---

## Objective Function Modifiers

* **`price_modifier_lambda_1`** (`float`, default: `0`): Price modifier allowing artificial price adjustments to improve convergence or stability.

* **`flow_penalty_lambda_2`** (`float`, default: `0`): Penalizes total exchanges through borders in the clearing objective.

* **`flow_penalty_lambda_3`** (`float`, default: `0`): Penalizes non-maximal exchanges through borders.

* **`flow_penalty_lambda_4`** (`float`, default: `0`): Penalizes non-minimal exchanges through borders.

* **`market_price_penalty_alpha`** (`float`, default: `10`): Penalty coefficient favoring the minimization of individual market prices.

* **`market_price_penalty_beta`** (`float`, default: `20`): Penalty coefficient favoring the minimization of absolute market prices.

---

## Constraints

* **`fb_branch_load_slack_penalty`** (`float`, default: `200`): Penalty coefficient encouraging minimization of slack variables on flow-based branch constraints during pricing.

* **`paradoxically_accepted_penalty_M`** (`float`, default: `10000`): Large penalty used to minimize paradoxically accepted bids during price fixing.

* **`paradoxically_rejected_penalty_N`** (`float`, default: `1000`): Large penalty used to minimize paradoxically rejected bids during price fixing.

---

## Numerical Stability

* **`allowed_round_off_error`** (`float`, default: `0.001 MW`): Threshold below which accepted power values are considered equal to zero.

  * Typical values: `0.001`, `0.0001`, `0.00001`

* **`initial_max_price`** (`int`, default: `100000000`): Initial upper bound for market prices.

* **`initial_min_price`** (`int`, default: `-100000000`): Initial lower bound for market prices.

---

## Output Configuration

* **`output_dataset_path`** (`str | None`, default: `None`): Path where the market clearing output dataset is exported.

* **`output_path`** (`str`, default: `""`): Path where the market clearing outputs are exported (csv and lp).

* **`export_csv`** (`boolean`, default: `False`): True if output csv files are exported else False .

  * Includes offers, market areas, order couplings, and market borders
---
## Example Configuration

```yml
time_step: "60m"
start_date:  "2028-09-27 00:00:00"
end_date: "2028-09-28 00:00:00"
execution_date: "2028-09-26 12:00:00"
activate_constrained_tso_quantity: False
prevent_adverse_flows: False
fb_branch_load_slack_penalty: 200
control_block_names: "All"
market_area_names: "All"
exchange_constraints_type: "ATC"
price_modifier_lambda_1: 0
flow_penalty_lambda_2: 0
flow_penalty_lambda_3: 0
flow_penalty_lambda_4: 0
market_price_penalty_alpha: 10
market_price_penalty_beta: 20
paradoxically_accepted_penalty_M: 1_000
paradoxically_rejected_penalty_N: 10_000
solver: "XPRESS"
use_presolve: True
log_level: "DEBUG"
product: "DayAhead"
export_lp: True
export_csv: True
allowed_round_off_error: 1e-3
execution_datetime_tolerance: 5
output_path: ""
```

## Next Steps

- [Running](running.md): How to execute the module
