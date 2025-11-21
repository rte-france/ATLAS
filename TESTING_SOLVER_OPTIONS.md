# Testing Solver Options - Parameter Passing Verification

This document explains how we verify that solver options are actually passed to the underlying OR-Tools solver.

## Testing Strategy

We use **three levels of testing** to ensure solver options work correctly:

### 1. **Unit Tests** - Test SolverOptions class itself
```python
def test_custom_options(self):
    """Test custom options."""
    options = SolverOptions(presolve=False, duality_gap=0.01, time_limit=60.0)
    assert options.presolve is False
    assert options.duality_gap == 0.01
    assert options.time_limit == 60.0
```

### 2. **Integration Tests** - Test end-to-end with real solver
```python
def test_solve_with_options(self):
    """Test solving with options."""
    options = SolverOptions(presolve=True, duality_gap=0.01, time_limit=60.0)
    model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

    x = model.add_continuous_variable("x", 0, 10)
    model.set_objective(x, direction="maximize")

    solution = model.solve()
    assert solution.status.name == "OPTIMAL"
```

### 3. **Mock Tests** - Verify parameters are passed to solver
This is the **key technique** to verify parameters are actually sent to the solver!

```python
def test_duality_gap_passed_to_solver(self):
    """Test that duality_gap is passed to solver."""
    options = SolverOptions(duality_gap=0.05)
    model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

    # Mock the underlying solver to intercept calls
    mock_solver = MagicMock()
    model._solver = mock_solver

    x = model.add_continuous_variable("x", 0, 10)
    model.set_objective(x, direction="maximize")
    model.solve()

    # Verify SetSolverSpecificParametersAsString was called with duality gap
    mock_solver.SetSolverSpecificParametersAsString.assert_called()
    call_args = mock_solver.SetSolverSpecificParametersAsString.call_args[0][0]
    assert "relative_mip_gap 0.05" in call_args
```

## How Mock Testing Works

### Step 1: Create model with options
```python
options = SolverOptions(presolve=False, duality_gap=0.05, time_limit=30.0)
model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)
```

### Step 2: Replace real solver with mock
```python
from unittest.mock import MagicMock

mock_solver = MagicMock()
model._solver = mock_solver
```

### Step 3: Run solve
```python
x = model.add_continuous_variable("x", 0, 10)
model.set_objective(x, direction="maximize")
model.solve()
```

### Step 4: Verify correct methods were called
```python
# For presolve and duality_gap
mock_solver.SetSolverSpecificParametersAsString.assert_called()
call_args = mock_solver.SetSolverSpecificParametersAsString.call_args[0][0]
assert "presolve off" in call_args
assert "relative_mip_gap 0.05" in call_args

# For time_limit
mock_solver.SetTimeLimit.assert_called_once_with(30000)  # 30 seconds = 30000 ms
```

## What We Verify

### ✅ Presolve Parameter
```python
# When presolve=False
assert "presolve off" in parameters_string
```

### ✅ Duality Gap Parameter
```python
# When duality_gap=0.05
assert "relative_mip_gap 0.05" in parameters_string
```

### ✅ Time Limit Parameter
```python
# When time_limit=30.0 seconds
mock_solver.SetTimeLimit.assert_called_once_with(30000)  # milliseconds
```

### ✅ Multiple Options Together
```python
# Verify all three parameters are set correctly
assert "presolve off" in parameters_string
assert "relative_mip_gap 0.02" in parameters_string
mock_solver.SetTimeLimit.assert_called_once_with(60000)
```

### ✅ Default Options Don't Set Unnecessary Parameters
```python
# With default options, no parameters should be set
mock_solver.SetSolverSpecificParametersAsString.assert_not_called()
mock_solver.SetTimeLimit.assert_not_called()
```

## Test Coverage

| Test | Purpose |
|------|---------|
| `test_presolve_disabled_passed_to_solver` | Verify presolve=False is sent |
| `test_duality_gap_passed_to_solver` | Verify duality_gap is sent |
| `test_time_limit_passed_to_solver` | Verify time_limit is sent (converted to ms) |
| `test_all_options_passed_to_solver` | Verify all options work together |
| `test_default_options_no_parameters_set` | Verify defaults don't set params |

## Running the Tests

```bash
# Run all solver options tests
uv run pytest tests/test_unit/test_solver/test_solver_options.py -v

# Run only parameter passing tests
uv run pytest tests/test_unit/test_solver/test_solver_options.py::TestSolverOptionsParameterPassing -v
```

## Example Output

```
tests/test_unit/test_solver/test_solver_options.py::TestSolverOptionsParameterPassing::test_presolve_disabled_passed_to_solver PASSED
tests/test_unit/test_solver/test_solver_options.py::TestSolverOptionsParameterPassing::test_duality_gap_passed_to_solver PASSED
tests/test_unit/test_solver/test_solver_options.py::TestSolverOptionsParameterPassing::test_time_limit_passed_to_solver PASSED
tests/test_unit/test_solver/test_solver_options.py::TestSolverOptionsParameterPassing::test_all_options_passed_to_solver PASSED
tests/test_unit/test_solver/test_solver_options.py::TestSolverOptionsParameterPassing::test_default_options_no_parameters_set PASSED
```

## Key Techniques

### 1. **MagicMock** - Record all method calls
```python
mock_solver = MagicMock()
```

### 2. **assert_called()** - Verify method was called
```python
mock_solver.SetSolverSpecificParametersAsString.assert_called()
```

### 3. **assert_called_once_with()** - Verify exact arguments
```python
mock_solver.SetTimeLimit.assert_called_once_with(30000)
```

### 4. **call_args** - Inspect actual arguments passed
```python
call_args = mock_solver.SetSolverSpecificParametersAsString.call_args[0][0]
assert "relative_mip_gap 0.05" in call_args
```

### 5. **assert_not_called()** - Verify method was NOT called
```python
mock_solver.SetTimeLimit.assert_not_called()
```

## Benefits

1. **Confidence**: We know parameters actually reach the solver
2. **Fast**: Mock tests run instantly (no actual solving)
3. **Precise**: We can verify exact parameter values
4. **Regression prevention**: Tests fail if parameter passing breaks
5. **Documentation**: Tests show how parameters are formatted

## Implementation Details

The actual parameter passing happens in [solver_interface.py](atlas/solver/solver_interface.py):

```python
def _apply_solver_options(self) -> None:
    """Apply solver options to the underlying solver."""
    params = []

    if not self._options.presolve:
        params.append("presolve off")

    if self._options.duality_gap is not None:
        params.append(f"relative_mip_gap {self._options.duality_gap}")

    if params:
        self._solver.SetSolverSpecificParametersAsString(" ".join(params))

    if self._options.time_limit is not None:
        self._solver.SetTimeLimit(int(self._options.time_limit * 1000))
```

Our tests verify each part of this implementation!
