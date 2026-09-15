# Architecture

## Why the layer exists

Day-Ahead Orders and Portfolio Optimisation solve the same physical problem with two different
objectives. Before the extraction, that meant roughly 2,200 duplicated lines across thermal and
storage alone — around 85% identical constraints for thermal, 75% for storage, with the same
variables under different names.

Duplication of that shape does not stay in sync. A fix to a ramp constraint lands in one module
and not the other, and the two dispatches quietly diverge.

The three genuine differences between the modules are:

| Difference | Day-Ahead Orders | Portfolio Optimisation |
|---|---|---|
| Objective | maximise $\sum \pi_t P_t$ against a price forecast | minimise $\sum c_t P_t$ plus imbalance penalties |
| Reserve form | fill-up against a procured forecast, bound by `setup_reserve_forecasts()` | fill-up against decision variables only |
| Balance | none | $\sum \text{imbalance} = \sum \text{commitment} + \sum P$ per portfolio |

None of these is physics. All three stay in the modules.

## Package layout

```
atlas/common/optimal_dispatch/
├── dispatch/                     # variables + physical constraints
│   ├── thermal.py                # ThermalDispatch
│   ├── thermal_initial_conditions.py
│   ├── storage.py                # StorageDispatch
│   ├── hydro.py                  # HydroDispatch
│   ├── renewable.py              # RenewableDispatch  (wind + solar)
│   └── load.py                   # LoadDispatch
│
├── input_objects/                # Pydantic contracts, one per technology
│   ├── thermal.py                # ThermalDispatchInput
│   ├── storage.py                # StorageDispatchInput
│   ├── hydro.py                  # HydroDispatchInput
│   ├── renewable.py              # RenewableDispatchInput  (Protocol)
│   └── load.py                   # LoadDispatchInput
│
├── reserves/                     # reserve variables + constraints
│   ├── handler.py                # ReserveHandler (ABC)
│   ├── thermal.py, storage.py, hydro.py, renewable.py
│   └── factory.py                # ReserveFactory
│
├── marginal_pricing.py           # InterpolatedMarginalValue (hydro water values)
└── steps/                        # AbstractOptimStep[T, P]
```

## What each piece owns

**`dispatch/*`** — decision variables and physical constraints, and nothing else. No objective
term, no reserve, no market concept. A dispatch class is bound to exactly one unit and to one
`OptimisationModel`.

**`input_objects/*`** — the contract between a module and a dispatch class. A `*DispatchInput`
declares precisely the fields the formulation reads; module-specific fields (startup costs,
reserve capacities, order parameters) stay on the module's own object, which inherits from the
contract. See [Input contracts](input-contracts.md).

**`reserves/*`** — reserve variables and constraints. Separate from dispatch because not every
module needs them and because the coupling runs one way: a reserve handler may read dispatch
state variables, never the reverse.

**`steps/AbstractOptimStep[T, P]`** — the shape a module's per-equipment step implements:
`add_variables`, `add_constraints`, `add_objective`. Generic over the equipment type `T` and the
module's parameters type `P`, so a step can narrow both without breaking substitutability.

## Composition

A module's step owns a dispatch, optionally a reserve handler, and the objective:

```
common.ThermalDispatch                common.ThermalReserveHandler
  setup / add_variables                 setup / add_variables
  add_constraints (physics)             add_constraints (reserve)
          │                                        │
          └──────────────── composed by ───────────┘
                               │
             ┌─────────────────┴──────────────────┐
             ▼                                    ▼
     ThermalStep (PO)                   ThermalStep (DAO)
     min(variable cost + hedging)       max(order profit − penalties)
```

Both steps build the same variables and the same physical constraints, then diverge only in
`add_objective`.

## The public-accessor rule

There is deliberately no `add_objective()` and no `add_reserves()` on a dispatch class. Modules
read what they need through public accessors — `power_level_var`, `off_var`, `on_up_var`,
`stored_energy_var`, `has_flat`, `combination` — and assemble their own terms.

The moment a dispatch class grows an objective method, it needs to know which module called it,
and the separation is gone.

## Coupling directions

Worth knowing before adding anything:

- Dispatch classes never import module code, and never import reserve code.
- `ThermalReserveHandler` and `HydroReserveHandler` hold a reference to their dispatch, because
  their constraints read its state variables. That direction is fine; the reverse is not.
- Reserve handlers reach reserve-procurement fields (`maximum_afrr`, `maximum_fcr`) through
  `getattr` where those fields live on module objects rather than on the contract. That keeps
  the dispatch contracts purely physical.
- `marginal_pricing.py` depends on nothing in the package. It is a pure function of a marginal
  value table and an energy level.

## Where the modules stand

Nothing under `atlas/modules/` imports this package yet. Phases 0–2 of the plan landed the
building blocks — dispatch classes, contracts, reserve handlers, unit tests — but Day-Ahead
Orders and Portfolio Optimisation still carry their own formulations, and migrating them is
tracked in [issue #266](https://github.com/rte-france/ATLAS/issues/266).

Practically, for anyone working here now: the tests under
`tests/test_unit/test_common/test_optimal_dispatch/` are the reference usage, and the LP-parity
notes scattered through the source (redundant bound constraints, constraint name suffixes) exist
so the migrated modules produce byte-identical LP files. Do not "clean them up".

## Next

- [Usage](usage.md) — the lifecycle and a worked example.
- [Extending](extending.md) — adding a technology.
