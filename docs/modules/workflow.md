# Run a Workflow

A workflow chains multiple modules sequentially — each step runs one module, and every step sees the
[Current Input State](orchestrator.md#the-current-input-state) as modified by the steps before it.

A workflow is one of the two [orchestrators](orchestrator.md) provided by Atlas. It runs a **fixed list of steps,
once**. If you need the same modules to run repeatedly over a rolling horizon, use an
[action plan](action-plan.md) instead.

---

## Define a Workflow

A workflow is defined in a YAML (or JSON) file:

```yaml
name: day-ahead
dataset_path: ./data/input/
output_dir: ./results/
steps:
  - module: DayAheadOrders
    parameters: ./parameters/day_ahead_orders.yml
  - module: MarketClearing
    parameters: ./parameters/market_clearing.yml
  - module: PortfolioOptimisation
    parameters: ./parameters/portfolio_optimisation.yml
```

The order in which steps are written in the YAML is important: it defines the actual chain of modules in the
simulation. The `module` field has to correspond to an existing module name (cf. the overview of each individual
module for its name in the [Modules section](index.md)). For the (optional) `name` field, however, the user can
choose whatever is best for clarity purposes.

Two different types of parameters are present in this file:

- **Top-level parameters** either define global information (such as the workflow name), or are applied to *every*
  step in the chain.
- **Step parameters** are applied to a given step.

### Top-level Parameters

Every workflow inherits the [common orchestrator parameters](orchestrator.md#orchestrator-parameters):

| Parameter | Required | Default | Description |
|---|---|---|---|
| `name` | No | `null` | Name of the workflow |
| `dataset_path` | Yes | — | Path to the initial input dataset |
| `output_dir` | No | `.` | Root directory for per-step results and for the final export |
| `path_from_workflow` | No | `false` | Resolve relative paths from `workflow_path` |
| `workflow_path` | No | directory of the workflow file | Absolute root path used when `path_from_workflow` is `true` |
| `rollback_on_job_failure` | No | `true` | Roll back the state to before the failed step |
| `create_job_snapshots` | No | `false` | Save a state snapshot before each step |
| `export_output` | No | `true` | Export the final state to `<output_dir>/workflow_output` |
| `context` | No | `{}` | [Context](context.md) of default and forced values applied to every step |
| `steps` | Yes | — | Ordered list of steps |

!!! note "Parameter aliases"
    `path_from_workflow` and `workflow_path` are aliases of the generic `path_from_orchestrator` and
    `orchestrator_path` fields shared with [action plans](action-plan.md). Either spelling is accepted.

!!! warning "`path_from_workflow` defaults to `false`"
    By default, relative paths are resolved from the **current working directory**, not from the workflow file.
    Set `path_from_workflow: true` to make a workflow folder self-contained and movable.

### Step Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `module` | Yes | — | Module to run: `DayAheadOrders`, `IntradayOrders`, `IntradayPriceForecast`, `MarketClearing`, or `PortfolioOptimisation` |
| `parameters` | Yes | — | Path to the module parameters file, **or** an inline mapping of module parameters |
| `name` | No | module name | Custom name for the step |

`parameters` accepts either form:

```yaml
steps:
  - module: MarketClearing
    parameters: ./parameters/market_clearing.yml   # a path
  - module: DayAheadOrders
    parameters:                                    # or an inline mapping
      temporal:
        start_date: '2028-09-27 00:00:00'
        end_date: '2028-09-28 00:00:00'
        execution_date: '2028-09-26 12:00:00'
```

Inline parameters are convenient for short parameter sets or dynamically generated workflows, avoiding the need
for a separate file per step.

!!! warning "`parameters_path` has been removed"
    Earlier versions accepted a separate `parameters_path` key. A step now carries a single `parameters` field
    that takes a path *or* an inline mapping. A workflow file still using `parameters_path` fails validation with
    a missing-`parameters` error.

!!! note "Duplicate step names"
    If several steps end up with the same name, Atlas appends `_1`, `_2`, … to **every** occurrence, in order:
    two `MarketClearing` steps become `MarketClearing_1` and `MarketClearing_2`. Names that are already unique are
    left untouched. Step names are used as output directory names, so keeping them explicit and unique is worthwhile.

An absolute `parameters` path is checked at validation time and raises immediately if the file does not exist.
Relative paths are only resolved later, when the step is built.

### Applying a Context

The optional `context` block sets values applied to every step's parameters, either as defaults (used only where
the step leaves a value unset) or as forced values (overriding whatever the step declares):

```yaml
name: day-ahead
dataset_path: ./data/input/
context:
  default:
    temporal:
      execution_date: '2028-09-26 12:00:00'
  forced:
    solver:
      solver_name: 'SCIP'
steps:
  - module: MarketClearing
    parameters: ./parameters/market_clearing.yml
```

See [Context](context.md) for the full precedence rules and the important caveat about when a context is applied.

---

## Run

### CLI

```bash
atlas workflow run workflow.yaml
```

To inspect the steps of a workflow file before running it:

```bash
atlas workflow list workflow.yaml
```

See the [CLI reference](../cli.md) for all commands.

### Python

```python
from atlas import Workflow

workflow = Workflow.from_file("workflow.yaml")
cis = workflow.execute()
```

`from_file` also accepts a [context](context.md) that takes priority over the one declared in the file:

```python
from atlas.io_utils.parameters import ContextParameters

workflow = Workflow.from_file(
    "workflow.yaml",
    ContextParameters(forced={"solver": {"solver_name": "SCIP"}}),
)
```

### Programmatic

You can also build a workflow directly in Python, without a YAML file:

```python
from atlas import Workflow, WorkflowParameters
from atlas.orchestrator.workflow.parameters import Step

parameters = WorkflowParameters(
    name="day-ahead",
    dataset_path="./data/input/",
    output_dir="./results/",
    steps=[
        Step(module="DayAheadOrders", parameters={"temporal": {...}}),
        Step(module="MarketClearing", parameters="./parameters/market_clearing.yml"),
        Step(module="PortfolioOptimisation", parameters="./parameters/portfolio_optimisation.yml"),
    ],
)

workflow = Workflow(parameters=parameters)
cis = workflow.execute()
```

This is useful for building workflows dynamically, for example when the list of steps depends on runtime conditions.

!!! note "Where `Step` lives"
    `Step` is defined in `atlas.orchestrator.workflow.parameters`. `Workflow` and `WorkflowParameters` are
    re-exported at the top level of the package and can be imported directly from `atlas`.

Steps can also be appended after construction with `add_step`, which accepts a single `Step` or a list of them:

```python
workflow.add_step(Step(module="PortfolioOptimisation", parameters="./parameters/po.yml"))
```

`add_step` resolves the step's parameters immediately, so it must be called **before** `execute()`.

---

## Accessing Results

`execute()` returns the final [`CurrentInputState`](../api/orchestrator/current_input_state.md) — the input
dataset with every step's changes applied. This is what you want in most cases:

```python
cis = workflow.execute()
dataset = cis.get_data()

for order in dataset.order.all():
    print(f"{order.name}: {order.accepted_power} MW")
```

`get_output_dataset()` returns something different: the **module output object produced by the last executed step**,
which carries that module's own results and its list of [ChangeSets](../api/orchestrator/change_set.md). It returns
`None` if the workflow has not been executed to the end.

```python
last_output = workflow.get_output_dataset()
print(len(last_output.change_sets))
```

!!! warning "Per-step outputs are not retained in memory"
    `workflow.jobs` is a **generator**: each access builds a fresh set of unexecuted jobs. Iterating over it after
    `execute()` therefore yields new objects whose `get_output_dataset()` is `None` — it does not give you the
    results of the run that just happened.

    To keep per-step results, set `output.export_output_dataset: true` in the relevant step's module parameters and
    read the exported dataset from disk (see below), or inspect the state between steps with
    [snapshots](orchestrator.md#snapshots).

---

## Directory Layout

A typical workflow project:

```
my-workflow/
├── workflow.yaml
├── data/
│   └── input/                  # Initial dataset (dataset_path)
├── parameters/
│   ├── day_ahead_orders.yml
│   ├── market_clearing.yml
│   └── portfolio_optimisation.yml
└── results/                    # output_dir
    ├── DayAheadOrders/
    │   └── output_dataset/     # only if that step sets output.export_output_dataset
    ├── MarketClearing/
    ├── PortfolioOptimisation/
    └── workflow_output/        # final state, written when export_output is true
```

Each step's module parameters get their `output.output_dir` rewritten to `<output_dir>/<step name>`, overriding
whatever `output_dir` the module parameters file declares. A step only writes there if its own module parameters
set `output.export_output_dataset: true` (or `export_result`); see
[common module parameters](common-parameters.md#output-output-configuration-optional).

When `path_from_workflow: true`, all relative paths in `workflow.yaml` are resolved from `workflow_path` — which
`Workflow.from_file` sets to the directory containing the workflow file — so you can move the whole folder without
breaking paths. Absolute paths are always used as-is.

---

## Advanced Options

Rollback, snapshots and the final export behave identically for workflows and action plans; they are documented
once in [Orchestrator](orchestrator.md#advanced-options). In short:

| Option | Default | Effect |
|---|---|---|
| `rollback_on_job_failure` | `true` | On failure, restore the containers touched by the failing step |
| `create_job_snapshots` | `false` | Snapshot the state before the workflow and before each step |
| `export_output` | `true` | Write the final state to `<output_dir>/workflow_output` |

With `create_job_snapshots: true`, a workflow creates one snapshot named `Workflow_input` before the first step,
then one named `input_'<step name>'` before each step. Snapshot labels are listed in the logs when a step fails.

---

## See Also

- [Orchestrator](orchestrator.md): the execution model shared by workflows and action plans
- [Context](context.md): defaults and forced values applied to every step
- [Run an Action Plan](action-plan.md): running modules and workflows on a recurring schedule
- [Run a Module](running-modules.md): running a single module
- [Common Parameters](common-parameters.md): parameters shared by all modules
- [CLI reference](../cli.md): full command-line reference
- [Workflow API Reference](../api/workflow/workflow.md): full API documentation
