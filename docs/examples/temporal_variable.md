# Temporal Variables Usage Examples

Most optimisation variables in ATLAS are indexed by time. A `TemporalVariable` groups them under a single name: each timestamp holds either a solver variable (named `{name}_{t}`) or a fixed value, such as an initial condition before the horizon. Indexing returns either one transparently, so constraints can reference `t - timestep` without special-casing the first step.

Temporal variables are always created through an [`OptimisationModel`](optimisation_model.md), which registers them.

## Setup

The examples below share this horizon: 24 hourly timestamps.

```python
import pendulum

from atlas import OptimisationModel, Timeseries
from atlas.enums import SolverEnum, VariableType

start = pendulum.datetime(2025, 1, 1)
timestep = pendulum.duration(hours=1)
horizon = [start + k * timestep for k in range(24)]

model = OptimisationModel(solver_name=SolverEnum.SCIP, name="unit_dispatch")
```

## Declaring Temporal Variables

`add_temporal_variable` creates one solver variable per timestamp given. Bounds can be a constant, a `Timeseries` or a function of time:

```python
# Hourly availability of the unit, as a timeseries
max_power = Timeseries.from_values(
    start_date="2025-01-01 00:00:00",
    frequency="1h",
    values=[100.0] * 12 + [80.0] * 12,
    timezone="UTC",
)

# Timeseries bound: read for the whole horizon in one lookup
power = model.add_temporal_variable("unit_power", horizon, lower_bound=0.0, upper_bound=max_power)

# Boolean variables accept no bounds
on = model.add_temporal_variable("unit_on", horizon, VariableType.BOOLEAN)

# Function of time: e.g. a larger storage limit at night
stored = model.add_temporal_variable(
    "storage_energy",
    horizon,
    lower_bound=0.0,
    upper_bound=lambda t: 200.0 if t.hour < 6 else 150.0,
)
```

A temporal variable declared without timestamps is empty: add them later, one by one with `add` or in bulk with `add_all` (faster, timeseries bounds are read in one lookup):

```python
charge = model.add_temporal_variable("storage_charge", lower_bound=0.0, upper_bound=50.0)
charge.add_all(horizon[:12])
charge.add(horizon[12])
```

## Fixed Values (Initial Conditions)

Timestamps outside the optimisation horizon can hold a fixed value instead of a solver variable:

```python
before = start - timestep

power.fix(before, 50.0)    # one value
stored.fix_all([before], [80.0])  # several values, or a Timeseries read at these timestamps

power.is_fixed(before)     # True
power[before]              # 50.0, a plain float
power.times                # before + horizon
power.model_times          # horizon only
```

## Building Constraints

`power[t]` returns the solver variable at `t`, or the fixed value: the same constraint covers the first timestep and the following ones.

```python
demand = Timeseries.from_values(
    start_date="2025-01-01 00:00:00",
    frequency="1h",
    values=[60.0] * 8 + [90.0] * 8 + [70.0] * 8,
    timezone="UTC",
)
demand_values = demand.get_values(horizon)  # one lookup instead of 24
discharge = model.add_temporal_variable("storage_discharge", horizon, lower_bound=0.0, upper_bound=50.0)
charge.add_all(horizon[13:])

for t, d in zip(horizon, demand_values, strict=True):
    # power[t - timestep] is the fixed value at start, a solver variable afterwards
    model.add_constraint(power[t] - power[t - timestep] <= 30.0, f"ramp_up_{t}")
    model.add_constraint(power[t] <= max_power.get_value(t) * on[t], f"power_on_{t}")
    model.add_constraint(
        stored[t] == stored[t - timestep] + charge[t] - discharge[t], f"storage_balance_{t}"
    )
    model.add_constraint(power[t] + discharge[t] - charge[t] == d, f"supply_demand_{t}")
```

## Sums and Objective

`sum` builds one linear expression, much faster than the builtin `sum` over `power[t]`. Weights take the same forms as bounds:

```python
fuel_cost = Timeseries.from_values(
    start_date="2025-01-01 00:00:00",
    frequency="1h",
    values=[40.0] * 24,
    timezone="UTC",
)

# Daily energy limit of the unit
model.add_constraint(power.sum(horizon) <= 1800.0, "daily_energy")

model.set_direction("minimize")
model.set_objective(power.sum(weights=fuel_cost) + 5.0 * on.sum())
model.solve()
```

## Reading the Solution

```python
power.solution()                       # Timeseries over the solver variables
power.solution(include_fixed=True)     # with the initial condition
power.solution(horizon[:6])            # restricted to a window
power.solution_value(start)            # single value
power.solution_values(horizon[:6])     # plain list, no Timeseries built

# Every registered temporal variable at once: picklable, safe to return from a worker process
results = model.solution()             # {"unit_power": Timeseries, "unit_on": ..., ...}
```

## Tightening Bounds and Solving Again

Retrieve a temporal variable by name with `get_temporal_variable`, then change its bounds with `set_bounds`. Bounds given at declaration still apply to variables added afterwards.

```python
power = model.get_temporal_variable("unit_power")

power.set_bounds(horizon[0], 0.0, 10.0)               # one timestamp
power.set_bounds(horizon[12:], upper_bound=60.0)      # lower bounds kept
power.set_bounds(upper_bound=max_power)               # every solver variable

model.solve()
```

## Errors

```python
# A timestamp can only be defined once
try:
    power.fix(start, 0.0)
except ValueError as e:
    print(e)  # Temporal variable 'unit_power' already holds a solver variable at ...

# Reading a timestamp that was never defined
try:
    power[start + 48 * timestep]
except KeyError as e:
    print(e)

# A name can only be declared once per model
try:
    model.add_temporal_variable("unit_power", horizon)
except ValueError as e:
    print(e)

# Solver objects cannot be pickled: return model.solution() instead
import pickle

try:
    pickle.dumps(power)
except TypeError as e:
    print(e)
```

For more information, see the [TemporalVariable API Reference](../api/solver/temporal_variable.md) and the [OptimisationModel API Reference](../api/solver/interface.md).
