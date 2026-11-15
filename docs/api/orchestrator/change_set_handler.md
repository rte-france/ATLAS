# ChangeSetHandler

`ChangeSetHandler` applies a **single [`ChangeSet`](change_set.md)** to the [`CurrentInputState`](current_input_state.md). It handles reference resolution, validation, and the actual mutation for each ChangeSet kind (`AddObject`, `UpdateObject`, `DeleteObject`).

In normal usage you should go through [`CISHandler`](cis_handler.md) which handles batching, ordering, and rollback. Use `ChangeSetHandler` directly only when you need fine-grained control over individual operations.

::: atlas.orchestrator.handler.change_set_handler.ChangeSetHandler
