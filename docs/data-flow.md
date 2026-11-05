# Data Flow & Orchestration

This page explains how data moves between modules at runtime. Understanding this is essential before implementing a new module or debugging unexpected state.

## The Three Actors

| Actor | Role |
|---|---|
| [`CurrentInputState`](../api/orchestrator/current_input_state.md) | Shared mutable state — wraps an `AtlasDataset` and is passed sequentially to every module. |
| [`ChangeSet`](../api/orchestrator/change_set.md) | Immutable description of one mutation (`AddObject`, `UpdateObject`, `DeleteObject`). Modules produce lists of these — they never write to the CIS directly. |
| [`CISHandler`](../api/orchestrator/cis_handler.md) | The only component that applies ChangeSets to the CIS. Handles ordering, duplicate detection, and transactional rollback. |

## Execution Flow

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant M as Module N
    participant CIS as CurrentInputState
    participant H as CISHandler

    O->>CIS: pass to Module N
    CIS->>M: read data (AtlasDataset)
    M->>M: execute logic
    M-->>O: return list[ChangeSet]
    O->>H: apply(change_sets, cis)
    H->>H: order + validate + dedup
    H->>CIS: mutate containers
    O->>CIS: pass updated state to Module N+1
```

1. The orchestrator passes the CIS to the current module.
2. The module reads data from `cis.data` (the underlying `AtlasDataset`) through its `InputDataset`.
3. The module executes its logic and populates its `ModuleResult`, then calls `build_change_sets()`.
4. The orchestrator calls `CISHandler.apply(change_sets, cis)`.
5. `CISHandler` orders the change sets (dependency order), detects duplicates, then delegates each to `ChangeSetHandler.apply()`.
6. The updated CIS is passed to the next module.

## Why ChangeSets?

Modules must not modify the CIS directly. Using ChangeSets enforces:

- **Isolation** — a module's side effects are explicit and auditable.
- **Rollback** — if a batch partially fails, `CISHandler` restores the affected containers atomically.
- **Ordering** — `CISHandler` reorders mutations to respect `ControlBlock → MarketArea → Node/Portfolio → Equipment` dependency order, regardless of the order modules produce them.

## ChangeSet Types

```python
from atlas.orchestrator.change_set import AddObject, UpdateObject, DeleteObject

# Add a new object
AddObject({"name": "new_thermal", "node": "node_fr", ...}, Thermal)

# Update fields on an existing object
UpdateObject({"name": "thermal_1", "da_power": timeseries}, Thermal)

# Remove an object by name
DeleteObject("thermal_old", Thermal)
```

All three require a `"name"` key. References to other business objects can be passed as strings (resolved automatically against the CIS) or as object instances.

## Snapshot & Rollback

`CurrentInputState` supports named snapshots for debugging or manual rollback:

```python
cis.create_snapshot("before_module_3")

# ... apply changes ...

# Something went wrong — restore
cis.restore_snapshot("before_module_3")

# Or inspect what changed
diff = cis.diff(label="before_module_3")
print(diff["thermal"]["modified"])  # ['thermal_1', 'thermal_2']
```

For transactional safety within a single batch, `CISHandler` keeps an undo log: before each change set, the touched container is copied shallowly (references only, once per batch) and an updated object keeps its previous field values. On any error the very same instances are put back, so references between objects stay valid. An `UpdateObject` is also atomic on its own: the whole object is validated before any field is written.

### Copy cost

Copying a dataset never duplicates timeseries or matrices: their Polars frames are shared (see `atlas/math/copying.py`). A deep copy therefore costs about 2 KB and 50 µs per business object (measured on `tests/dataset`), and scales with the number of objects, mostly orders. Per job, the orchestrator still deep copies the dataset given to the module (`cis.get_data(copy=True)`), plus one copy per snapshot when `create_job_snapshots` is enabled. Replacing the module input copy with read-only views is left as a follow-up.

## Implementing a Module: Checklist

- [ ] `InputDataset.__init__` — extract from `AtlasDataset`, never hold a reference to the CIS itself.
- [ ] `ModuleResult.build_change_sets()` — emit `UpdateObject` / `AddObject` / `DeleteObject` for every mutated object.
- [ ] Never call `CISHandler` or `ChangeSetHandler` from inside a module — the orchestrator does this.
- [ ] Use module-specific wrapper objects (`input_objects/`) to add computed properties; don't mutate the raw business objects during `import_data`.

See [Implementing a Module](implementing-a-module.md) for the full step-by-step guide.
