import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Literal, cast

import typer
from rich import print as rprint
from rich.table import Table

import atlas
from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.config import logger
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.prometheus_transformer import PrometheusToAtlasDataParser, find_hdf5_files
from atlas.modules.antares_to_atlas.antares_to_atlas import AntaresToAtlas
from atlas.modules.module_run import ModuleRun
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.module_registry import ModuleRegistry
from atlas.orchestrator.workflow.workflow import Workflow
from atlas.profiling.module import run as run_module
from atlas.profiling.workflow import run as run_workflow
from atlas.timing import timer

_PROFILING_LEVELS = ["workflow", "module"]

app = typer.Typer()

module_app = typer.Typer(help="Module operations.")
app.add_typer(module_app, name="module")

workflow_app = typer.Typer(help="Workflow operations.")
app.add_typer(workflow_app, name="workflow")


@module_app.command("run")
def run_module_cmd(
    module_name: str = typer.Argument(help="Module name. Run atlas module list to list availables modules."),
    parameters_path: Path = typer.Option(..., "--parameters", "-p", help="Path to the module parameters YAML"),
    dataset_path: Path = typer.Option(..., "--dataset", "-d", help="Path to the Atlas input dataset directory"),
) -> None:
    """Run a single Atlas module.

    \b
      atlas module run PortfolioOptimisation -p params.yaml -d ./data/
    """
    if not dataset_path.exists() or not dataset_path.is_dir():
        rprint(f"Error: Dataset directory not found: {dataset_path}")
        raise typer.Exit(code=1)

    if not parameters_path.exists():
        rprint(f"Error: Parameters file not found: {parameters_path}")
        raise typer.Exit(code=1)

    try:
        module_class = ModuleRegistry.get(module_name)
    except ValueError as e:
        rprint(f"Error: {e}")
        raise typer.Exit(code=1) from e

    logger.info(f"Running module: {module_name}")
    logger.info(f"  Dataset   : {dataset_path}")
    logger.info(f"  Parameters: {parameters_path}")

    try:
        with timer() as t:
            dataset = AtlasDataset.from_directory(dataset_path)
            module = module_class()
            params = cast(AbstractModuleParameters, module.get_parameters_class()).from_file(parameters_path)
            result = ModuleRun(module, dataset, params).run()

            if params.output.export_output_dataset:
                CurrentInputState(result).to_directory(params.get_output_dataset_dir())

        logger.info(f"Module '{module_name}' completed in {t()} seconds")
        rprint(f"[bold green]✓[/bold green] Module '{module_name}' completed successfully.")
    except Exception as e:
        logger.exception(f"✗ Module '{module_name}' failed: {e}")
        raise typer.Exit(code=1) from e


@module_app.command("list")
def list_modules() -> None:
    """List all available Atlas modules.

    \b
      atlas module list
    """
    names = ModuleRegistry.get_names()
    table = Table(title=f"Available modules ({len(names)})", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Module", style="bold")
    for i, name in enumerate(names, 1):
        table.add_row(str(i), name)
    rprint(table)


@workflow_app.command("run")
def run_workflow_cmd(
    parameters_path: Path = typer.Argument(help="Path to the workflow configuration YAML"),
) -> None:
    """Run an Atlas workflow.

    \b
      atlas workflow run workflow.yaml
    """
    if not parameters_path.exists():
        rprint(f"[bold red]Error[/bold red]: Workflow configuration file not found: {parameters_path}")
        raise typer.Exit(code=1)

    logger.info(f"Running workflow: {parameters_path}")
    with timer() as t:
        wf = Workflow.from_file(parameters_path)
        wf.execute()
    logger.info(f"Workflow completed in {t()} seconds")
    logger.info("✓ Workflow completed successfully.")


@workflow_app.command("list")
def list_workflow(
    parameters_path: Path = typer.Argument(help="Path to the workflow configuration YAML"),
) -> None:
    """List the steps declared in a workflow file.

    \b
      atlas workflow list workflow.yaml
    """
    from atlas.orchestrator.workflow.parameters import WorkflowParameters

    if not parameters_path.exists():
        rprint(f"[bold red]Error[/bold red]: Workflow configuration file not found: {parameters_path}")
        raise typer.Exit(code=1)

    try:
        params = WorkflowParameters.from_file(parameters_path)
    except Exception as e:
        rprint(f"[bold red]Error[/bold red]: Failed to load workflow: {e}")
        raise typer.Exit(code=1) from e

    title = f"Workflow: {params.name or parameters_path.stem}  —  {len(params.steps)} step(s)"
    table = Table(title=title, show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Step name", style="bold")
    table.add_column("Module")
    table.add_column("Parameters file", style="dim")
    for i, step in enumerate(params.steps, 1):
        table.add_row(str(i), step.name or "", step.module.name, str(step.parameters_path))
    rprint(table)


@app.command()
def profiling(
    level: str = typer.Option(
        ..., "--level", "-l", help=f"Profiling level. Valid levels: {', '.join(_PROFILING_LEVELS)}"
    ),
    parameters: Path = typer.Option(..., "--parameters", "-p", help="Path to the workflow or module parameters YAML"),
    module_name: str | None = typer.Option(None, "--module", "-m", help="Module name (required for level 'module')"),
    dataset_path: Path | None = typer.Option(
        None, "--dataset", "-d", help="Dataset directory (required for level 'module')"
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path stem. Workflow: saves <stem>.json + <stem>.csv. Module: saves <stem>.html + <stem>_stats.txt",
    ),
) -> None:
    """Profile an Atlas workflow or module.

    \b
    Workflow-level profiling (timing breakdown per job):
      atlas profiling --level workflow --parameters workflow.yml

    \b
    Module-level profiling (pyinstrument + cProfile):
      atlas profiling --level module --parameters params.yml --module DayAheadOrders --dataset ./data
    """
    if level not in _PROFILING_LEVELS:
        rprint(f"[bold red]Error[/bold red]: Unknown level '{level}'. Valid levels: {', '.join(_PROFILING_LEVELS)}")
        raise typer.Exit(code=1)

    if not parameters.exists():
        rprint(f"[bold red]Error[/bold red]: Parameters file not found: {parameters}")
        raise typer.Exit(code=1)

    if level == "workflow":
        run_workflow(parameters, output)

    elif level == "module":
        if module_name is None:
            rprint("[bold red]Error[/bold red]: --module is required for level 'module'.")
            raise typer.Exit(code=1)
        if dataset_path is None:
            rprint("[bold red]Error[/bold red]: --dataset is required for level 'module'.")
            raise typer.Exit(code=1)
        if not dataset_path.exists() or not dataset_path.is_dir():
            rprint(f"[bold red]Error[/bold red]: Dataset directory not found: {dataset_path}")
            raise typer.Exit(code=1)

        try:
            ModuleRegistry.get(module_name)
        except ValueError as e:
            rprint(f"[bold red]Error[/bold red]: {e}")
            raise typer.Exit(code=1) from e

        run_module(parameters, module_name, dataset_path, output)


antares_app = typer.Typer(help="Convert Antares studies to Atlas dataset format.")
app.add_typer(antares_app, name="antares-to-atlas")


def _load_converter(parameters_file: Path) -> AntaresToAtlas:
    try:
        return AntaresToAtlas.from_file(parameters_file)
    except Exception as e:
        rprint(f"[bold red]Error[/bold red]: Failed to load parameters: {e}")
        raise typer.Exit(code=1) from e


@antares_app.command("run")
def antares_run(
    study_path: Path = typer.Argument(help="Path to the Antares study directory"),
    parameters_file: Path = typer.Option(..., "--parameters", "-p", help="Parameters YAML file"),
    output: Path = typer.Option(..., "--output", "-o", help="Directory to write the converted AtlasDataset"),
    fmt: Literal["csv", "parquet", "pickle"] = typer.Option("parquet", "--format", "-f"),
) -> None:
    """Convert an Antares study to Atlas dataset format.

    \b
    Basic conversion:
      atlas antares-to-atlas run ./study -p params.yaml -o ./dataset/

    \b
    CSV output:
      atlas antares-to-atlas run ./study -p params.yaml -o ./dataset/ -f csv
    """
    if not parameters_file.exists():
        rprint(f"[bold red]Error[/bold red]: Parameters file not found: {parameters_file}")
        raise typer.Exit(code=1)

    if not study_path.exists() or not study_path.is_dir():
        rprint(f"[bold red]Error[/bold red]: Study directory not found: {study_path}")
        raise typer.Exit(code=1)

    converter = _load_converter(parameters_file)

    logger.info(f"Study     : {study_path}")
    logger.info(f"Parameters: {parameters_file}")
    logger.info(f"Output    : {output} ({fmt})")

    try:
        with timer() as t:
            dataset = converter.convert(study_path)
        rprint(f"[bold green]✓[/bold green] Conversion completed in {t()} seconds")
    except Exception as e:
        logger.exception(f"✗ Conversion failed: {e}")
        raise typer.Exit(code=1) from e

    try:
        dataset.to_directory(
            output,
            timeseries_file_extension=fmt,
            matrix_file_extension=fmt,
        )
        rprint(f"[bold green]✓[/bold green] Dataset written to: {output}")
    except Exception as e:
        logger.exception(f"✗ Failed to write dataset: {e}")
        raise typer.Exit(code=1) from e


@antares_app.command("validate")
def antares_validate(
    parameters_file: Path = typer.Option(..., "--parameters", "-p", help="Parameters YAML to validate"),
) -> None:
    """Validate a parameters file without running the conversion.

    \b
    Check parameters and list converters that would run:
      atlas antares-to-atlas validate -p params.yaml
    """
    if not parameters_file.exists():
        rprint(f"[bold red]Error[/bold red]: Parameters file not found: {parameters_file}")
        raise typer.Exit(code=1)

    converter = _load_converter(parameters_file)
    p = converter.parameters

    rprint(f"[bold green]✓[/bold green] Parameters loaded from [cyan]{parameters_file}[/cyan]")
    rprint(f"  start_date   : {p.start_date}")
    rprint(f"  execution_date: {p.execution_date}")
    rprint(f"  hypothesis   : {p.hypothesis or '(none)'}")
    rprint(f"  scenario     : {p.scenario}")
    rprint(f"  output_name  : {p.output_name}")
    rprint(f"  market_areas : {', '.join(p.market_areas)}")

    paths = {
        "initialization_curve": p.hydro.initialization_curve,
        "path_inflows": p.hydro.path_inflows,
        "baseline_displacement_energy": p.baseline_displacement_energy,
        "disp_energy_node_parameters": p.disp_energy_node_parameters,
    }
    path_issues = [f"{k}: {v}" for k, v in paths.items() if v is not None and not Path(v).exists()]
    if path_issues:
        rprint("\n[bold red]✗ Missing paths:[/bold red]")
        for issue in path_issues:
            rprint(f"  {issue}")
    else:
        rprint("  paths        : [green]OK[/green]")

    details = converter.list_converter_details()
    table = Table(title=f"\nConverters that would run ({len(details)})", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", style="bold")
    table.add_column("Description", style="dim")
    for i, (name, description) in enumerate(details, 1):
        table.add_row(str(i), name, description)
    rprint(table)


@antares_app.command("converters")
def antares_converters(
    parameters_file: Path = typer.Option(..., "--parameters", "-p", help="Parameters YAML"),
) -> None:
    """List converters that would run for a given parameters file.

    \b
      atlas antares-to-atlas converters -p params.yaml
    """
    if not parameters_file.exists():
        rprint(f"[bold red]Error[/bold red]: Parameters file not found: {parameters_file}")
        raise typer.Exit(code=1)

    converter = _load_converter(parameters_file)
    details = converter.list_converter_details()

    table = Table(title=f"Converters ({len(details)})", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", style="bold")
    table.add_column("Description", style="dim")
    for i, (name, description) in enumerate(details, 1):
        table.add_row(str(i), name, description)
    rprint(table)


@app.command()
def version() -> None:
    """Print the version of the package."""
    rprint(f"[bold]Atlas version[/bold] : {atlas.__version__}")  # noqa: T201


prometheus_app = typer.Typer(help="Convert Prometheus format data to Atlas dataset format.")
app.add_typer(prometheus_app, name="prometheus-to-atlas")

_DATE_FORMAT_FORECASTING = typer.Option("DD/MM/YYYY HH:mm:ss", help="Date format for forecasting matrices")
_DATE_FORMAT_INPUT = typer.Option("DD/MM/YYYY HH:mm:ss", help="Date format for input files")
_DATE_FORMAT_TIMESTEP = typer.Option("DD_MM_YYYY_HH_mm_ss", help="Date format for timestep column")


@prometheus_app.command("run")
def prometheus_run(
    timeseries_folder_path: Path = typer.Argument(help="Folder containing timeseries CSV files"),
    hdf5_path: Path = typer.Argument(help="Path to the HDF5 file"),
    output_dir: Path = typer.Option(..., "--output", "-o", help="Output directory"),
    date_format_forecasting: str = _DATE_FORMAT_FORECASTING,
    date_format_input_files: str = _DATE_FORMAT_INPUT,
    date_format_timestep: str = _DATE_FORMAT_TIMESTEP,
    use_mp: bool = typer.Option(True, "--mp/--no-mp", help="Enable multiprocessing"),
    n_workers: int | None = typer.Option(None, "--workers", "-w", help="Number of worker processes"),
) -> None:
    """Convert a single Prometheus dataset to Atlas format.

    \b
      atlas prometheus-to-atlas run ./ts_folder ./data.hdf5 -o ./output/
    """
    if not timeseries_folder_path.exists():
        rprint(f"[bold red]Error[/bold red]: Timeseries folder not found: {timeseries_folder_path}")
        raise typer.Exit(code=1)

    if not hdf5_path.exists():
        rprint(f"[bold red]Error[/bold red]: HDF5 file not found: {hdf5_path}")
        raise typer.Exit(code=1)

    transformer = PrometheusToAtlasDataParser(
        timeseries_path=timeseries_folder_path,
        hdf5_path=hdf5_path,
        output_dir=output_dir,
        date_format_forecasting=date_format_forecasting,
        date_format_input_files=date_format_input_files,
        date_format_timestep=date_format_timestep,
    )
    transformer.process(use_multiprocessing=use_mp, n_workers=n_workers)
    rprint(f"[bold green]✓[/bold green] Dataset written to: {output_dir}")


@prometheus_app.command("batch")
def prometheus_batch(
    root_dir: Path = typer.Argument(help="Root directory containing module sub-directories"),
    output_root_dir: Path = typer.Option(..., "--output", "-o", help="Root output directory"),
    date_format_forecasting: str = _DATE_FORMAT_FORECASTING,
    date_format_input_files: str = _DATE_FORMAT_INPUT,
    date_format_timestep: str = _DATE_FORMAT_TIMESTEP,
    use_mp: bool = typer.Option(True, "--mp/--no-mp", help="Enable multiprocessing"),
    n_workers: int | None = typer.Option(None, "--workers", "-w", help="Number of worker processes"),
) -> None:
    """Convert all Prometheus datasets found in a directory to Atlas format.

    Each sub-directory must contain a 'ts/' folder and a single HDF5 file.

    \b
    Expected structure:
      root_dir/
      ├── day-ahead/
      │   ├── ts/
      │   └── uuid.hdf5
      └── portfolio-optimisation/
          ├── ts/
          └── uuid.hdf5

    \b
      atlas prometheus-to-atlas batch ./root_dir -o ./output/
    """
    if not root_dir.exists() or not root_dir.is_dir():
        rprint(f"[bold red]Error[/bold red]: Root directory not found: {root_dir}")
        raise typer.Exit(code=1)

    logger.info(f"Scanning directory: {root_dir}")

    module_dirs = sorted(d for d in root_dir.iterdir() if d.is_dir() and (d / "ts").is_dir())

    if not module_dirs:
        rprint("[bold red]Error[/bold red]: No valid module directories found.")
        raise typer.Exit(code=1)

    logger.info(f"Found {len(module_dirs)} module(s) to process")

    if use_mp and len(module_dirs) > 1:
        n_workers = n_workers or min(os.cpu_count() or 1, len(module_dirs))
        logger.info(f"Processing in parallel with {n_workers} workers")
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = [
                executor.submit(
                    _process_single_module,
                    d,
                    output_root_dir,
                    date_format_forecasting,
                    date_format_input_files,
                    date_format_timestep,
                    use_mp,
                )
                for d in module_dirs
            ]
            results = [f.result() for f in futures]
    else:
        results = [
            _process_single_module(
                d,
                output_root_dir,
                date_format_forecasting,
                date_format_input_files,
                date_format_timestep,
                use_mp,
            )
            for d in module_dirs
        ]

    ok = [name for name, success, _ in results if success]
    failed = [(name, msg) for name, success, msg in results if not success]

    for name in ok:
        logger.info(f"✓ {name}")
    for name, msg in failed:
        logger.error(f"✗ {name}: {msg}")

    rprint(f"\n[bold]Summary:[/bold] {len(ok)} succeeded, {len(failed)} failed out of {len(results)}")

    if not ok:
        raise typer.Exit(code=1)


def _process_single_module(
    module_dir: Path,
    output_root_dir: Path,
    date_format_forecasting: str,
    date_format_input_files: str,
    date_format_timestep: str,
    use_mp: bool = True,
) -> tuple[str, bool, str | None]:
    """Process a single module directory.

    Args:
        module_dir: Path to the module directory
        output_root_dir: Root directory for outputs
        date_format_forecasting: Date format for forecasting matrices
        date_format_input_files: Date format for input files
        date_format_timestep: Date format for timestep column

    Returns:
        Tuple of (module_name, success, error_message)
    """
    ts_dir = module_dir / "ts"
    if not ts_dir.exists() or not ts_dir.is_dir():
        return (module_dir.name, False, "No 'ts' directory found")

    hdf5_files = find_hdf5_files(module_dir)

    if len(hdf5_files) == 0:
        return (module_dir.name, False, "No valid HDF5 file found")
    elif len(hdf5_files) > 1:
        return (module_dir.name, False, f"Multiple HDF5 files found ({len(hdf5_files)})")

    hdf5_file = hdf5_files[0]
    output_dir = output_root_dir / module_dir.name

    try:
        transformer = PrometheusToAtlasDataParser(
            timeseries_path=ts_dir,
            hdf5_path=hdf5_file,
            output_dir=output_dir,
            date_format_forecasting=date_format_forecasting,
            date_format_input_files=date_format_input_files,
            date_format_timestep=date_format_timestep,
        )
        transformer.process(use_multiprocessing=use_mp)
        return (module_dir.name, True, None)
    except Exception as e:
        return (module_dir.name, False, str(e))
