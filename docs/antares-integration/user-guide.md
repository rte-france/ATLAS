# Antares-to-Atlas User Guide

This guide walks through converting an Antares study to an Atlas dataset using the `atlas antares-to-atlas` command group.

## Prerequisites

- Atlas installed (`uv sync --all-groups`)
- An Antares study directory (the folder that contains `study.antares`)
- A parameters YAML file (see [Parameters reference](#parameters-reference) below)

## CLI Commands

### `run` — Convert a study

```bash
atlas antares-to-atlas run <STUDY_PATH> \
  --parameters parameters.yaml \
  --output ./atlas-dataset/ \
  --format parquet
```

| Argument / Option | Required | Description |
|---|---|---|
| `STUDY_PATH` | yes | Path to the Antares study directory |
| `-p, --parameters` | yes | Parameters YAML file |
| `-o, --output` | yes | Output directory for the Atlas dataset |
| `-f, --format` | no | Output format: `parquet` (default), `csv`, or `pickle` |

The command loads the Antares study, executes all active converters in order, and writes an `AtlasDataset` to the output directory. That directory can be passed directly to `atlas run --dataset`.

---

### `validate` — Check parameters without converting

```bash
atlas antares-to-atlas validate --parameters parameters.yaml
```

Validates the parameters file and checks that all referenced paths exist. Prints a summary of the configuration and the list of converters that would execute. No study path required — useful for CI checks.

---

### `converters` — List active converters

```bash
atlas antares-to-atlas converters --parameters parameters.yaml
```

Lists every converter that would run, with its name, description, and tags. Useful for understanding the effect of `only_tags`, `skip_tags`, or `conversion_steps` before a full run.

---

## Parameters Reference

The parameters file is a YAML document validated against `AntaresToAtlasParameters`.

### Minimal example

```yaml
start_date: "2030-01-01T00:00:00"
execution_date: "2025-06-01T00:00:00"
output_name: "1"
market_areas: ["fr", "de", "es", "be", "nl"]
```

### Full annotated example

```yaml
# ── Identity ────────────────────────────────────────────────────────────────
start_date: "2030-01-01T00:00:00"    # First timestep of the simulation horizon
execution_date: "2025-06-01T00:00:00" # Date the study was executed (used for naming)
output_name: "1"                      # Monte-Carlo year number to load from Antares output
hypothesis: "BP23"                    # Optional — activates BP23-specific converters

# ── Area selection ───────────────────────────────────────────────────────────
market_areas: "all"                   # "all" auto-expands to every area in the study…
excluded_market_areas: ["xnode"]      # …minus these exclusions
# Or use an explicit list:
# market_areas: ["fr", "de", "es", "be", "nl", "ch"]

excluded_thermic_groups: []           # Thermal cluster names to skip globally

# ── Economic bounds ──────────────────────────────────────────────────────────
minimum_price: -500.0                 # Floor price (€/MWh)
maximum_price: 3000.0                 # Cap price (€/MWh)

# ── Renewables ───────────────────────────────────────────────────────────────
renewables:
  wind_max_curtailment_ratio: 1.0
  pv_max_curtailment_ratio: 1.0
  wind_curtailment_cost: 0.01         # €/MWh
  pv_curtailment_cost: 0.01
  wind_offshore_suffix: "_wind_offshore"
  wind_offshore_excluded_areas: ["dekf", "dkkf"]
  solar_thermo_suffix: "_solar_thermo"

# ── Storage initial levels ───────────────────────────────────────────────────
storage:
  battery_initial_level: 0.2          # Default for all areas [0–1]
  battery_initial_level_by_area:      # Per-area overrides
    fr: 0.3
  ev_initial_level: 0.5
  phs_initial_level: 0.2
  phs_initial_level_by_area:
    fr: 0.4

# ── Converter filtering ──────────────────────────────────────────────────────
# Run only a subset of converters by tag:
only_tags: []                         # Empty = no restriction (run all)
skip_tags: []                         # Tags whose converters to skip entirely

# Or name converters explicitly (overrides tag filters):
conversion_steps: []                  # Empty = run all active converters

# ── Portfolio separation ─────────────────────────────────────────────────────
consumption_production_separation: false
```

---

### Key parameters explained

#### `market_areas`

Controls which Antares areas are converted. Use `"all"` to include every area in the study (minus `excluded_market_areas`), or provide an explicit list:

```yaml
market_areas: ["fr", "de", "es"]
# or
market_areas: "all"
excluded_market_areas: ["xnode", "virtual_area"]
```

#### `hypothesis`

Activates hypothesis-specific converters. Currently supported:

- `BP23` — RTE Bilan Prévisionnel 2023 conventions. Adds 15 extra converters for electric vehicles, open-loop PHS, mixed-fuel thermals, P2G, multi-energy nodes, DSR, nuclear modulation, and Bellman water values.

Omit `hypothesis` (or set it to `null`) to run only the 10 standard converters.

#### `output_name`

The name of the Monte-Carlo scenario to read from the Antares output. Must match the directory name of an MC year inside the study's `output` folder (e.g. `"1"` reads `output/<run>/economy/mc-ind/00001/`).

#### Converter filtering

Three mutually exclusive mechanisms control which converters execute:

| Parameter | Behaviour |
|---|---|
| `conversion_steps: [name1, name2]` | Run only these converters by name, in order |
| `only_tags: [hydro, thermal]` | Run only converters tagged with at least one of these tags |
| `skip_tags: [storage, p2g]` | Skip converters whose tags overlap this list |

`conversion_steps` takes precedence over tag filters. Converters marked `always_run` (e.g. `SystemStructureConverter`) bypass tag filters but still respect `conversion_steps`.

Available tags: `load`, `renewable`, `hydro`, `thermal`, `storage`, `battery`, `demand`, `p2g`, `multi_energy`, `system`.

---

## Full Workflow Example

```bash
# 1. Validate parameters before committing to a full run
atlas antares-to-atlas validate -p parameters.yaml

# 2. Preview active converters
atlas antares-to-atlas converters -p parameters.yaml

# 3. Convert the study
atlas antares-to-atlas run /path/to/antares-study \
  -p parameters.yaml \
  -o ./my-atlas-dataset/ \
  -f parquet

# 4. Run an Atlas simulation on the converted dataset
atlas run parameters_atlas.yaml \
  --module PortfolioOptimisation \
  --dataset ./my-atlas-dataset/
```

---

## Python API

You can also drive the conversion from Python:

```python
from atlas.modules.antares_to_atlas import AntaresToAtlas

converter = AntaresToAtlas.from_file("parameters.yaml")

# Inspect converters that will run
for name, description in converter.list_converter_details():
    print(f"{name}: {description}")

# Run the conversion
dataset = converter.convert("/path/to/antares-study")

# Export
dataset.to_directory("./my-atlas-dataset/", format="parquet")
```

---

## Troubleshooting

**`FileNotFoundError` on `initialization_curve` or `path_inflows`**

These optional hydro parameters point to external files. Check that the paths in your YAML are absolute, or relative to your working directory.

**`ValueError: market_areas='all' but no areas found`**

The study path is invalid or `antares-craft` cannot read it. Verify that `study.antares` exists at the root of the path you pass to `run`.

**Unexpected empty dataset after conversion**

Run `atlas antares-to-atlas converters -p parameters.yaml` to confirm the converters you expect are active. A restrictive `only_tags` or `conversion_steps` list is the most common cause.
