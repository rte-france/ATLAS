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
