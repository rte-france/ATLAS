from pathlib import Path

import typer
from rich import print as rprint

import atlas
from atlas.io_utils.prometheus_transformer import PrometheusToAtlasDataParser

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
    # Validate input paths
    if not timeseries_folder_path.exists():
        rprint(f"[bold red]Error:[/bold red] Timeseries folder not found: {timeseries_folder_path}")
        raise typer.Exit(code=1)

    if not hdf5_path.exists():
        rprint(f"[bold red]Error:[/bold red] HDF5 file not found: {hdf5_path}")
        raise typer.Exit(code=1)

    # Start conversion
    rprint("[bold blue]Converting Prometheus data to Atlas format...[/bold blue]")

    try:
        transformer = PrometheusToAtlasDataParser(
            timeseries_path=timeseries_folder_path,
            hdf5_path=hdf5_path,
            root_input_directory=output_dir,
            date_format_forecasting=date_format_forecasting,
            date_format_input_files=date_format_input_files,
            date_format_timestep=date_format_timestep,
        )
        transformer.process()
        rprint(f"[bold green]✓[/bold green] Successfully converted data to: {output_dir}")

    except Exception as e:
        rprint(f"[bold red]Error during conversion:[/bold red] {e}")
        raise typer.Exit(code=1) from e
