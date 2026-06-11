# CLI Reference

After installing ATLAS, the `atlas` command is available. Run `atlas --help` at any time to list available commands.

## Command Overview

| Command | Description |
|---|---|
| [`atlas module run`](#atlas-module-run) | Run a single module |
| [`atlas module list`](#atlas-module-list) | List all available modules |
| [`atlas workflow run`](#atlas-workflow-run) | Run a full workflow |
| [`atlas workflow list`](#atlas-workflow-list) | List the steps declared in a workflow file |
| [`atlas version`](#atlas-version) | Print the installed version |
| [`atlas prometheus-to-atlas run`](#atlas-prometheus-to-atlas-run) | Convert a single Prometheus dataset to Atlas format |
| [`atlas prometheus-to-atlas batch`](#atlas-prometheus-to-atlas-batch) | Convert multiple Prometheus datasets at once |
| [`atlas antares-to-atlas run`](#atlas-antares-to-atlas-run) | Convert an Antares study to Atlas format |
| [`atlas antares-to-atlas validate`](#atlas-antares-to-atlas-validate) | Validate an Antares parameters file |
| [`atlas antares-to-atlas converters`](#atlas-antares-to-atlas-converters) | List converters that would run for given parameters |

---

## `atlas module run`

Runs a single Atlas module.

```bash
atlas module run <MODULE_NAME> --parameters <PARAMS> --dataset <DATASET_PATH>
```

| Argument / Option | Short | Required | Description |
|---|---|---|---|
| `MODULE_NAME` | — | Yes | Name of the module to run. Use `atlas module list` to see available modules. |
| `--parameters` | `-p` | Yes | Path to the module parameters YAML file |
| `--dataset` | `-d` | Yes | Path to the input dataset directory |

**Example:**

```bash
atlas module run DayAheadOrders -p parameters.yml -d ./data/input/
```

See [Run a Module](modules/running-modules.md) for the full execution guide.

---

## `atlas module list`

Lists all modules registered in Atlas.

```bash
atlas module list
```

---

## `atlas workflow run`

Runs a full Atlas workflow defined in a YAML file.

```bash
atlas workflow run <WORKFLOW_FILE>
```

| Argument | Required | Description |
|---|---|---|
| `WORKFLOW_FILE` | Yes | Path to the workflow configuration YAML file |

**Example:**

```bash
atlas workflow run workflow.yaml
```

See [Run a Workflow](modules/workflow.md) for the workflow configuration reference.

---

## `atlas workflow list`

Lists the steps declared in a workflow file without executing it.

```bash
atlas workflow list <WORKFLOW_FILE>
```

| Argument | Required | Description |
|---|---|---|
| `WORKFLOW_FILE` | Yes | Path to the workflow configuration YAML file |

**Example:**

```bash
atlas workflow list workflow.yaml
```

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
