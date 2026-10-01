# Usage

How to build a module step on top of the shared layer.

## The lifecycle

Every dispatch class follows the same four-phase sequence, and the order is not negotiable:

```python
dispatch = ThermalDispatch(equipment)

# 1. Bind and initialise — time parameters, variable handles, initial conditions
dispatch.setup(model, parameters)

# 2. Declare variables for the whole window
for time in time_window:
    dispatch.add_variables(time)

# 3. Add constraints, in a second pass
for time in time_window:
    dispatch.add_constraints(model, time, parameters)

# 4. Horizon-wide constraints
dispatch.add_daily_energy_constraint(model, time_window, parameters.temporal.timestep)
```

**`setup()` first.** It computes the time parameters, creates the
[`ModelVar`](../../api/solver/models.md) handles and fixes the pre-window initial conditions.
Calling `add_variables()` before it raises or, worse, silently builds against uninitialised
state.

**Two separate passes.** A constraint at $t$ routinely references $t - \Delta t$ or
$t - k\,\Delta t$. Interleaving declaration and constraint-building would reference variables
that do not exist yet.

**Horizon-wide constraints last**, once every variable in the window exists.

## Variables vs. constraints

The split between phases 2 and 3 is exactly the split between *what can be decided* and *what
must hold*. Bounds passed to `add_variables()` are enforced by the solver directly; constraints
added in phase 3 are rows in the LP.

Several classes emit bounds in both places. That redundancy is deliberate — see
[LP parity](#lp-parity).

## A worked example: a thermal step

Putting a dispatch, a reserve handler and a module objective together:

```python
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.reserves import ReserveFactory
from atlas.common.optimal_dispatch.steps import AbstractOptimStep


class ThermalStep(AbstractOptimStep[ThermalPO, PortfolioOptimisationParameters]):
    """Dispatch one thermal unit, minimising its variable cost."""

    def __init__(self, equipment: ThermalPO) -> None:
        super().__init__(equipment)
        self._dispatch = ThermalDispatch(equipment)
        self._reserves = ReserveFactory.for_thermal(equipment, self._dispatch)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        self._dispatch.setup(model, parameters)
        self._reserves.setup(model)

        for time in self.equipment.optimisation_time_window:
            self._dispatch.add_variables(time)
            self._reserves.add_variables(
                time,
                max_power=self.equipment.maximum_power.get_value(time),
                min_power=self.equipment.minimum_power.get_value(time),
            )

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        window = self.equipment.optimisation_time_window
        timestep = parameters.temporal.timestep

        for time in window:
            # physics
            self._dispatch.add_constraints(model, time, parameters)

            # gradients reference two steps ahead — skip the tail of the window
            if time not in window[-2:]:
                self._dispatch.add_dd_and_gradient_constraints(model, time, time - timestep)

            # reserves, reading dispatch state
            max_p = self.equipment.maximum_power.get_value(time)
            min_p = self.equipment.minimum_power.get_value(time)
            self._reserves.add_fill_up_constraints(
                time, self._dispatch.power_level_var.get_value(time), max_p, min_p, epsilon=1e-6
            )
            self._reserves.add_capacity_constraints(time, max_p)
            self._reserves.add_relaxed_reserve_constraint(time, min_p)

        self._dispatch.add_daily_energy_constraint(model, window, timestep)

    def add_objective(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        price_forecasts: dict | None = None,
    ) -> None:
        # the module's own concern — the common layer contributes nothing here
        model.set_direction("minimize")
        for time in self.equipment.optimisation_time_window:
            power = self._dispatch.power_level_var.get_value(time)
            model.add_objective(power * self.equipment.variable_cost.get_value(time))
```

Three things to take from it:

1. `setup()` for both dispatch and reserves happens inside `add_variables()`, before the loop.
2. The step never constructs a reserve handler directly — [`ReserveFactory`](../../api/optimal-dispatch/reserves.md)
   computes `maximum_automated` from the equipment's FCR and aFRR capacities.
3. `add_objective()` touches only accessors. Swapping it for the day-ahead version
   (`max Σ price × power`) changes nothing above it.

## Reading results

After the solve, values are read back **by variable name** — which is why the
[naming conventions](variable-naming.md) are part of the public contract rather than an
implementation detail:

```python
power = model.get_variable_value(f"{equipment.name}_power_level_{time}")
is_online = model.get_variable_value(f"off_{equipment.name}_{time}") == 0
```

For reserves, let the handler build the name so you cannot drift from it:

```python
reserved_up = model.get_variable_value(reserves.var("reserves_up", time))
```

A non-zero `unprovided_reserves_*` means the fleet was short of the reserve it committed to —
worth surfacing in the module's output rather than discarding.

## Per-technology notes

| Class | Deviation from the standard lifecycle |
|---|---|
| `ThermalDispatch` | `add_dd_and_gradient_constraints()` is separate and must skip the last two timesteps |
| `StorageDispatch` | `setup()` takes `nb_fragments`; fragment methods are no-ops when it is 0. Call `add_cycle_balance_constraint()` once over the window — but never for an EV unit in a day-ahead context |
| `HydroDispatch` | No `add_constraints()`. Call `add_energy_balance()` at the timesteps where balance applies — the class does not loop |
| `RenewableDispatch` | Requires `_cached_forecast` to be populated before `setup()`; an empty cache means a silently idle unit |
| `LoadDispatch` | Falls back to the forecast matrix when the cache is empty |

## LP parity

Several classes emit constraints that duplicate variable bounds — explicit `power ≤ max_power`
rows for renewables, explicit reserve capacity caps. They are redundant for the solver and
deliberate for the tests: they keep generated LP files comparable with the reference files used
in regression testing, which is how the migration of Day-Ahead Orders and Portfolio Optimisation
will be validated.

The same goes for a handful of odd-looking constraint name suffixes. Removing either will make
tests fail for reasons that have nothing to do with the maths.

## Next

- [Input contracts](input-contracts.md) — what to pass as `equipment`.
- [Variable naming](variable-naming.md) — what the model looks like from the outside.
- [Extending](extending.md) — adding a technology.
