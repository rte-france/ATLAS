# Reserve Developer Guide

Working with the reserve handlers: building one, driving its lifecycle, and adding one for a new
technology.

## The handler hierarchy

```
ReserveHandler (ABC)              # naming convention, model binding
├── ThermalReserveHandler         # + relaxed_reserves, dispatch-state coupling, DA forecasts
├── StorageReserveHandler         # + bidirectional down, SOC capacity, inequality fill-up
└── RenewableReserveHandler       # the baseline shape
    └── HydroReserveHandler       # + relaxed_reserves, reservoir-level coupling
```

`HydroReserveHandler` inheriting from `RenewableReserveHandler` is an implementation detail, not
a claim that hydro is renewable: it reuses the standard variable shape and adds the reservoir
specifics on top.

## The factory

Handlers are never constructed directly. [`ReserveFactory`](../../api/optimal-dispatch/reserves.md)
is the single construction point, and it is what computes `maximum_automated` from the
equipment's FCR and aFRR capabilities:

```python
from atlas.common.optimal_dispatch.reserves import ReserveFactory

reserves = ReserveFactory.for_thermal(equipment, dispatch)   # needs the dispatch
reserves = ReserveFactory.for_hydro(equipment, dispatch)     # needs the dispatch
reserves = ReserveFactory.for_storage(equipment)             # standalone
reserves = ReserveFactory.for_renewable(equipment)           # standalone
```

Thermal and hydro take the dispatch because their constraints read its state variables. Storage
and renewable do not need it — the caller passes the variables they need as arguments instead.

Going through the factory is what makes adding a technology additive: a new method plus a new
subclass, with no existing call site touched.

## Lifecycle

```python
# 1. Build, and bind to the solver model
reserves = ReserveFactory.for_thermal(equipment, dispatch)
reserves.setup(model)

# 2. Declare variables over the window
for time in time_window:
    reserves.add_variables(
        time,
        max_power=equipment.maximum_power.get_value(time),
        min_power=equipment.minimum_power.get_value(time),
    )

# 3. Add constraints, in a second pass
for time in time_window:
    reserves.add_fill_up_constraints(time, power_var, max_p, min_p, epsilon=1e-6)
    reserves.add_capacity_constraints(time, max_p)
    reserves.add_relaxed_reserve_constraint(time, min_p)
```

`setup()` binds the model and must come first — every other method routes through
`_require_model()`, which raises a `RuntimeError` with the handler's class name if you skipped it.
That guard exists because the alternative failure mode is an `AttributeError` on `None` several
frames deep.

The two-pass rule is the same as for dispatch: declare everything, then constrain.

## Constraint methods by handler

The handlers do not share a constraint interface — each exposes what its technology needs, and
the calling step knows which to call.

| Method | Thermal | Storage | Hydro | Renewable |
|---|:-:|:-:|:-:|:-:|
| `add_variables(time, max_power, min_power)` | ✓ | ✓ | ✓ | ✓ |
| `add_fill_up_constraints(...)` | ✓ | ✓ | | |
| `add_capacity_constraints(...)` | ✓ | ✓ | ✓ | ✓ |
| `add_automated_capacity_constraints(time)` | | | ✓ | ✓ |
| `add_relaxed_reserve_constraint(time, min_power)` | ✓ | | ✓ | |
| `add_bound_constraints(time, max_power)` | | ✓ | | |
| `add_storage_level_constraints(time, min_e, max_e)` | | | ✓ | |
| `setup_reserve_forecasts(...)` | ✓ | | | |

The signatures differ too — `add_capacity_constraints` takes only `max_power` on thermal, but
the stored-energy variable and both durations on storage. Read the
[API reference](../../api/optimal-dispatch/reserves.md) rather than assuming symmetry.

## Reading dispatch state

`ThermalReserveHandler` and `HydroReserveHandler` hold their dispatch and read its public
accessors:

```python
unavailable = dispatch.off_var.get_value(time)
if dispatch.has_start:
    unavailable = unavailable + dispatch.on_start_var.get_value(time)
if dispatch.has_stop:
    unavailable = unavailable + dispatch.stop_var.get_value(time)
```

Two rules:

- **The dependency runs one way.** A handler may read dispatch state; a dispatch class must never
  know that reserves exist. The moment it does, the physics/objective separation is gone.
- **Guard on the flags, not on the combination.** `has_start`, `has_stop` and `has_flat` say
  which variables exist for that unit. Reading `on_start_var` on a unit with no startup ramp
  fails, and which flags are set depends on the unit's
  [combination](../concepts/thermal.md#the-eight-combinations).

## Naming

Every reserve variable is `{prefix}_{name}_{time}`, built by `var()`:

```python
name = reserves.var("reserves_up", time)          # "reserves_up_myunit_2024-01-01T00:00:00+00:00"
value = model.get_variable_value(name)
```

Always go through `var()` rather than formatting the string yourself — it is the single
definition of the convention, and results are read back by name. See
[Variable naming](../developer/variable-naming.md#reserves).

## Penalising unprovided reserve

The handlers declare the slack variables; **the module decides what they cost**. That term
belongs in the step's `add_objective`, not in the handler:

```python
penalty = parameters.automated_unprocured_reserves_penalty
for time in window:
    model.add_objective(
        penalty * model.get_variable(reserves.var("unprovided_reserves_up", time))
    )
```

Leaving it out makes unprovided reserve free, and the solver will happily commit to reserve it
never intends to supply.

## Day-ahead reserve forecasts

`ThermalReserveHandler` carries one extra piece of state for the day-ahead case:
`setup_reserve_forecasts()` binds the pre-computed procured volumes — manual up and down,
feasible automated up and down (already clipped to what the unit can supply), and the cumulated
infeasible automated volume. Call it after `setup()` and before any contracted-difference
constraint.

## Adding a handler

For a new technology:

1. **Subclass the closest existing handler.** `RenewableReserveHandler` is the baseline shape —
   inheriting from it says nothing about the technology.

   ```python
   class ElectrolyserReserveHandler(RenewableReserveHandler):
       def add_variables(self, time: DateTime, max_power: float, min_power: float) -> None:
           super().add_variables(time, max_power, min_power)
           self._require_model().add_continuous_variable(self.var("my_extra", time), 0, max_power)
   ```

2. **Add a factory method** on `ReserveFactory`, computing `maximum_automated` there. Read
   `maximum_fcr` / `maximum_afrr` directly if every module object for the technology carries them
   (as thermal and storage do), or through `getattr` with a zero default if they may be absent —
   a module that does not model reserves should still be able to build a handler.

3. **Export it** from `reserves/__init__.py`.

4. **Build names through `self.var()`**, never inline.

5. **Test it** under `tests/test_unit/test_common/test_optimal_dispatch/test_reserves/`, asserting
   on the structure of the built model — that the named variables and constraints exist with the
   expected bounds — rather than on solved values.

The broader checklist for a new technology, including the dispatch class and its input contract,
is in [Extending](../developer/extending.md).
