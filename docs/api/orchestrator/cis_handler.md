# CISHandler

`CISHandler` is the **entry point for applying a batch of [ChangeSets](change_set.md)** to the [`CurrentInputState`](current_input_state.md). It handles ordering, duplicate detection, and optional transactional rollback.

For applying a single ChangeSet directly, see [`ChangeSetHandler`](change_set_handler.md).

::: atlas.orchestrator.handler.cis_handler.CISHandler
