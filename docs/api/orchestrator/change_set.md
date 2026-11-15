# ChangeSets

A `ChangeSet` is an **immutable description of a single mutation** to the [`CurrentInputState`](current_input_state.md). Modules produce lists of ChangeSets instead of modifying the state directly — the [CISHandler](cis_handler.md) is the only component that applies them.

There are three concrete variants:

| Class | Effect |
|---|---|
| `AddObject` | Insert a new business object into the state |
| `UpdateObject` | Modify fields of an existing object |
| `DeleteObject` | Remove an object by name |

All three share the abstract base class `ChangeSet`.

## ChangeSet (base)

::: atlas.orchestrator.change_set.ChangeSet
    options:
        show_if_no_docstring: true

## AddObject

::: atlas.orchestrator.change_set.AddObject
    options:
        show_if_no_docstring: true

## UpdateObject

::: atlas.orchestrator.change_set.UpdateObject
    options:
        show_if_no_docstring: true

## DeleteObject

::: atlas.orchestrator.change_set.DeleteObject
    options:
        show_if_no_docstring: true
