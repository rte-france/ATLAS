# Extending

Adding a technology to the layer touches five places. None of them requires modifying existing
code — that is the point of the factory.

Worked through here for a fictional `Electrolyser`.

## 1. The input contract

`atlas/common/optimal_dispatch/input_objects/electrolyser.py` — declare exactly the fields the
formulation will read, and nothing more:

```python
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.electrolyser import Electrolyser
from atlas.validators import DurationField


class ElectrolyserDispatchInput(Electrolyser):
    """Physical contract for electrolyser dispatch — fields read by :class:`ElectrolyserDispatch`."""

    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    minimum_time_on: DurationField
```

Inherit from the core object in `atlas/objects/`, type timeseries as `AbstractTimeseries` so
lazy and eager variants both work, and tighten any validation the formulation depends on (a
divisor that must be non-zero, for instance) here rather than on the base class.

If the technology has no single base class to inherit from — as with wind and solar — use a
`runtime_checkable` `Protocol` instead. See
[Input contracts](input-contracts.md#renewable).

## 2. The dispatch class

`atlas/common/optimal_dispatch/dispatch/electrolyser.py`:

```python
class ElectrolyserDispatch:
    def __init__(self, equipment: ElectrolyserDispatchInput) -> None:
        self._eq = equipment
        self.power_level_var: ModelVar = None  # type: ignore[assignment]

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """Compute derived parameters and create the ModelVar handles."""

    def add_variables(self, time: DateTime) -> None:
        """Register decision variables for *time*."""

    def add_constraints(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        """Add the physical constraints for *time*."""
```

Constraints:

- **No `add_objective`, no `add_reserves`.** Expose public accessors instead and let the module
  compose. The moment the class has to know which module called it, the separation is gone.
- **Type `parameters` as `AbstractModuleParameters`**, never a module's concrete parameters
  class — that would make the dispatch depend on a module.
- **Use `ModelVar`** for variable handles, so declaration and lookup share one definition of the
  name.
- **Declare variables and add constraints in separate passes.** Constraints reference earlier
  timesteps.
- **Name every constraint**, including the unit name and the timestep. See
  [Variable naming](variable-naming.md#adding-names).

Where the technology has pre-window history that the first timesteps' constraints reach back
into, follow `ThermalDispatch`: reconstruct it from the unit's own forecast, and fall back to a
documented cold-start when no history is available.

## 3. The reserve handler

Only if the technology can provide reserve. Summarised here; the full guide is in
[Reserves → Developer guide](../reserves/developer.md#adding-a-handler). In
`atlas/common/optimal_dispatch/reserves/electrolyser.py`, subclass whichever existing handler is
closest — `RenewableReserveHandler` is the baseline shape, and inheriting from it is not a claim
about the technology:

```python
class ElectrolyserReserveHandler(RenewableReserveHandler):
    def add_variables(self, time: DateTime, max_power: float, min_power: float) -> None:
        super().add_variables(time, max_power, min_power)
        # technology-specific additions
```

Build names through `self.var(prefix, time)` rather than formatting them inline.

A handler may hold a reference to its dispatch and read its state variables — that is how
`ThermalReserveHandler` zeroes reserve while a unit is starting. The reverse direction is not
allowed.

## 4. The factory method

`ReserveFactory` is the only place that constructs handlers. Add a static method:

```python
@staticmethod
def for_electrolyser(equipment: ElectrolyserDispatchInput) -> ElectrolyserReserveHandler:
    maximum_automated = (getattr(equipment, "maximum_afrr", None) or 0.0) + (
        getattr(equipment, "maximum_fcr", None) or 0.0
    )
    return ElectrolyserReserveHandler(equipment.name, maximum_automated)
```

Reserve-procurement fields live on module objects, not on the physical contract. Read them
directly if every module object for the technology carries them (as thermal and storage do), and
through `getattr` with a zero default if they may be absent — a module that does not model
reserves should still be able to build a handler.

Export the new handler from `reserves/__init__.py`.

## 5. Tests

Mirroring the source layout, under
`tests/test_unit/test_common/test_optimal_dispatch/`:

```
test_input_objects/test_electrolyser.py   # contract validation
test_dispatch/test_electrolyser.py        # variables + constraints
test_reserves/test_electrolyser.py        # reserve variables + constraints
```

The existing dispatch tests are the model to follow. They assert on the *structure* of the built
model — that a named variable exists, that a named constraint exists with the expected bounds —
rather than on solved values, which makes them fast and makes a naming regression fail loudly.

Every new code path needs a test; see [Contributing](../../contributing.md).

## Checklist

- [ ] Contract declares only fields the dispatch reads
- [ ] Dispatch has no objective and no reserve logic
- [ ] `parameters` typed as `AbstractModuleParameters`
- [ ] Variables and constraints added in separate passes
- [ ] Every constraint named, with unit name and timestep
- [ ] Handler constructed only through `ReserveFactory`
- [ ] Handler exported from `reserves/__init__.py`
- [ ] Tests for contract, dispatch and reserves
- [ ] Docs: a concept page under `docs/optimal-dispatch/concepts/`, plus rows in
      [Variable naming](variable-naming.md)
- [ ] An entry in the [changelog](../../changelog.md)
