from pathlib import Path

import typer
from rich import print as rprint

import atlas
from atlas.io_utils.prometheus_transformer import PrometheusToAtlasDataParser, _find_hdf5_files

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
    transformer.process()


@app.command()
def prometheus_to_atlas_recursive(
    root_dir: Path,
    output_root_dir: Path,
    date_format_forecasting: str = "DD/MM/YYYY HH:mm:ss",
    date_format_input_files: str = "DD/MM/YYYY HH:mm:ss",
    date_format_timestep: str = "DD_MM_YYYY_HH_mm_ss",
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

    # Find all subdirectories that contain a 'ts' folder
    modules_processed = 0
    modules_failed = 0

    rprint(f"\n[bold cyan]Scanning directory:[/bold cyan] {root_dir}")

    for module_dir in sorted(root_dir.iterdir()):
        if not module_dir.is_dir():
            continue

        ts_dir = module_dir / "ts"
        if not ts_dir.exists() or not ts_dir.is_dir():
            continue

        # Find valid HDF5 files
        hdf5_files = _find_hdf5_files(module_dir)

        if len(hdf5_files) == 0:
            rprint(f"[yellow]Warning:[/yellow] Skipping {module_dir.name} - no valid HDF5 file found")
            modules_failed += 1
            continue
        elif len(hdf5_files) > 1:
            rprint(
                f"[yellow]Warning:[/yellow] Skipping {module_dir.name} - multiple HDF5 files found ({len(hdf5_files)})"
            )
            modules_failed += 1
            continue

        hdf5_file = hdf5_files[0]
        output_dir = output_root_dir / module_dir.name

        rprint(f"\n[bold green]Processing module:[/bold green] {module_dir.name}")
        rprint(f"  HDF5 file: {hdf5_file.name}")
        rprint(f"  Output: {output_dir}")

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
            rprint(f"[bold green]✓[/bold green] Successfully processed {module_dir.name}")
            modules_processed += 1
        except Exception as e:
            rprint(f"[bold red]✗[/bold red] Failed to process {module_dir.name}: {e}")
            modules_failed += 1

    rprint("\n[bold cyan]Summary:[/bold cyan]")
    rprint(f"  Processed: [green]{modules_processed}[/green]")
    rprint(f"  Failed: [red]{modules_failed}[/red]")
    rprint(f"  Total: {modules_processed + modules_failed}")

    if modules_processed == 0:
        rprint("\n[bold yellow]No modules were processed.[/bold yellow]")
        raise typer.Exit(code=1)
