# CLI Reference

After installing ATLAS, the `atlas` command is available. Run `atlas --help` at any time to list available commands.

## Command Overview

| Command | Description |
|---|---|
| [`atlas run`](#atlas-run) | Run a module or a workflow |
| [`atlas version`](#atlas-version) | Print the installed version |
| [`atlas prometheus-to-atlas run`](#atlas-prometheus-to-atlas-run) | Convert a single Prometheus dataset to Atlas format |
| [`atlas prometheus-to-atlas batch`](#atlas-prometheus-to-atlas-batch) | Convert multiple Prometheus datasets at once |
| [`atlas antares-to-atlas run`](#atlas-antares-to-atlas-run) | Convert an Antares study to Atlas format |
| [`atlas antares-to-atlas validate`](#atlas-antares-to-atlas-validate) | Validate an Antares parameters file |
| [`atlas antares-to-atlas converters`](#atlas-antares-to-atlas-converters) | List converters that would run for given parameters |

---

## `atlas run`

Runs a single module or a full workflow. The mode is selected via a flag.

### Module mode

```bash
atlas run <parameters.yml> --module <MODULE> --dataset <DATASET_PATH>
```

| Argument / Option | Short | Required | Description |
|---|---|---|---|
| `parameters.yml` | — | Yes | Path to the module parameters YAML file |
| `--module` | `-m` | Yes | Module to run |
| `--dataset` | `-d` | Yes | Path to the input dataset directory |

Available modules:

| Name | Description |
|---|---|
| `DayAheadOrders` | Generate market orders for all equipment types |
| `MarketClearing` | Clear the market across interconnected areas |
| `PortfolioOptimisation` | Optimise energy portfolios |
| `IntradayPriceForecast` | Forecast intraday prices |

**Example:**

```bash
atlas run parameters.yml --module DayAheadOrders --dataset ./data/input/
```

See [Run a Module](modules/running-modules.md) for the full execution guide.

### Workflow mode

```bash
atlas run <workflow.yml> --workflow
```

| Argument / Option | Short | Required | Description |
|---|---|---|---|
| `workflow.yml` | — | Yes | Path to the workflow configuration YAML file |
| `--workflow` | `-w` | Yes | Flag to enable workflow mode |

**Example:**

```bash
atlas run workflow.yml --workflow
```

See [Run a Workflow](modules/workflow.md) for the workflow configuration reference.

---

## `atlas version`

Prints the currently installed version of ATLAS.

```bash
atlas version
```

```
Atlas version : 0.1.0
```

---

## `atlas prometheus-to-atlas run`

Converts a single Prometheus dataset (HDF5 + timeseries CSV files) to Atlas format.

```bash
atlas prometheus-to-atlas run <TIMESERIES_FOLDER> <HDF5_FILE> --output <OUTPUT_DIR>
```

| Argument / Option | Short | Required | Default | Description |
|---|---|---|---|---|
| `timeseries_folder` | — | Yes | — | Folder containing timeseries CSV files |
| `hdf5_file` | — | Yes | — | Path to the Prometheus HDF5 file |
| `--output` | `-o` | Yes | — | Output directory for the converted dataset |
| `--date-format-forecasting` | — | No | `DD/MM/YYYY HH:mm:ss` | Date format used in forecasting matrices |
| `--date-format-input-files` | — | No | `DD/MM/YYYY HH:mm:ss` | Date format used in input CSV files |
| `--date-format-timestep` | — | No | `DD_MM_YYYY_HH_mm_ss` | Date format used in the timestep column |
| `--mp / --no-mp` | — | No | `--mp` | Enable or disable multiprocessing |
| `--workers` | `-w` | No | auto | Number of worker processes |

**Example:**

```bash
atlas prometheus-to-atlas run \
  ./prometheus/ts/ \
  ./prometheus/data.hdf5 \
  --output ./atlas-data/ \
  --workers 4
```

---

## `atlas prometheus-to-atlas batch`

Converts all Prometheus datasets found under a root directory. Each sub-directory must contain a `ts/` folder and a single HDF5 file.

```bash
atlas prometheus-to-atlas batch <ROOT_DIR> --output <OUTPUT_ROOT_DIR>
```

| Argument / Option | Short | Required | Default | Description |
|---|---|---|---|---|
| `root_dir` | — | Yes | — | Root directory containing module sub-directories |
| `--output` | `-o` | Yes | — | Root output directory for converted datasets |
| `--mp / --no-mp` | — | No | `--mp` | Enable or disable multiprocessing |
| `--workers` | `-w` | No | auto | Number of worker processes |
| `--date-format-*` | — | No | same as `run` | Same date format options as `run` |

Expected directory structure:

```
root_dir/
├── day-ahead/
│   ├── ts/
│   └── uuid.hdf5
└── portfolio-optimisation/
    ├── ts/
    └── uuid.hdf5
```

**Example:**

```bash
atlas prometheus-to-atlas batch ./prometheus-datasets/ --output ./atlas-datasets/
```

---

<a id="atlas-antares-to-atlas"></a>

## `atlas antares-to-atlas run`

Converts an Antares study directory into an Atlas-formatted dataset.

```bash
atlas antares-to-atlas run <STUDY_PATH> --parameters <PARAMS> --output <OUTPUT_DIR>
```

| Argument / Option | Short | Required | Default | Description |
|---|---|---|---|---|
| `study_path` | — | Yes | — | Path to the Antares study directory (must contain `study.antares`) |
| `--parameters` | `-p` | Yes | — | Parameters YAML file controlling the conversion |
| `--output` | `-o` | Yes | — | Output directory for the Atlas dataset |
| `--format` | `-f` | No | `parquet` | Output file format: `parquet`, `csv`, or `pickle` |

**Example:**

```bash
atlas antares-to-atlas run ./my-study \
  --parameters antares_params.yml \
  --output ./atlas-dataset/
```

See the [Antares Integration guide](antares-integration/user-guide.md) for the parameters file format.

---

## `atlas antares-to-atlas validate`

Validates an Antares parameters file and checks that all referenced paths exist, without running the conversion.

```bash
atlas antares-to-atlas validate --parameters <PARAMS>
```

| Option | Short | Required | Description |
|---|---|---|---|
| `--parameters` | `-p` | Yes | Parameters YAML file to validate |

---

## `atlas antares-to-atlas converters`

Lists all converters that would execute for a given parameters file, without running them.

```bash
atlas antares-to-atlas converters --parameters <PARAMS>
```

| Option | Short | Required | Description |
|---|---|---|---|
| `--parameters` | `-p` | Yes | Parameters YAML file |

---

## Shell Completion

ATLAS supports shell completion for bash, zsh, and fish.

```bash
atlas --install-completion   # install for the current shell
atlas --show-completion      # print the completion script (for manual installation)
```
