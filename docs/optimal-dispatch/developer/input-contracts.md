# Input Contracts

A dispatch class never sees a module's equipment object in full. It sees a
**`*DispatchInput`** — a Pydantic model declaring exactly the fields the formulation reads.

## The rule

> A field belongs in `*DispatchInput` **if and only if** the corresponding `*Dispatch` reads it.

Everything else — startup costs, order parameters, reserve capacities, hedging coefficients —
stays on the module's own object.

This is what keeps the layer honest. If `ThermalDispatchInput` grew a `startup_cost` field, a
reader would reasonably assume the physics depends on it, and the next person would wire an
objective term into the dispatch class. The contract is narrow so that the separation is
self-evident from the type.

## The hierarchy

Module objects inherit from the contract, adding their own fields:

```
Thermal ──► ThermalDispatchInput ──┬──► ThermalDAO   (startup_cost, additional_hours, …)
                                   └──► ThermalPO    (max_fcr, max_afrr, …)

Storage ──► StorageDispatchInput ──┬──► StorageDAO   (storage_initial_level, …)
                                   └──► StoragePO    (max_fcr, max_afrr, …)
```

So a module passes its own object straight to the dispatch class — it *is* a valid
`ThermalDispatchInput`, plus extras the dispatch never looks at. No adapter, no copying.

The base of each chain is the corresponding [core business object](../../data-model.md) in
`atlas/objects/`.

## The contracts

### Thermal

[`ThermalDispatchInput`](../../api/optimal-dispatch/input-objects.md#thermal) extends `Thermal`:

| Field | Purpose |
|---|---|
| `maximum_power`, `minimum_power` | The power envelope, and the source of $Q^{\min}$ for the ramps |
| `minimum_time_on`, `minimum_time_off` | $T^{\text{on}}$, $T^{\text{off}}$ |
| `minimum_stable_power_duration` | $T^{\text{stable}}$ — whether the unit has a stable phase |

`startup_duration`, `shutdown_duration`, `maximum_gradient`, `power`,
`has_daily_energy_constraint` and `maximum_daily_energy` are inherited from `Thermal` and read
by the dispatch too — the contract only *narrows* the types of the fields it needs as
timeseries.

### Storage

[`StorageDispatchInput`](../../api/optimal-dispatch/input-objects.md#storage) extends `Storage`:

| Field | Purpose |
|---|---|
| `maximum_energy`, `minimum_state_of_charge` | Stored-energy bounds |
| `maximum_power`, `minimum_power` | Discharge ceiling and charge floor (the latter negative) |
| `charge_efficiency`, `discharge_efficiency` | Constrained **strictly positive** |
| `storage_initial_level` | Fallback initial stock when no `stored_energy` forecast exists |
| `additional_hours` | Window extension |

!!! note "Why the efficiencies are tightened here"

    The base `Storage` object allows a zero efficiency. The dispatch formulation divides by
    `discharge_efficiency`, and a zero has no physical meaning for a unit being dispatched — so
    the constraint is added on the contract rather than pushed up into the core object, where it
    would reject data that is legitimate for other uses.

    This is the general pattern: tighten at the contract, not at the base.

### Hydro

[`HydroDispatchInput`](../../api/optimal-dispatch/input-objects.md#hydro) extends `Hydro` with
`maximum_energy`, `minimum_energy`, `maximum_power`, `minimum_power`, `initial_level` and
`additional_hours`.

Marginal values and `storage_marginal_value` are **not** in the contract. They price the
fragments, which is an objective-side concern the calling module owns — see
[Water values](../concepts/hydro.md#water-values).

### Load

[`LoadDispatchInput`](../../api/optimal-dispatch/input-objects.md#load) extends `Load` with
`load_type`, `maximum_power_forecast` and `additional_hours`.

### Renewable

[`RenewableDispatchInput`](../../api/optimal-dispatch/input-objects.md#renewable) is a
**`typing.Protocol`**, not a Pydantic model:

```python
@runtime_checkable
class RenewableDispatchInput(Protocol):
    name: str
    maximum_curtailment_ratio: AbstractTimeseries
    _cached_forecast: Timeseries | None
```

Wind and Solar share no common base class in the data model, so there is no class to inherit
from. A structural contract sidesteps that: any object exposing those three attributes satisfies
it, and the day-ahead and portfolio-optimisation wind and solar objects all qualify as they
stand.

`_cached_forecast` being part of a public contract is a wart. It reflects that the forecast is
resolved once by the step (through `prefetch_forecasts()`) and reused, rather than re-queried
per timestep. A dispatch built against an unpopulated cache produces a unit with zero maximum
power — no error, just an idle unit.

## Reserve fields

Reserve-procurement fields (`maximum_fcr`, `maximum_afrr`) are deliberately absent from every
contract, even though `ReserveFactory` reads them to compute `maximum_automated`. They live on
the module objects instead, so the dispatch contracts stay purely physical.

The factory reads them off whatever object it is handed — directly for thermal and storage,
where the module objects always carry them, and through `getattr` with a zero default for hydro
and renewable, where they may be absent entirely.

## Practical notes

- Timeseries fields are typed [`AbstractTimeseries`](../../api/math/timeseries.md), so lazy and
  eager variants are interchangeable. Never narrow to the concrete `Timeseries`.
- Durations use `DurationField`, which accepts a `pendulum.Duration` or an ISO-8601 string.
- `additional_hours` extends the optimisation window past `end_date`, so a unit is not forced to
  make a decision at the edge of the horizon that a slightly longer view would have avoided.

## Next

- [Extending](extending.md) — writing a contract for a new technology.
- [Variable naming](variable-naming.md).
