# ContextParameters

A `ContextParameters` carries values an [orchestrator](orchestrator.md) applies to every module it runs, in two
blocks:

| Block | Applies when | Precedence |
|---|---|---|
| `default` | The target leaves the value unset | Lowest — the target's own value wins |
| `forced` | Always | Highest — overrides the target's value |

Overall precedence is `forced > module parameters > default`.

!!! note Merging is **deep**
        a context touching `temporal.execution_date` leaves `temporal.start_date` alone.
        Nested mappings are merged key by key rather than replaced wholesale.

See [Context](../../modules/context.md) for the conceptual guide, worked examples, and the caveat about
`use_context()` after construction.

## Methods

| Method | Use |
|---|---|
| `apply(context)` | Merge another context into this one; the argument wins on overlapping keys |
| `apply_on_dict(base)` | Apply to a raw parameters dict before validation — used for file and inline parameters |
| `apply_on_parameters(parameter)` | Apply to an already-built parameters object; `default` only fills fields whose value is `None`, and both blocks only reach top-level fields |

::: atlas.io_utils.parameters.ContextParameters
    options:
        show_if_no_docstring: true
