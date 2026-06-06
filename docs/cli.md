# Command Line Interface (CLI)

Atlas provides a command-line interface built with [Typer](https://typer.tiangolo.com/) for running simulations, managing workflows, and converting data formats.

## Installation

After installing Atlas, the `atlas` command becomes available:

```bash
atlas --help
```

## Available Commands

### `atlas run` - Run Modules or Workflows

The primary command for executing Atlas simulations. It supports two modes:

#### Module Mode (Default)

Run a single simulation module with a parameters file and input dataset.

**Syntax:**
```bash
atlas run <parameters.yaml> --module <MODULE_NAME> --dataset <DATASET_PATH>
```

**Options:**

- `config_path` (required): Path to the module parameters YAML file
- `--module`, `-m` (required): Module name to execute (e.g., `PortfolioOptimisation`, `MarketClearing`, `DayAheadOrders`, `IntradayPriceForecast`)
- `--dataset`, `-d` (required): Path to the input dataset directory containing Atlas-formatted data

**Example:**

```bash
atlas run parameters.yaml \
  --module PortfolioOptimisation \
  --dataset ./data/atlas-dataset/portfolio-optimisation/
```

**Available Modules:**

- `PortfolioOptimisation` - Portfolio optimization simulation
- `MarketClearing` - Market clearing simulation
- `DayAheadOrders` - Day-ahead order generation
- `IntradayPriceForecast` - Intraday price forecast

#### Workflow Mode

Execute a complete workflow with multiple sequential steps.

**Syntax:**

```bash
atlas run <workflow.yaml> --workflow
```

**Options:**

- `config_path` (required): Path to the workflow configuration YAML file
- `--workflow`, `-w`: Flag to enable workflow mode

**Example:**

```bash
atlas run workflow.yaml --workflow
```

**How Workflows Work:**

1. Each workflow consists of multiple steps (see [Workflow Documentation](api/workflow/workflow.md))
2. Steps are executed sequentially
3. Output from one step becomes input for the next step
4. The workflow configuration defines all steps and their parameters

---

### `atlas version` - Check Version

Display the currently installed version of Atlas.

**Syntax:**
```bash
atlas version
```

**Example Output:**
```
Atlas version : 0.1.0
```

---

### `atlas prometheus-to-atlas` - Convert Prometheus Data

Converts Prometheus datasets to Atlas format. Two subcommands are available.

#### `atlas prometheus-to-atlas run`

Convert a single Prometheus dataset.

**Syntax:**

```bash
atlas prometheus-to-atlas run \
  <TIMESERIES_FOLDER> \
  <HDF5_FILE> \
  --output <OUTPUT_DIR> \
  [OPTIONS]
```

**Arguments:**

- `timeseries_folder_path`: Path to folder containing timeseries CSV files
- `hdf5_path`: Path to the Prometheus HDF5 file

**Options:**

- `--output`, `-o` (required): Output directory for Atlas-formatted data
- `--date-format-forecasting`: Date format for forecasting matrices (default: `"DD/MM/YYYY HH:mm:ss"`)
- `--date-format-input-files`: Date format for input files (default: `"DD/MM/YYYY HH:mm:ss"`)
- `--date-format-timestep`: Date format for timestep column (default: `"DD_MM_YYYY_HH_mm_ss"`)
- `--mp / --no-mp`: Enable/disable multiprocessing (default: enabled)
- `--workers`, `-w`: Number of worker processes (default: auto-detect)

**Example:**

```bash
atlas prometheus-to-atlas run \
  ./prometheus/ts/ \
  ./prometheus/data.hdf5 \
  --output ./atlas-data/ \
  --workers 4
```

---

#### `atlas prometheus-to-atlas batch`

Convert all Prometheus datasets found in a directory. Each sub-directory must contain a `ts/` folder and a single HDF5 file.

**Syntax:**

```bash
atlas prometheus-to-atlas batch \
  <ROOT_DIR> \
  --output <OUTPUT_ROOT_DIR> \
  [OPTIONS]
```

**Arguments:**

- `root_dir`: Root directory containing multiple module sub-directories

**Options:**

- `--output`, `-o` (required): Root output directory for converted datasets
- Same date format and multiprocessing options as `run`

**Expected Directory Structure:**

```
root_dir/
├── day-ahead/
│   ├── ts/              # Timeseries CSV files
│   └── uuid-file.hdf5   # HDF5 data file
├── portfolio-optimisation/
│   ├── ts/
│   └── uuid-file.hdf5
└── market-clearing/
    ├── ts/
    └── uuid-file.hdf5
```

**Example:**

```bash
atlas prometheus-to-atlas batch \
  ./prometheus-datasets/ \
  --output ./atlas-datasets/ \
  --workers 8
```

**Output:**

```
Summary: 3 succeeded, 0 failed out of 3
```

---

<a id="atlas-antares-to-atlas"></a>

### `atlas antares-to-atlas` - Convert an Antares Study

Convert an Antares study directory into an Atlas-formatted dataset. See the [Antares Integration guide](antares-integration/user-guide.md) for full details.

#### `atlas antares-to-atlas run`

```bash
atlas antares-to-atlas run <STUDY_PATH> \
  --parameters parameters.yaml \
  --output ./atlas-dataset/ \
  --format parquet
```

**Arguments:**

- `STUDY_PATH`: Path to the Antares study directory (must contain `study.antares`)

**Options:**

- `-p, --parameters` (required): Parameters YAML file
- `-o, --output` (required): Output directory for the Atlas dataset
- `-f, --format` (optional, default: `parquet`): Output format — `parquet`, `csv`, or `pickle`

#### `atlas antares-to-atlas validate`

Validate a parameters file without running the conversion.

```bash
atlas antares-to-atlas validate --parameters parameters.yaml
```

#### `atlas antares-to-atlas converters`

List all converters that would execute with the given parameters.

```bash
atlas antares-to-atlas converters --parameters parameters.yaml
```

---

## Common Usage Patterns

### Running a Simple Simulation

```bash
# 1. Prepare your input data
# 2. Create parameters.yaml
# 3. Run the module
atlas run parameters.yaml \
  --module PortfolioOptimisation \
  --dataset ./data/input/
```

### Running a Complete Workflow

```bash
# 1. Define workflow.yaml with all steps
# 2. Execute the workflow
atlas run workflow.yaml --workflow
```

## Shell Completion

Atlas CLI supports shell completion for bash, zsh, and fish.

**Install completion:**

```bash
atlas --install-completion
```

**Show completion script (for manual installation):**

```bash
atlas --show-completion
```

---

## Related Documentation

- [Getting Started](getting_started/getting_started.md) - Installation and setup
- [Workflow System](api/workflow/workflow.md) - Understanding workflows
- [Module Development](implementing-a-module.md) - Creating custom modules
- [AtlasDataset](api/io/atlas_dataset.md) - Input/output data format
