# Tracing — `@step`

The `@step` decorator captures the execution of a function or method as a
`StepRecord`: timing, status, metadata, errors, and a tree of child steps. Root
steps are persisted to disk (`record.json` + `run.log`) and every log line emitted
inside a step is automatically tagged with the current `run_id` and step path.

## Basic usage

### On a standalone function

```python
from atlas.tracing import step

@step
def load_data():
    ...

load_data()
load_data.run_record           # StepRecord
load_data.run_record.status    # "success"
load_data.run_record.duration_seconds
```

### On a method

When applied to a method, the record is stored on the **instance** (not the class):

```python
class Worker:
    @step
    def run(self):
        ...

w = Worker()
w.run()
w.run_record                  # StepRecord, tied to this instance
```

Two instances → two independent records:

```python
a, b = Worker(), Worker()
a.run()
b.run()
a.run_record.run_id != b.run_record.run_id  # True
```

## Custom name and metadata

Pass `name` and `metadata` either as static values or as **callables** that
receive the same arguments as the decorated function (including `self` for
methods):

```python
@step(name="load-data", metadata={"version": "1.0"})
def load(): ...

@step(
    name=lambda self: f"execute-{self.parameters.name}",
    metadata=lambda self: model_to_metadata(self.parameters),
)
def execute(self): ...
```

## Nesting — building a tree

A `@step` called inside another `@step` becomes a **child**: it inherits the
parent's `run_id` and is appended to `parent.children`. Only the **root** step
(no parent in context) is persisted to disk — the entire tree ends up in a
single `record.json`.

```python
@step
def leaf(): ...

@step
def middle():
    leaf()

@step
def root():
    middle()

root()
root.run_record.children                  # [middle_record]
root.run_record.children[0].children      # [leaf_record]
# All three share the same run_id
```

Step paths are derived from the parent chain:

```
root | middle | leaf
```

This path is what appears in log prefixes and in `get_log_context()`.

## Errors and tracebacks

If the wrapped function raises, the exception propagates as usual but the record
captures it for post-mortem inspection:

```python
@step
def boom():
    raise ValueError("oops")

try:
    boom()
except ValueError:
    pass

boom.run_record.status      # "failed"
boom.run_record.error       # ValueError("oops")
boom.run_record.traceback   # full traceback string
```

The persisted `record.json` includes both `error` (string) and `traceback`.

## Multi-process — `ProcessPoolExecutor`

A drop-in replacement for `concurrent.futures.ProcessPoolExecutor` that
propagates the current step context to worker processes:

```python
from atlas.tracing import ProcessPoolExecutor, step

@step
def pipeline():
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(my_worker, x) for x in inputs]
        return [f.result() for f in futures]
```

Inside `my_worker` (running in a child process):

- Logs are tagged with `pipeline`'s `run_id` and step path.
- `@step` calls inside the worker inherit the same `run_id`.

⚠️ **Limitation**: child records created in the worker process are **not**
aggregated back into the parent's `children` list — mutations don't cross
process boundaries. The `run_id` and log tagging are preserved; the tree
structure is not.

## Persistence — what gets written

For every **root** step, `RunStore` writes one folder under `RUN_RECORD_DIR`:

```
runs/
└── 20260509_143201_pipeline_abc12345/
    ├── record.json   # the full StepRecord tree
    └── run.log       # all log lines emitted during this run
```

The folder name is `{started_at}_{step_name}_{run_id}`. Configuration
(enable/disable, dir, log level) is documented in [Logging](logging.md).
