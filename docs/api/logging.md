# Logging

Atlas uses [Loguru](https://github.com/Delgan/loguru) under the hood. Configuration is
driven by environment variables (and an optional `.env` file at the project root).

## How to use

Import the logger and use it directly — it is configured for you when `atlas.config`
is imported anywhere in your app.

```python
from atlas.config import logger

logger.info("Logger is working!")
logger.debug("This is a debug message.")
```

When inside an `@step`-decorated function, every log line is automatically tagged
with the current `run_id` and step path:

```
14:32:01 | INFO     | abc12345 | outer | inner | hello from inner step
```

## Configuration

Configuration is **optional** — the defaults work out of the box.

Set environment variables directly, or create a `.env` file at the project root.
The full set of supported variables (with defaults) is shown below — copy this into
your `.env` and uncomment what you want to override.

```dotenv
# ---------------------------------------------------------------------------
# Logging (atlas.log.LoggerSettings)
# ---------------------------------------------------------------------------

# Logging level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Loguru format string for the stdout sink. The run_id and step path are injected
# automatically as a pipe-separated prefix before {message}.
LOG_FORMAT=<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>


# ---------------------------------------------------------------------------
# Per-run persistence (atlas.tracing.RunStore)
# ---------------------------------------------------------------------------

# Enable/disable writing record.json + run.log per @step root call.
RUN_RECORD_ENABLED=true

# Directory where each run is persisted (one subfolder per run).
RUN_RECORD_DIR=runs

# Also write a run.log file alongside record.json (per root step).
RUN_RECORD_LOG=true

# Level for the per-run log file (independent of LOG_LEVEL).
RUN_RECORD_LOG_LEVEL=DEBUG
```
