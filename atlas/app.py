import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import typer
from rich import print as rprint

import atlas
from atlas.io_utils.prometheus_transformer import PrometheusToAtlasDataParser, find_hdf5_files

app = typer.Typer()


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
        rprint(f"[bold red]Error:[/bold red] Timeseries folder not found: {timeseries_folder_path}")
        raise typer.Exit(code=1)

    if not hdf5_path.exists():
        rprint(f"[bold red]Error:[/bold red] HDF5 file not found: {hdf5_path}")
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
        rprint(f"[bold red]Error:[/bold red] Root directory not found: {root_dir}")
        raise typer.Exit(code=1)

    if not root_dir.is_dir():
        rprint(f"[bold red]Error:[/bold red] Path is not a directory: {root_dir}")
        raise typer.Exit(code=1)

    rprint(f"\n[bold cyan]Scanning directory:[/bold cyan] {root_dir}")

    module_dirs = []
    for module_dir in sorted(root_dir.iterdir()):
        if module_dir.is_dir() and (module_dir / "ts").exists() and (module_dir / "ts").is_dir():
            module_dirs.append(module_dir)

    if not module_dirs:
        rprint("[bold yellow]No valid module directories found.[/bold yellow]")
        raise typer.Exit(code=1)

    rprint(f"Found {len(module_dirs)} module(s) to process")

    if use_mp and len(module_dirs) > 1:
        n_workers = n_workers or min(os.cpu_count() or 1, len(module_dirs))
        rprint(f"[bold cyan]Processing modules in parallel using {n_workers} workers[/bold cyan]")

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
                )
                for module_dir in module_dirs
            ]
            # Collect results as futures complete
            results = [future.result() for future in futures]
    else:
        if not use_mp:
            rprint("[bold cyan]Processing modules sequentially (multiprocessing disabled)[/bold cyan]")

        results = []
        for module_dir in module_dirs:
            rprint(f"\n[bold green]Processing module:[/bold green] {module_dir.name}")
            result = _process_single_module(
                module_dir,
                output_root_dir,
                date_format_forecasting,
                date_format_input_files,
                date_format_timestep,
            )
            results.append(result)

    # Process results
    modules_processed = 0
    modules_failed = 0

    rprint("\n[bold cyan]Results:[/bold cyan]")
    for module_name, success, error_msg in results:
        if success:
            rprint(f"[bold green]✓[/bold green] {module_name}: Successfully processed")
            modules_processed += 1
        else:
            rprint(f"[bold red]✗[/bold red] {module_name}: {error_msg}")
            modules_failed += 1

    rprint("\n[bold cyan]Summary:[/bold cyan]")
    rprint(f"  Processed: [green]{modules_processed}[/green]")
    rprint(f"  Failed: [red]{modules_failed}[/red]")
    rprint(f"  Total: {modules_processed + modules_failed}")

    if modules_processed == 0:
        rprint("\n[bold yellow]No modules were processed.[/bold yellow]")
        raise typer.Exit(code=1)


def _process_single_module(
    module_dir: Path,
    output_root_dir: Path,
    date_format_forecasting: str,
    date_format_input_files: str,
    date_format_timestep: str,
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
        transformer.process()
        return (module_dir.name, True, None)
    except Exception as e:
        return (module_dir.name, False, str(e))
