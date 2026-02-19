# Command Line Interface (CLI)

Atlas provides a command-line interface built with [Typer](https://typer.tiangolo.com/) for running simulations, managing workflows, and converting data formats.

## Installation

After installing Atlas, the `atlas` command becomes available:

```bash
# Run atlas CLI
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
- `--module`, `-m` (required): Module name to execute (e.g., `PortfolioOptimisation`, `MarketClearing`, `DayAheadOrders`)
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

Convert a single Prometheus dataset to Atlas format.

**Syntax:**

```bash
atlas prometheus-to-atlas \
  <TIMESERIES_FOLDER> \
  <HDF5_FILE> \
  <OUTPUT_DIR> \
  [OPTIONS]
```

**Arguments:**

- `timeseries_folder_path`: Path to folder containing timeseries CSV files
- `hdf5_path`: Path to the Prometheus HDF5 file
- `output_dir`: Output directory for Atlas-formatted data

**Options:**

- `--date-format-forecasting`: Date format for forecasting matrices (default: `"DD/MM/YYYY HH:mm:ss"`)
- `--date-format-input-files`: Date format for input files (default: `"DD/MM/YYYY HH:mm:ss"`)
- `--date-format-timestep`: Date format for timestep column (default: `"DD_MM_YYYY_HH_mm_ss"`)
- `--use-mp / --no-use-mp`: Enable/disable multiprocessing (default: enabled)
- `--n-workers`: Number of worker processes (default: auto-detect)

**Example:**

```bash
atlas prometheus-to-atlas \
  ./prometheus/ts/ \
  ./prometheus/data.hdf5 \
  ./atlas-data/ \
  --use-mp \
  --n-workers 4
```

---

### `atlas prometheus-to-atlas-recursive` - Batch Convert Prometheus Data

Recursively convert multiple Prometheus datasets to Atlas format. Useful for processing entire directory structures.

**Syntax:**

```bash
atlas prometheus-to-atlas-recursive \
  <ROOT_DIR> \
  <OUTPUT_ROOT_DIR> \
  [OPTIONS]
```

**Arguments:**

- `root_dir`: Root directory containing multiple module folders
- `output_root_dir`: Output root directory for converted datasets

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

**Options:**

- Same as `prometheus-to-atlas` command
- Automatically processes all valid subdirectories in parallel

**Example:**

```bash
atlas prometheus-to-atlas-recursive \
  ./prometheus-datasets/ \
  ./atlas-datasets/ \
  --use-mp \
  --n-workers 8
```

**Output:**

The command will display progress and a summary:

```
Found 3 module(s) to process
Processing modules in parallel using 8 workers

Results:
✓ day-ahead: Successfully processed
✓ portfolio-optimisation: Successfully processed
✓ market-clearing: Successfully processed

Summary:
  Processed: 3
  Failed: 0
  Total: 3
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

### Converting Legacy Data

```bash
# Convert Prometheus format to Atlas format
atlas prometheus-to-atlas-recursive \
  ./legacy-data/ \
  ./atlas-data/
```

---

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

- [Getting Started](getting_started.md) - Installation and setup
- [Workflow System](api/workflow/workflow.md) - Understanding workflows
- [Module Development](concepts/overview.md) - Creating custom modules
- [AtlasDataset](api/io/atlas_dataset.md) - Input/output data format
