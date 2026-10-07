# OptimisationModel Usage Examples

The `OptimisationModel` provides a unified interface for building and solving optimization problems using OR-Tools. It supports linear programming (LP), mixed-integer programming (MIP), and various solvers.

## Creating an Optimization Model

### Basic Setup

```python
from atlas.solver.solver_interface import OptimisationModel
from atlas.enums import SolverEnum

# Create model with default solver (GLOP for LP)
model = OptimisationModel(
    solver_name=SolverEnum.GLOP,
    name="my_optimization"
)

# Or use SCIP for MIP problems
model = OptimisationModel(
    solver_name=SolverEnum.SCIP,
    name="my_mip_model"
)
```

### With Solver Options

```python
from atlas.solver.models import SolverOptions
from pendulum import duration

# Configure solver options
options = SolverOptions(
    presolve=True,
    duality_gap=0.01,  # 1% gap tolerance
    time_limit='30s'
)

model = OptimisationModel(
    solver_name=SolverEnum.SCIP,
    name="my_model",
    options=options
)
```

## Adding Decision Variables

### Continuous Variables

```python
# Add continuous variable with bounds
x = model.add_continuous_variable(
    name="production",
    lower_bound=0.0,
    upper_bound=100.0
)

# Unbounded variable
y = model.add_continuous_variable(
    name="delta",
    lower_bound=float("-inf"),
    upper_bound=float("inf")
)
```

### Integer Variables

```python
# Add integer variable
num_units = model.add_integer_variable(
    name="num_units",
    lower_bound=0,
    upper_bound=10
)
```

### Boolean Variables

```python
# Add binary decision variable
is_active = model.add_boolean_variable(name="is_active")
```

## Retrieving Variables

```python
# Get variable by name for use in expressions
x = model.get_variable("production")
y = model.get_variable("delta")

# Check all variables in model
all_vars = model.variables  # Returns set of variable names
```

## Adding Constraints

### Using Natural Expressions

```python
# Add linear constraints using expressions
model.add_constraint(x + y <= 50, name="capacity_limit")
model.add_constraint(2 * x + 3 * y >= 20, name="minimum_production")
model.add_constraint(x == 2 * y, name="ratio_constraint")

# Complex constraints
model.add_constraint(
    x + 2 * y + 3 * num_units <= 100,
    name="resource_constraint"
)
```

### Retrieving Constraints

```python
# Get constraint by name
constraint = model.get_constraint("capacity_limit")

# Get constraint bounds
bounds = model.get_constraint_bounds("capacity_limit")
print(f"Lower: {bounds.lower_bound}, Upper: {bounds.upper_bound}")

# Check all constraints
all_constraints = model.constraints  # Returns set of constraint names
```

## Setting the Objective Function

### Set Direction First

```python
# Must set direction before adding objective
model.set_direction("maximize")  # or "minimize"
```

### Set Complete Objective

```python
# Set entire objective at once
model.set_direction("maximize")
model.set_objective(3 * x + 2 * y)
```

### Build Objective Incrementally

```python
# Add objective terms one by one
model.set_direction("minimize")
model.add_objective(x + 2 * y)      # First term
model.add_objective(3 * num_units)  # Adds to existing objective
```

## Solving the Model

### Basic Solve

```python
# Solve and get solution info
solution = model.solve()

print(f"Status: {solution.status}")
print(f"Objective value: {solution.objective_value}")
print(f"Solve time: {solution.solve_time}")
print(f"Iterations: {solution.num_iterations}")
```

### Retrieve Variable Values

```python
# Get optimal values after solving
x_value = model.get_variable_value("production")
y_value = model.get_variable_value("delta")
is_active_value = model.get_variable_value("is_active")

print(f"Production: {x_value}")
print(f"Delta: {y_value}")
print(f"Active: {bool(is_active_value)}")
```

### Check Constraint Slack

```python
# Get slack values for constraints
slack = model.get_constraint_slack_value("capacity_limit")
print(f"Slack for capacity limit: {slack}")
```

## Complete Example: Production Planning

```python
from atlas.solver.solver_interface import OptimisationModel
from atlas.solver.models import SolverOptions
from atlas.enums import SolverEnum, SolverStatus

# Create model
model = OptimisationModel(
    solver_name=SolverEnum.SCIP,
    name="production_planning"
)

# Add variables
product_a = model.add_continuous_variable("product_a", lower_bound=0, upper_bound=100)
product_b = model.add_continuous_variable("product_b", lower_bound=0, upper_bound=80)

# Add constraints
model.add_constraint(product_a + product_b <= 150, name="total_capacity")
model.add_constraint(2 * product_a + product_b <= 200, name="labor_hours")
model.add_constraint(product_a >= 20, name="min_product_a")

# Set objective: maximize profit
model.set_direction("maximize")
model.set_objective(5 * product_a + 3 * product_b)

# Solve
solution = model.solve()

# Check results
if solution.status == SolverStatus.OPTIMAL:
    print("Optimal solution found!")
    print(f"Product A: {model.get_variable_value('product_a'):.2f}")
    print(f"Product B: {model.get_variable_value('product_b'):.2f}")
    print(f"Total profit: {solution.objective_value:.2f}")
elif solution.status == SolverStatus.INFEASIBLE:
    print("No feasible solution exists")
else:
    print(f"Solver status: {solution.status}")
```

## Advanced Features

### Export Model

```python
# Export model to LP format for inspection
model.export_model("model.lp")
```

### Update Solver Options

```python
from pendulum import duration

# Change options after creation
new_options = SolverOptions(
    presolve=False,
    time_limit=duration(hours=1)
)
model.set_solver_options(new_options)
```

### Clear and Rebuild

```python
# Clear all variables, constraints, and objective
model.clear()

# Model is reset and ready for new problem
```

## Accessing Model Properties

```python
# Get solver information
solver_name = model.solver_name  # SolverEnum
model_name = model.name

# Get all variables and constraints
variables = model.variables      # Set of variable names
constraints = model.constraints  # Set of constraint names

# Get last solution info
if model.solution_info:
    status = model.solution_info.status
    obj_value = model.solution_info.objective_value

# Access underlying OR-Tools solver (advanced)
ortools_solver = model.solver
```

## Working with Mixed-Integer Problems

```python
# Create MIP model
model = OptimisationModel(solver_name=SolverEnum.SCIP, name="facility_location")

# Continuous variables for quantities
production = []
for i in range(5):
    var = model.add_continuous_variable(
        name=f"production_{i}",
        lower_bound=0,
        upper_bound=1000
    )
    production.append(var)

# Binary variables for facility opening
facilities = []
for i in range(5):
    var = model.add_boolean_variable(name=f"facility_{i}")
    facilities.append(var)

# Link production to facility opening
for i in range(5):
    model.add_constraint(
        production[i] <= 1000 * facilities[i],
        name=f"link_{i}"
    )

# Budget constraint: can only open 3 facilities
model.add_constraint(sum(facilities) <= 3, name="budget")

# Maximize production
model.set_direction("maximize")
model.set_objective(sum(production))

# Solve
solution = model.solve()
```

## Working with Temporal Variables

Most variables are indexed by time. `add_temporal_variable` declares a `TemporalVariable` that groups them under a single name: each timestamp holds either a solver variable (named `{name}_{t}`) or a fixed value, such as an initial condition before the horizon.

Keep the returned object to build constraints: reading it at a timestamp is a plain dictionary lookup, much cheaper than rebuilding a name and calling `get_variable`.

```python
import pendulum

from atlas.enums import VariableType

start = pendulum.datetime(2025, 1, 1)
timestep = pendulum.duration(hours=1)
time_window = [start + k * timestep for k in range(24)]

model = OptimisationModel(solver_name=SolverEnum.SCIP, name="unit_dispatch")

# Declare the family once over the horizon; bounds can be constants, timeseries or functions of time.
# A timeseries bound is read for the whole window in one lookup: prefer it over max_power.get_value.
power = model.add_temporal_variable("unit_power", time_window, lower_bound=0, upper_bound=max_power)
on = model.add_temporal_variable("unit_on", time_window, VariableType.BOOLEAN)

# Initial condition before the horizon: a fixed value, not a solver variable
power.fix(start - timestep, 50.0)

# Extra timestamps can still be added one by one (add) or in bulk (add_all)
stored = model.add_temporal_variable("unit_stored_energy", lower_bound=0)
stored.add_all([start - timestep, *time_window])

for t in time_window:
    # power[t - timestep] is the fixed value at start, a solver variable afterwards
    model.add_constraint(power[t] - power[t - timestep] <= 10, f"ramp_up_{t}")
    model.add_constraint(power[t] <= max_power.get_value(t) * on[t], f"power_on_{t}")
    model.add_constraint(stored[t] == stored[t - timestep] + power[t], f"energy_balance_{t}")

model.set_direction("maximize")
model.set_objective(sum(power[t] for t in time_window))
model.solve()

# Picklable results, safe to return from a worker process
power.solution()                     # Timeseries over time_window
power.solution(include_fixed=True)   # also includes the initial condition
power.solution_value(start)          # single value
model.solution()                     # {"unit_power": ..., "unit_on": ..., "unit_stored_energy": ...}
```

A timestamp can only be defined once: `add` and `fix` raise a `ValueError` if it already holds a variable or a fixed value, and `power[t]` raises a `KeyError` if it was never defined. A temporal variable name can only be declared once per model. Always create temporal variables through `add_temporal_variable`: only registered ones are part of `model.solution()`. A `TemporalVariable` holds solver objects and refuses to be pickled; return `model.solution()` from worker processes instead.

## Error Handling

```python
# Handle variable/constraint errors
try:
    var = model.get_variable("nonexistent")
except ValueError as e:
    print(f"Variable not found: {e}")

# Handle solution errors
try:
    value = model.get_variable_value("x")
except RuntimeError as e:
    print(f"Model not solved: {e}")

# Handle duplicate names
try:
    x = model.add_continuous_variable("x", 0, 100)
    x2 = model.add_continuous_variable("x", 0, 50)  # Error!
except ValueError as e:
    print(f"Duplicate variable: {e}")
```

For more information, see the [API Reference](../api/solver/interface.md).
