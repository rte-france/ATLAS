import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import cast

import typer
from rich import print as rprint

import atlas
from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.config import logger
from atlas.io_utils.prometheus_transformer import PrometheusToAtlasDataParser, find_hdf5_files
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.orchestrator.step import ModuleRegistry
from atlas.orchestrator.workflow.workflow import Workflow
from atlas.timing import timer

app = typer.Typer()


@app.command()
def run(
    config_path: Path = typer.Argument(help="Workflow config YAML (--workflow) or module parameters YAML (default)"),
    workflow: bool = typer.Option(False, "--workflow", "-w", help="Run a workflow instead of a single module"),
    module_name: str | None = typer.Option(
        None,
        "--module",
        "-m",
        help=f"Module name. Valid modules: {', '.join(ModuleRegistry.get_names())}",
    ),
    dataset_path: Path | None = typer.Option(None, "--dataset", "-d", help="Path to the Atlas input dataset directory"),
) -> None:
    """Run an Atlas module or workflow.

    \b
    Module mode (default):
      atlas run parameters.yaml --module PortfolioOptimisation --dataset ./data/

    \b
    Workflow mode:
      atlas run workflow.yaml --workflow
    """
    if workflow:
        if not config_path.exists():
            rprint(f"[bold red]Error[/bold red]: Workflow configuration file not found: {config_path}")
            raise typer.Exit(code=1)

        logger.info(f"Running workflow: {config_path}")
        with timer() as t:
            wf = Workflow.from_file(config_path)
            wf.execute()
        logger.info(f"Workflow completed in {t()} seconds")
        logger.info("✓ Workflow completed successfully.")

    else:
        if module_name is None:
            rprint("Error: --module is required in module mode.")
            raise typer.Exit(code=1)

        if dataset_path is None:
            rprint("Error: --dataset is required in module mode.")
            raise typer.Exit(code=1)

        if not dataset_path.exists() or not dataset_path.is_dir():
            rprint(f"Error: Dataset directory not found: {dataset_path}")
            raise typer.Exit(code=1)

        if not config_path.exists():
            rprint(f"Error: Parameters file not found: {config_path}")
            raise typer.Exit(code=1)

        try:
            module_class = ModuleRegistry.get(module_name)
        except ValueError as e:
            rprint(f"Error: {e}")
            raise typer.Exit(code=1) from e

        logger.info(f"Running module: {module_name}")
        logger.info(f"  Dataset   : {dataset_path}")
        logger.info(f"  Parameters: {config_path}")

        try:
            with timer() as t:
                cis = CurrentInputState.from_directory(dataset_path)
                module = module_class()
                parameters = cast(AbstractParameters, module.get_parameters_class()).from_file(config_path)

                output_dataset = module.run(cis.data, parameters)

                if parameters.output.export_output_dataset:
                    CISHandler.apply(output_dataset.change_sets, cis)
                    cis.to_directory(parameters.get_output_dir())

            logger.info(f"Module '{module_name}' completed in {t()} seconds")
            rprint(f"[bold green]✓[/bold green] Module '{module_name}' completed successfully.")
        except Exception as e:
            logger.exception(f"✗ Module '{module_name}' failed: {e}")
            raise typer.Exit(code=1) from e


@app.command()
def version() -> None:
    """Print the version of the package."""
    rprint(f"[bold]Atlas version[/bold] : {atlas.__version__}")  # noqa: T201


@app.command()
def prometheus_to_atlas(
    timeseries_folder_path: Path,
    hdf5_path: Path,
    output_dir: Path,
    date_format_forecasting: str = "DD/MM/YYYY HH:mm:ss",
    date_format_input_files: str = "DD/MM/YYYY HH:mm:ss",
    date_format_timestep: str = "DD_MM_YYYY_HH_mm_ss",
    use_mp: bool = True,
    n_workers: int | None = None,
) -> None:
    """Convert Prometheus format data to Atlas dataset format."""

    if not timeseries_folder_path.exists():
        rprint(f"Error: Timeseries folder not found: {timeseries_folder_path}")
        raise typer.Exit(code=1)

    if not hdf5_path.exists():
        rprint(f"Error: HDF5 file not found: {hdf5_path}")
        raise typer.Exit(code=1)

    transformer = PrometheusToAtlasDataParser(
        timeseries_path=timeseries_folder_path,
        hdf5_path=hdf5_path,
        output_dir=output_dir,
        date_format_forecasting=date_format_forecasting,
        date_format_input_files=date_format_input_files,
        date_format_timestep=date_format_timestep,
    )
    transformer.process(
        use_multiprocessing=use_mp,
        n_workers=n_workers,
    )


@app.command()
def prometheus_to_atlas_recursive(
    root_dir: Path,
    output_root_dir: Path,
    date_format_forecasting: str = "DD/MM/YYYY HH:mm:ss",
    date_format_input_files: str = "DD/MM/YYYY HH:mm:ss",
    date_format_timestep: str = "DD_MM_YYYY_HH_mm_ss",
    use_mp: bool = True,
    n_workers: int | None = None,
) -> None:
    """
    Recursively convert all Prometheus datasets in a folder to Atlas format.
    Expects a directory structure where each module has:

    - A 'ts' folder containing timeseries CSV files

    - A single HDF5 file (typically with a UUID name)

    Example structure:

    \b
    root_dir/
    ├── day-ahead/
    │   ├── ts/
    │   └── uuid-file.hdf5
    ├── portfolio-optimisation/
    │   ├── ts/
    │   └── uuid-file.hdf5
    └── market-clearing/
        ├── ts/
        └── uuid-file.hdf5
    """
    if not root_dir.exists():
        rprint(f"[bold red]Error[/bold red]: Root directory not found: {root_dir}")
        raise typer.Exit(code=1)

    if not root_dir.is_dir():
        rprint(f"[bold red]Error[/bold red]: Path is not a directory: {root_dir}")
        raise typer.Exit(code=1)

    logger.info(f"Scanning directory:{root_dir}")

    module_dirs = []
    for module_dir in sorted(root_dir.iterdir()):
        if module_dir.is_dir() and (module_dir / "ts").exists() and (module_dir / "ts").is_dir():
            module_dirs.append(module_dir)

    if not module_dirs:
        logger.error("No valid module directories found.")
        raise typer.Exit(code=1)

    logger.info(f"Found {len(module_dirs)} module(s) to process")

    if use_mp and len(module_dirs) > 1:
        n_workers = n_workers or min(os.cpu_count() or 1, len(module_dirs))
        logger.info(f"Processing modules in parallel using {n_workers} workers")

        # Process modules in parallel using ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = [
                executor.submit(
                    _process_single_module,
                    module_dir,
                    output_root_dir,
                    date_format_forecasting,
                    date_format_input_files,
                    date_format_timestep,
                    use_mp,
                )
                for module_dir in module_dirs
            ]
            # Collect results as futures complete
            results = [future.result() for future in futures]
    else:
        if not use_mp:
            logger.info("Processing modules sequentially (multiprocessing disabled)")

        results = []
        for module_dir in module_dirs:
            logger.info(f"Processing module: {module_dir.name}")
            result = _process_single_module(
                module_dir,
                output_root_dir,
                date_format_forecasting,
                date_format_input_files,
                date_format_timestep,
                use_mp,
            )
            results.append(result)

    # Process results
    modules_processed = 0
    modules_failed = 0

    logger.info("\nResults:")
    for module_name, success, error_msg in results:
        if success:
            logger.info(f"✓ {module_name}: Successfully processed")
            modules_processed += 1
        else:
            logger.info(f"✗ {module_name}: {error_msg}")
            modules_failed += 1

    logger.info("Summary:")
    logger.info(f"  Processed: {modules_processed}")
    logger.info(f"  Failed: {modules_failed}")
    logger.info(f"  Total: {modules_processed + modules_failed}")

    if modules_processed == 0:
        rprint("\n[bold yellow]No modules were processed.[/bold yellow]")
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
