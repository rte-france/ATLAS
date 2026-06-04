# CurrentInputState

The `CurrentInputState` (CIS) is the **central shared state** passed between modules during workflow execution. It wraps an [`AtlasDataset`](../io/atlas_dataset.md) and adds snapshot, rollback, diff, and transaction capabilities.

Modules never communicate directly — they read from and write to the CIS via [ChangeSets](change_set.md) applied by the [CISHandler](cis_handler.md).

::: atlas.orchestrator.current_input_state.CurrentInputState
