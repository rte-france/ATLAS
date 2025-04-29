# Logging

This logger utility provides a project-wide logging solution using [Loguru](https://github.com/Delgan/loguru), with configuration driven by environment variables and an optional `.env` file.

::: atlas.logging.Logger

## Features

- Log level and output customizable via environment variables
- Optional file logging with rotation and retention policies
- Pretty terminal output with function and line number context
- Easy integration in any Python script or module
- `.env` support using `python-dotenv`

---

## How to use ?

Very simply, import the `logger` from `atlas` package

```python
from atlas.config import logger

logger.info("Logger is working!")
logger.debug("This is a debug message.")
```

## Configuration

### Environment file or variables

It is completely **optional** !

You can either :

- Define environment variables to_fileing them directly.
- Define environment variables in a `.env` file at the root of your project:

```txt
LOG_LEVEL=DEBUG
LOG_TO_FILE=true
LOG_DIR=logs
LOG_ROTATION=10 MB
LOG_RETENTION=7 days
LOG_NAME=atlas
LOG_FORMAT=
```
